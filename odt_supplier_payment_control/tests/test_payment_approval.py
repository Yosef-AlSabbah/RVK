# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
REQ-105: approval levels by amount, the duplicate block and its release, the
shareholder rule, trusted accounts, and the approvals' access and company rule.
"""

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import PaymentControlCase


@tagged("post_install", "-at_install", "odt_supplier_payment_control")
class TestPaymentApproval(PaymentControlCase):
    """REQ-105 T1 to T8, the approval record rule and the access checks."""

    def _valvitalia_posted(self):
        """The posted 84,300 SAR payment to Valvitalia with reference INV-VT-2026-0917."""
        payment = self.make_payment(self.valvitalia, 84_300, "INV-VT-2026-0917")
        self.approve(payment, self.finance_manager)
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))
        return payment

    def test_req105_t1_ceo_needed_above_third(self):
        """600,000 SAR approved by Finance and Operations waits for the Chief Executive."""
        payment = self.make_payment(self.valvitalia, 600_000, "INV-VT-2026-0950")
        self.assertEqual(payment.approval_state, "to_approve_finance")
        self.approve(payment, self.finance_manager, self.ops_manager)
        self.assertEqual(payment.approval_state, "to_approve_ceo")
        with self.assertRaises(UserError):
            self.post(payment)
        self.assertEqual(payment.state, "draft")
        self.approve(payment, self.ceo)
        self.assertEqual(payment.approval_state, "approved")
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual(payment.approval_state, "posted")
        self.assertEqual(
            payment.approval_ids.mapped("level"), ["finance", "operations", "ceo"]
        )

    def test_req105_t2_threshold_boundary(self):
        """Exactly 50,000 SAR needs no approval; 50,000.01 waits for the Finance Manager."""
        at = self.make_payment(self.valvitalia, 50_000, "INV-VT-2026-0960")
        above = self.make_payment(self.valvitalia, 50_000.01, "INV-VT-2026-0961")
        self.assertEqual(at.approval_state, "approved")
        self.assertEqual(above.approval_state, "to_approve_finance")
        self.post(at)
        self.assertIn(at.state, ("in_process", "paid"))
        with self.assertRaises(UserError):
            self.post(above)

    def test_req105_t3_finance_approval_stored(self):
        """120,000 SAR approved by the Finance Manager posts, with approver and date stored."""
        payment = self.make_payment(self.valvitalia, 120_000, "INV-VT-2026-0970")
        self.approve(payment, self.finance_manager)
        approval = payment.approval_ids
        self.assertEqual(len(approval), 1)
        self.assertEqual(approval.level, "finance")
        self.assertEqual(approval.user_id, self.finance_manager)
        self.assertEqual(str(approval.date)[:10], "2026-10-05")
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))

    def test_req105_t4_duplicate_blocked(self):
        """A second 84,300 SAR payment to Valvitalia for INV-VT-2026-0917 is blocked."""
        first = self._valvitalia_posted()
        second = self.make_payment(self.valvitalia, 84_300, "INV-VT-2026-0917")
        self.assertEqual(second.duplicate_of_id, first)
        self.assertEqual(second.approval_state, "blocked")
        with self.assertRaises(UserError):
            self.approve(second, self.finance_manager)
        with self.assertRaisesRegex(UserError, first.name):
            self.post(second)
        self.assertEqual(second.state, "draft")

    def test_req105_t5_other_reference_not_blocked(self):
        """The same amount to Valvitalia for INV-VT-2026-0918 is not blocked."""
        self._valvitalia_posted()
        other = self.make_payment(self.valvitalia, 84_300, "INV-VT-2026-0918")
        self.assertFalse(other.duplicate_of_id)
        self.assertEqual(other.approval_state, "to_approve_finance")
        self.approve(other, self.finance_manager)
        self.post(other)
        self.assertIn(other.state, ("in_process", "paid"))

    def test_req105_t6_admin_release_logged(self):
        """An administrator reopens the earlier payment; the second proceeds and the release is logged."""
        first = self._valvitalia_posted()
        second = self.make_payment(self.valvitalia, 84_300, "INV-VT-2026-0917")
        second.with_user(self.administrator).action_release_duplicate()
        self.assertTrue(second.is_duplicate_released)
        self.assertEqual(second.approval_state, "to_approve_finance")
        self.approve(second, self.finance_manager)
        self.post(second)
        self.assertIn(second.state, ("in_process", "paid"))
        for payment in first | second:
            bodies = " ".join(payment.message_ids.mapped("body"))
            self.assertIn("Sami Administrator", bodies)
            self.assertIn("released", bodies)

    def test_req105_t7_shareholder_payroll_refused(self):
        """A payment to shareholder Khalid Al Rashid on the salaries account is refused, naming it."""
        payment = self.make_payment(
            self.khalid, 10_000, "DIV-2026-01", destination_account_id=self.salaries.id
        )
        with self.assertRaisesRegex(UserError, "629901"):
            self.post(payment)
        self.assertEqual(payment.state, "draft")

    def test_req105_t8_shareholder_account_posts(self):
        """The same payment on the shareholder current account posts."""
        payment = self.make_payment(
            self.khalid,
            10_000,
            "DIV-2026-01",
            destination_account_id=self.shareholder_account.id,
        )
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual(payment.destination_account_id, self.shareholder_account)

    def test_rule_approval_company(self):
        """An RVK-only approver sees RVK approvals and none of Waterline's."""
        rvk_payment = self.make_payment(self.valvitalia, 60_000, "INV-VT-2026-0980")
        self.approve(rvk_payment, self.finance_manager)
        waterline_payment = (
            self.env["account.payment"]
            .with_company(self.waterline)
            .create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": self.valvitalia.id,
                    "amount": 60_000,
                    "memo": "WL-2026-001",
                    "journal_id": self.waterline_bank.id,
                }
            )
        )
        waterline_approval = self.env["payment.approval"].create(
            {"payment_id": waterline_payment.id, "level": "finance"}
        )
        self.assertEqual(waterline_approval.company_id, self.waterline)
        visible = (
            self.env["payment.approval"]
            .with_user(self.rvk_approver)
            .with_context(allowed_company_ids=[self.rvk.id])
            .search([])
        )
        self.assertIn(rvk_payment.approval_ids, visible)
        self.assertNotIn(waterline_approval, visible)

    def test_access_only_admin_releases_duplicate(self):
        """The Finance Manager cannot release a blocked duplicate."""
        self._valvitalia_posted()
        second = self.make_payment(self.valvitalia, 84_300, "INV-VT-2026-0917")
        with self.assertRaises(AccessError):
            second.with_user(self.finance_manager).action_release_duplicate()
        self.assertFalse(second.is_duplicate_released)

    def test_access_approver_needs_level_group(self):
        """The Operations Manager cannot give the Finance Manager's approval, nor approvals be edited."""
        payment = self.make_payment(self.valvitalia, 250_000, "INV-VT-2026-0990")
        with self.assertRaises(AccessError):
            payment.with_user(self.ops_manager).action_approve()
        self.approve(payment, self.finance_manager)
        with self.assertRaises(AccessError):
            payment.with_user(self.accountant).action_approve()
        with self.assertRaises(AccessError):
            payment.approval_ids.with_user(self.finance_manager).write(
                {"user_id": self.ceo.id}
            )
        self.approve(payment, self.ops_manager)
        self.assertEqual(payment.approval_state, "approved")

    def test_security_untrusted_account_refused(self):
        """A vendor payment to a bank account that is not trusted is refused (REQ-105-T-FR6)."""
        account = self.env["res.partner.bank"].create(
            {
                "acc_number": "SA0380000000608010167519",
                "partner_id": self.valvitalia.id,
                "allow_out_payment": False,
            }
        )
        payment = self.make_payment(
            self.valvitalia, 5_000, "INV-VT-2026-0999", partner_bank_id=account.id
        )
        with self.assertRaises(UserError):
            self.post(payment)
        account.allow_out_payment = True
        self.post(payment)
        self.assertIn(payment.state, ("in_process", "paid"))

    def test_security_shareholder_constraint(self):
        """Writing a posted shareholder payment onto a payroll account is refused (REQ-105-T-C1)."""
        payment = self.make_payment(
            self.khalid,
            10_000,
            "DIV-2026-02",
            destination_account_id=self.shareholder_account.id,
        )
        self.post(payment)
        with self.assertRaises(ValidationError):
            payment.destination_account_id = self.salaries
