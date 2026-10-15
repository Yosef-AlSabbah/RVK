# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
REQ-104: a vendor bill is paid only when its Should Be Paid is Yes, singly or
in a batch, except a service bill raised without a purchase order.
"""

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import DAY, PaymentControlCase


@tagged("post_install", "-at_install", "odt_supplier_payment_control")
class TestBillMatching(PaymentControlCase):
    """REQ-104 T1 to T4."""

    def _p00531(self):
        """PO P00531: 100 valves ordered, 80 received."""
        order = self.make_order(100)
        self.receive(order, 80)
        return order

    def test_req104_t1_unmatched_bill_refused(self):
        """A posted bill for 100 valves of which 80 were received cannot be paid."""
        order = self._p00531()
        bill = self.order_bill(order, 100)
        self.assertNotEqual(bill.release_to_pay, "yes")
        with self.assertRaisesRegex(UserError, bill.name):
            self.register(bill)
        self.assertFalse(bill.matched_payment_ids)
        self.assertEqual(bill.payment_state, "not_paid")

    def test_req104_t2_corrected_bill_paid(self):
        """The P00531 bill corrected to the 80 received is paid."""
        order = self._p00531()
        bill = self.order_bill(order, 100)
        bill.button_draft()
        bill.invoice_line_ids.quantity = 80
        with freeze_time(DAY):
            bill.action_post()
        self.assertEqual(bill.release_to_pay, "yes")
        payments = self.register(bill)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments.amount, 8_000)
        self.assertIn(payments.state, ("in_process", "paid"))

    def test_req104_t3_batch_names_unmatched_bill(self):
        """A batch holding the unmatched P00531 bill and a matched bill is refused, naming the first."""
        order = self._p00531()
        unmatched = self.order_bill(order, 100)
        other = self.make_order(10)
        self.receive(other, 10)
        matched = self.order_bill(other, 10, ref="BILL-P00532")
        self.assertEqual(matched.release_to_pay, "yes")
        payments = self.make_payment(
            self.valvitalia, 10_000, "BILL-P00531", invoice_ids=unmatched.ids
        ) | self.make_payment(
            self.valvitalia, 1_000, "BILL-P00532", invoice_ids=matched.ids
        )
        batch = self.make_batch(payments)
        with self.assertRaisesRegex(UserError, unmatched.name) as caught:
            batch.validate_batch()
        self.assertNotIn(matched.name, str(caught.exception))
        self.assertEqual(batch.state, "draft")

    def test_req104_t4_service_bill_without_order_paid(self):
        """A 12,000 SAR consultancy bill raised without a purchase order is paid without a match."""
        bill = self.make_bill(
            self.consultant, [(self.consultancy, 1, 12_000, False)], ref="GAC-2026-114"
        )
        self.assertNotEqual(bill.release_to_pay, "yes")
        payments = self.register(bill)
        self.assertEqual(payments.amount, 12_000)
        self.assertIn(payments.state, ("in_process", "paid"))
