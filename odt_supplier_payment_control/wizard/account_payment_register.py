# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Register Payment Block (file: wizard/account_payment_register.py).

Extends the Register Payment dialog so that vendor bills not cleared to pay
cannot be paid, and so that payments needing approval are created and left
for the approvers instead of failing the registration.
"""

from odoo import models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    """
    Register Payment.

    Creating the payments checks the bills first (override of
    action_create_payments, checks first, then the standard creation).
    """

    _inherit = "account.payment.register"

    def action_create_payments(self):
        """
        Refuse bills not cleared to pay, then create the payments as standard.

        Payments that wait for an approval or a duplicate release are created
        in draft and left for the approvers (context defer_payment_approval,
        read by account.payment.action_post).

        :return: the standard result (the payments' action, or True)
        :raises UserError: naming every bill whose Should Be Paid is not Yes
        """
        bills = self.line_ids.move_id.filtered(lambda move: move._is_payment_blocked())
        if bills:
            raise UserError(
                self.env._(
                    "These bills cannot be paid because they are not matched to their "
                    "purchase order and receipt (Should Be Paid is not Yes): "
                    "%(bills)s. The Finance Manager can release a bill by setting it "
                    "to Yes.",
                    bills=", ".join(bills.mapped("name")),
                )
            )
        return super(
            AccountPaymentRegister, self.with_context(defer_payment_approval=True)
        ).action_create_payments()
