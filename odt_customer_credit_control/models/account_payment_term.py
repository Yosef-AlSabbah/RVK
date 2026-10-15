# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Payment Term Advance (file: models/account_payment_term.py).

Adds to account.payment.term the share of an order paid in advance. An order
on a term with a 100% advance is not a credit sale and never counts against
the monthly credit ceiling.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountPaymentTerm(models.Model):
    """
    Payment Term.

    Declares how much of an order is paid before delivery:
      - 100% means full advance: orders on the term are not credit sales.
      - Anything less makes them credit sales for the credit ceiling.
    """

    _inherit = "account.payment.term"

    advance_pct = fields.Float(
        string="Advance (%)",
        digits=(5, 2),
        help="Share of the order paid in advance, from 0 to 100. At 100 the order is "
        "paid in full before delivery and is not counted as a credit sale.",
    )

    @api.constrains("advance_pct")
    def _check_advance_pct(self):
        """
        Keep the advance share between 0 and 100.

        :raises ValidationError: if the advance is below 0 or above 100
        """
        for term in self:
            if not 0 <= term.advance_pct <= 100:
                raise ValidationError(
                    self.env._("The advance of a payment term is between 0 and 100%.")
                )
