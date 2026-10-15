# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
The three overridden standard methods, each with a negative, a normal and a
standard-preserved test (O1 account.payment.register.action_create_payments,
O2 account.batch.payment.validate_batch, O3 account.payment.action_post).
"""

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import DAY, PaymentControlCase


@tagged("post_install", "-at_install", "odt_supplier_payment_control")
class TestOverrides(PaymentControlCase):
    """O1, O2 and O3."""

    def _bill_0412(self, qty_received=0):
        """Bill BILL/2026/0412: 10 valves ordered and billed, the given quantity received."""
        order = self.make_order(10)
        if qty_received:
            self.receive(order, qty_received)
        return self.order_bill(order, 10, ref="BILL/2026/0412")

    def _customer_invoice(self, amount):
        """Post a customer invoice of the given amount."""
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_date": DAY,
                "invoice_date_due": DAY,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.valve.id,
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        with freeze_time(DAY):
            invoice.action_post()
        return invoice

    def _customer_payment(self, amount, memo):
        """Prepare a draft incoming customer payment to the RVK bank."""
        return self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.customer.id,
                "amount": amount,
                "memo": memo,
                "date": DAY,
                "journal_id": self.bank.id,
            }
        )

    # O1 ----------------------------------------------------------------

    def test_o1_negative_unmatched_bill_refused(self):
        """Bill BILL/2026/0412 with Should Be Paid No cannot be paid."""
        bill = self._bill_0412()
        self.assertEqual(bill.release_to_pay, "no")
        with self.assertRaisesRegex(UserError, bill.name):
            self.register(bill)
        self.assertFalse(bill.matched_payment_ids)

    def test_o1_normal_bill_set_to_yes_paid(self):
        """The same bill set to Yes by the Finance Manager is paid."""
        bill = self._bill_0412()
        bill.with_user(self.finance_manager).write(
            {"release_to_pay_manual": "yes", "force_release_to_pay": True}
        )
        self.assertEqual(bill.release_to_pay, "yes")
        payments = self.register(bill)
        self.assertEqual(payments.amount, 1_000)
        self.assertIn(payments.state, ("in_process", "paid"))

    def test_o1_normal_large_payment_waits_for_approval(self):
        """A matched 60,000 SAR bill gets its payment, which waits for the Finance Manager (REQ-104-T-FR4)."""
        order = self.make_order(600)
        self.receive(order, 600)
        bill = self.order_bill(order, 600, ref="BILL/2026/0413")
        payments = self.register(bill)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments.state, "draft")
        self.assertEqual(payments.approval_state, "to_approve_finance")
        self.approve(payments, self.finance_manager)
        self.post(payments)
        self.assertIn(payments.state, ("in_process", "paid"))

    def test_o1_large_payment_waits_with_outstanding_account(self):
        """With an outstanding account the entry is made at registration; the payment still waits."""
        outstanding = self.env["account.account"].create(
            {
                "name": "Outstanding Payments (test)",
                "code": "101999",
                "account_type": "asset_current",
                "reconcile": True,
            }
        )
        self.bank.outbound_payment_method_line_ids.payment_account_id = outstanding
        order = self.make_order(600)
        self.receive(order, 600)
        bill = self.order_bill(order, 600, ref="BILL/2026/0414")
        payments = self.register(bill)
        self.assertEqual(payments.state, "draft")
        self.assertEqual(payments.approval_state, "to_approve_finance")
        self.assertNotEqual(payments.move_id.state, "posted")
        self.approve(payments, self.finance_manager)
        self.post(payments)
        self.assertIn(payments.state, ("in_process", "paid"))
        self.assertEqual(payments.move_id.state, "posted")

    def test_o1_standard_preserved_customer_invoice(self):
        """Registering payment of a customer invoice behaves as standard, with no approval."""
        invoice = self._customer_invoice(70_000)
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create({"payment_date": DAY, "journal_id": self.bank.id})
        )
        with freeze_time(DAY):
            wizard.action_create_payments()
        payment = invoice.matched_payment_ids
        self.assertEqual(payment.amount, 70_000)
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertFalse(payment.approval_state)
        self.assertFalse(payment.approval_ids)
        self.assertIn(invoice.payment_state, ("in_payment", "paid"))

    # O2 ----------------------------------------------------------------

    def test_o2_negative_batch_names_unmatched_bill(self):
        """A batch with one matched and one unmatched bill is refused, naming the unmatched one."""
        unmatched = self._bill_0412()
        order = self.make_order(5)
        self.receive(order, 5)
        matched = self.order_bill(order, 5, ref="BILL/2026/0414")
        batch = self.make_batch(
            self.make_payment(
                self.valvitalia, 1_000, "BILL/2026/0412", invoice_ids=unmatched.ids
            )
            | self.make_payment(
                self.valvitalia, 500, "BILL/2026/0414", invoice_ids=matched.ids
            )
        )
        with self.assertRaisesRegex(UserError, unmatched.name):
            batch.validate_batch()
        self.assertEqual(batch.state, "draft")

    def test_o2_normal_matched_batch_validated(self):
        """A batch of matched bills is validated and its payments sent."""
        bills = self.env["account.move"]
        for qty, ref in ((5, "BILL/2026/0415"), (7, "BILL/2026/0416")):
            order = self.make_order(qty)
            self.receive(order, qty)
            bills |= self.order_bill(order, qty, ref=ref)
        payments = self.env["account.payment"]
        for bill in bills:
            payments |= self.make_payment(
                self.valvitalia, bill.amount_total, bill.ref, invoice_ids=bill.ids
            )
        batch = self.make_batch(payments)
        with freeze_time(DAY):
            batch.validate_batch()
        self.assertTrue(all(payments.mapped("is_sent")))
        self.assertEqual(batch.state, "sent")

    def test_o2_standard_preserved_customer_receipts(self):
        """A batch of customer receipts is validated as standard."""
        receipts = self._customer_payment(900_000, "R-1") | self._customer_payment(
            700_000, "R-2"
        )
        batch = self.make_batch(receipts, batch_type="inbound")
        with freeze_time(DAY):
            batch.validate_batch()
        self.assertTrue(all(receipts.mapped("is_sent")))
        self.assertTrue(
            all(state in ("in_process", "paid") for state in receipts.mapped("state"))
        )
        self.assertFalse(receipts.approval_ids)

    # O3 ----------------------------------------------------------------

    def test_o3_negative_ceo_missing_refused(self):
        """400,000 SAR approved by Finance and Operations only is refused until the Chief Executive approves."""
        self.rvk.approval_threshold_3 = 300_000
        payment = self.make_payment(self.valvitalia, 400_000, "INV-VT-2026-1001")
        self.approve(payment, self.finance_manager, self.ops_manager)
        with self.assertRaisesRegex(UserError, "Chief Executive"):
            self.post(payment)
        self.assertEqual(payment.state, "draft")
        self.approve(payment, self.ceo)
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))

    def test_o3_normal_finance_approved_posts(self):
        """60,000 SAR approved by the Finance Manager posts."""
        payment = self.make_payment(self.valvitalia, 60_000, "INV-VT-2026-1002")
        self.approve(payment, self.finance_manager)
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual(payment.approval_state, "posted")

    def test_o3_standard_preserved_customer_payment(self):
        """An incoming 900,000 SAR customer payment posts as standard with no approval."""
        payment = self._customer_payment(900_000, "R-3")
        with freeze_time(DAY):
            payment.action_post()
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertFalse(payment.approval_state)
        self.assertFalse(payment.approval_ids)
