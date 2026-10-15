# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
The three overridden standard methods, each with a normal, a negative and a
standard-preserved test (O1 sale.order.action_confirm, O3
stock.picking.button_validate, O4 account.move.action_post).
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CreditControlCase


@tagged("post_install", "-at_install", "odt_customer_credit_control")
class TestOverrides(CreditControlCase):
    """O1, O3 and O4."""

    def _al_nakheel_at(self, amount):
        """Confirm October credit sales of the given amount for Al Nakheel."""
        self.confirm_on(self.make_order(self.al_nakheel, amount), "2026-10-10 09:00:00")

    def test_o1_negative_waits_for_approval(self):
        """At 420,000 of a 500,000 cap, a 90,000 Net 30 order waits for approval."""
        self._al_nakheel_at(420_000)
        order = self.make_order(self.al_nakheel, 90_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.credit_approval, "pending")
        self.assertIn(order.state, ("draft", "sent"))

    def test_o1_normal_confirms_at_cap(self):
        """At 420,000 of a 500,000 cap, an 80,000 Net 30 order confirms exactly at the cap."""
        self._al_nakheel_at(420_000)
        order = self.make_order(self.al_nakheel, 80_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.credit_approval, "none")

    def test_o1_standard_preserved_advance_order(self):
        """A 100% advance order of a customer at its cap confirms exactly as standard."""
        self._al_nakheel_at(500_000)
        order = self.make_order(self.al_nakheel, 300_000, term=self.advance)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.credit_approval, "none")
        self.assertEqual(order.invoice_status, "to invoice")
        self.assertEqual(str(order.date_order), "2026-10-20 09:00:00")
        if "picking_ids" in order._fields:
            self.assertTrue(order.picking_ids, "standard deliveries were not created")

    def test_o3_negative_hold_refuses_delivery(self):
        """A ready delivery to Al Nakheel on hold cannot be validated."""
        picking = self.make_picking(self.al_nakheel, "outgoing")
        self.set_state(self.al_nakheel, "action_credit_hold")
        with self.assertRaises(UserError):
            picking.button_validate()

    def test_o3_normal_delivery_done(self):
        """Back to normal, Al Nakheel's delivery is validated."""
        picking = self.make_picking(self.al_nakheel, "outgoing")
        self.set_state(self.al_nakheel, "action_credit_hold")
        self.set_state(self.al_nakheel, "action_credit_lift_hold", "Paid")
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_o3_standard_preserved_receipt(self):
        """A receipt from a supplier who is also a held customer is validated as standard."""
        self.set_state(self.al_nakheel, "action_credit_hold")
        receipt = self.make_picking(self.al_nakheel, "incoming")
        receipt.button_validate()
        self.assertEqual(receipt.state, "done")

    def test_o4_negative_block_refuses_invoice(self):
        """A customer invoice of Gulf Pipes under absolute block cannot be posted."""
        self.set_state(self.gulf_pipes, "action_credit_block")
        with self.assertRaises(UserError):
            self.make_invoice(self.gulf_pipes, 1_000, date(2026, 10, 20))

    def test_o4_normal_invoice_posted(self):
        """Back to normal, Gulf Pipes' invoice is posted."""
        self.set_state(self.gulf_pipes, "action_credit_block")
        self.set_state(self.gulf_pipes, "action_credit_unblock", "Settled")
        invoice = self.make_invoice(self.gulf_pipes, 1_000, date(2026, 10, 20))
        self.assertEqual(invoice.state, "posted")

    def test_o4_standard_preserved_vendor_bill(self):
        """A vendor bill from a blocked customer posts as standard."""
        self.set_state(self.gulf_pipes, "action_credit_block")
        bill = self.make_invoice(
            self.gulf_pipes, 1_000, date(2026, 10, 20), move_type="in_invoice"
        )
        self.assertEqual(bill.state, "posted")
