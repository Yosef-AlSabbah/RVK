# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
The spec's tests for sending quotations: the payment term and its approval
(REQ-024 T1-T3), the special-item minimum advance (T4, T5), the special
marking down to purchase (T6) and the watch-list sending approval (REQ-023
T5-T7).
"""

from datetime import datetime

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import QuotationTermsCase


@tagged("post_install", "-at_install", "odt_quotation_payment_terms")
class TestQuotationSend(QuotationTermsCase):
    """REQ-024 T1-T6 and REQ-023 T5-T7."""

    def test_req024_t1_no_term_refused(self):
        """S00533 without a payment term cannot be sent, and the missing term is named."""
        order = self.make_quotation(self.al_nakheel, term=False)
        with self.assertRaisesRegex(UserError, "payment term"):
            order.with_user(self.salesperson).action_quotation_send()
        self.assertEqual(order.state, "draft")

    def test_req024_t2_non_default_term_refused(self):
        """S00533 on Net 60 against Al Nakheel's Net 30 default waits for the Finance Manager."""
        order = self.make_quotation(self.al_nakheel, term=self.net60)
        self.assertTrue(order.is_term_approval_needed)
        with self.assertRaisesRegex(UserError, "Finance Manager"):
            order.with_user(self.salesperson).action_quotation_send()
        self.assertEqual(order.state, "draft")

    def test_req024_t3_finance_approval_sends(self):
        """Once the Finance Manager approves Net 60, S00533 is sent showing who and when."""
        order = self.make_quotation(self.al_nakheel, term=self.net60)
        with self.freeze("2026-10-15 10:00:00"):
            order.with_user(self.finance_manager).action_approve_payment_term()
        self.assertEqual(order.term_approved_by_id, self.finance_manager)
        self.assertEqual(order.term_approval_date, datetime(2026, 10, 15, 10, 0, 0))
        self.assertFalse(order.is_term_approval_needed)
        self.send(order)
        self.assertEqual(order.state, "sent")

    def test_req024_t4_special_below_minimum_refused(self):
        """A special gate valve on a 30% advance term is refused, naming the 50% minimum."""
        order = self.make_quotation(
            self.al_nakheel,
            term=self.advance30,
            products=[self.valve, self.special_valve],
        )
        order.with_user(self.finance_manager).action_approve_payment_term()
        with self.assertRaisesRegex(UserError, "50"):
            order.with_user(self.salesperson).action_quotation_send()
        self.assertEqual(order.state, "draft")

    def test_req024_t5_special_at_minimum_sends(self):
        """The same quotation moved to a 50% advance term is sent (the minimum itself is enough)."""
        order = self.make_quotation(
            self.al_nakheel,
            term=self.advance30,
            products=[self.valve, self.special_valve],
        )
        order.write({"payment_term_id": self.advance50.id})
        order.with_user(self.finance_manager).action_approve_payment_term()
        self.send(order)
        self.assertEqual(order.state, "sent")

    def test_req024_t6_special_marking_on_purchase(self):
        """The confirmed order's special line, and the purchase line raised for it, show Special."""
        order = self.make_quotation(
            self.al_nakheel,
            term=self.advance50,
            products=[self.valve, self.special_valve],
        )
        order.with_user(self.finance_manager).action_approve_payment_term()
        special_line = order.order_line.filtered(
            lambda line: line.product_id == self.special_valve
        )
        self.assertTrue(special_line.is_special, "not marked on the quotation line")
        self.send(order)
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertTrue(special_line.is_special, "not marked on the order line")
        self.assertFalse((order.order_line - special_line).is_special)

        purchase_line_vals = {
            "product_id": self.special_valve.id,
            "product_qty": 1,
            "price_unit": 18000.0,
            "tax_ids": [Command.clear()],
        }
        if "sale_line_id" in self.env["purchase.order.line"]._fields:
            purchase_line_vals["sale_line_id"] = special_line.id
        purchase = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "origin": order.name,
                "order_line": [Command.create(purchase_line_vals)],
            }
        )
        self.assertTrue(
            purchase.order_line.is_special, "not marked on the purchase line"
        )

    def test_req023_t5_watch_list_refused(self):
        """S00520 for watch-listed Al Nakheel cannot be sent without approval."""
        self.watch_list(self.al_nakheel)
        order = self.make_quotation(self.al_nakheel)
        self.assertTrue(order.is_send_approval_needed)
        with self.assertRaisesRegex(UserError, "watch list"):
            order.with_user(self.salesperson).action_quotation_send()
        self.assertEqual(order.state, "draft")

    def test_req023_t6_operations_manager_approves(self):
        """The Operations Manager approves S00520; it is sent and shows his name and the date."""
        self.watch_list(self.al_nakheel)
        order = self.make_quotation(self.al_nakheel)
        with self.freeze("2026-10-15 11:30:00"):
            order.with_user(self.operations_manager).action_approve_sending()
        self.assertEqual(order.send_approved_by_id, self.operations_manager)
        self.assertEqual(order.send_approval_date, datetime(2026, 10, 15, 11, 30, 0))
        self.assertFalse(order.is_send_approval_needed)
        self.send(order)
        self.assertEqual(order.state, "sent")

    def test_req023_t7_sales_manager_cannot_approve(self):
        """The Sales Manager's approval of S00520 is refused as outside his rights."""
        self.watch_list(self.al_nakheel)
        order = self.make_quotation(self.al_nakheel)
        with self.assertRaises(AccessError):
            order.with_user(self.sales_manager).action_approve_sending()
        self.assertFalse(order.send_approved_by_id)
        self.assertTrue(order.is_send_approval_needed)

    def test_access_salesperson_cannot_approve_term(self):
        """Only the Finance Manager approves a payment term other than the customer's default."""
        order = self.make_quotation(self.al_nakheel, term=self.net60)
        for user in (self.salesperson, self.sales_manager, self.operations_manager):
            with self.assertRaises(AccessError):
                order.with_user(user).action_approve_payment_term()
        self.assertFalse(order.term_approved_by_id)

    def test_access_term_change_needs_new_approval(self):
        """An approved Net 60 that the salesperson changes to another term needs approval again."""
        order = self.make_quotation(self.al_nakheel, term=self.net60)
        order.with_user(self.finance_manager).action_approve_payment_term()
        order.with_user(self.salesperson).write({"payment_term_id": self.advance50.id})
        self.assertFalse(order.term_approved_by_id)
        with self.assertRaisesRegex(UserError, "Finance Manager"):
            order.with_user(self.salesperson).action_quotation_send()
