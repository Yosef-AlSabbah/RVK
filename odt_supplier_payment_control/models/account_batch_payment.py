# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Batch Payment Block (file: models/account_batch_payment.py).

Extends account.batch.payment so that an outgoing batch holding a payment
for a bill that is not cleared to pay cannot be validated, naming that bill.
Incoming batches are not affected.
"""

from odoo import models
from odoo.exceptions import UserError


class AccountBatchPayment(models.Model):
    """
    Batch Payment.

    Validation of an outgoing batch checks the bills of its payments first
    (override of validate_batch, checks first, then the standard
    validation).
    """

    _inherit = "account.batch.payment"

    def validate_batch(self):
        """
        Refuse an outgoing batch holding a bill not cleared to pay, then validate as standard.

        :return: the standard result (an error wizard, an export action or None)
        :raises UserError: naming every blocked bill of the batch
        """
        for batch in self.filtered(lambda b: b.batch_type == "outbound"):
            payments = batch.payment_ids
            bills = (payments.invoice_ids | payments.reconciled_bill_ids).filtered(
                lambda move: move._is_payment_blocked()
            )
            if bills:
                raise UserError(
                    self.env._(
                        "%(batch)s cannot be validated: these bills are not cleared to "
                        "pay (Should Be Paid is not Yes): %(bills)s.",
                        batch=batch.display_name,
                        bills=", ".join(bills.mapped("name")),
                    )
                )
        return super().validate_batch()
