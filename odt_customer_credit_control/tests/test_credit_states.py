# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""Customer credit states, the nightly check, blocks and the weekly report (REQ-023)."""

from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import CreditControlCase


@tagged("post_install", "-at_install", "odt_customer_credit_control")
class TestCreditStates(CreditControlCase):
    """REQ-023 T1 to T4 and T8 to T14."""

    def test_req023_t1_overdue_watch_list(self):
        """An invoice due 15 October and unpaid puts Al Nakheel on the watch list on 16 October."""
        self.make_invoice(self.al_nakheel, 10_000, date(2026, 10, 15))
        self.run_credit_check("2026-10-16 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "watch")

    def test_req023_t2_due_today_stays_normal(self):
        """On its due date the invoice is not overdue: Al Nakheel stays normal."""
        self.make_invoice(self.al_nakheel, 10_000, date(2026, 10, 15))
        self.run_credit_check("2026-10-15 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "normal")

    def test_req023_t3_paid_leaves_watch_list(self):
        """Paid in full on 20 October, the invoice no longer keeps Al Nakheel on the list."""
        invoice = self.make_invoice(self.al_nakheel, 10_000, date(2026, 10, 15))
        self.run_credit_check("2026-10-16 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "watch")
        with self.freeze("2026-10-20 10:00:00"):
            self.env["account.payment.register"].with_context(
                active_model="account.move", active_ids=invoice.ids
            ).create({"payment_date": date(2026, 10, 20)})._create_payments()
        self.assertEqual(invoice.payment_state in ("paid", "in_payment"), True)
        self.run_credit_check("2026-10-21 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "normal")

    def test_req023_t4_finance_flags_by_hand(self):
        """Finance flags Gulf Pipes for an open dispute: it is on the watch list with the reason."""
        self.gulf_pipes.with_user(self.accountant).action_credit_flag(
            "Open dispute on delivery DN-77"
        )
        self.assertEqual(self.gulf_pipes.credit_state, "watch")
        self.assertEqual(
            self.gulf_pipes.credit_state_reason, "Open dispute on delivery DN-77"
        )
        self.run_credit_check("2026-10-16 01:00:00")
        self.assertEqual(self.gulf_pipes.credit_state, "watch")

    def test_req023_t8_hold_refuses_confirmation(self):
        """A salesperson cannot confirm a new order for Al Nakheel on credit hold."""
        self.set_state(self.al_nakheel, "action_credit_hold")
        order = self.make_order(self.al_nakheel, 10_000)
        with self.assertRaises(UserError):
            self.confirm_on(order.with_user(self.salesperson), "2026-10-20 09:00:00")
        self.assertIn(order.state, ("draft", "sent"))

    def test_req023_t9_hold_refuses_delivery(self):
        """The warehouse keeper cannot validate a ready delivery to Al Nakheel on hold."""
        picking = self.make_picking(self.al_nakheel, "outgoing")
        self.set_state(self.al_nakheel, "action_credit_hold")
        with self.assertRaises(UserError):
            picking.button_validate()
        self.assertNotEqual(picking.state, "done")

    def test_req023_t10_block_refuses_quotation(self):
        """A quotation for Gulf Pipes under absolute block cannot be saved."""
        self.set_state(self.gulf_pipes, "action_credit_block")
        with self.assertRaises(ValidationError):
            self.make_order(self.gulf_pipes, 5_000)

    def test_req023_t11_weekly_report_order(self):
        """Management gets the watch list ordered 180,000, 95,000, 40,000."""
        self.make_invoice(self.gulf_pipes, 180_000, date(2026, 10, 1))
        self.make_invoice(self.big_buyer, 95_000, date(2026, 10, 1))
        self.make_invoice(self.al_nakheel, 40_000, date(2026, 10, 1))
        self.run_credit_check("2026-10-24 01:00:00")
        with self.freeze("2026-10-25 06:00:00"):
            self.env["res.partner"]._cron_credit_watch_report()
        mail = self.env["mail.mail"].search(
            [("subject", "ilike", "credit watch list")], order="id desc", limit=1
        )
        self.assertTrue(mail, "the weekly email was not created")
        self.assertIn(self.finance_manager.partner_id, mail.recipient_ids)
        body = str(mail.body_html)
        positions = [
            body.find(p.name)
            for p in (self.gulf_pipes, self.big_buyer, self.al_nakheel)
        ]
        self.assertTrue(all(pos >= 0 for pos in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_req023_t12_sixty_days_stays_watch(self):
        """60 days overdue on 14 October: Al Nakheel stays on the watch list, not on hold."""
        self.make_invoice(self.al_nakheel, 25_000, date(2026, 8, 15))
        self.run_credit_check("2026-10-14 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "watch")

    def test_req023_t13_sixty_one_days_hold(self):
        """61 days overdue on 15 October: credit hold, and a new order cannot be confirmed."""
        self.make_invoice(self.al_nakheel, 25_000, date(2026, 8, 15))
        self.run_credit_check("2026-10-15 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "hold")
        order = self.make_order(self.al_nakheel, 1_000)
        with self.assertRaises(UserError):
            self.confirm_on(order, "2026-10-15 09:00:00")

    def test_req023_t14_lifted_hold_not_reset(self):
        """A hold lifted on 16 October is not set again on 17 October for the same invoice."""
        self.make_invoice(self.al_nakheel, 25_000, date(2026, 8, 15))
        self.run_credit_check("2026-10-15 01:00:00")
        self.assertEqual(self.al_nakheel.credit_state, "hold")
        with self.freeze("2026-10-16 10:00:00"):
            self.set_state(
                self.al_nakheel, "action_credit_lift_hold", "Payment plan agreed"
            )
        self.run_credit_check("2026-10-17 01:00:00")
        self.assertNotEqual(self.al_nakheel.credit_state, "hold")
        self.assertEqual(self.al_nakheel.credit_state, "watch")

    def test_access_only_finance_manager_lifts_hold(self):
        """A salesperson or an accountant cannot set or lift a hold."""
        self.set_state(self.al_nakheel, "action_credit_hold")
        for user in (self.salesperson, self.accountant):
            partner = self.al_nakheel.with_user(user)
            with self.assertRaises(AccessError):
                partner.action_credit_lift_hold("Paid")
            with self.assertRaises(AccessError):
                partner.write({"credit_state": "normal"})
        self.assertEqual(self.al_nakheel.credit_state, "hold")
