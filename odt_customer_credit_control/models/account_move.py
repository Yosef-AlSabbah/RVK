# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Invoice Credit Block (file: models/account_move.py).

Extends account.move so that a customer invoice of a customer under absolute
block cannot be posted. Vendor bills, refunds and other entries are not
affected.
"""

from odoo import models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """
    Journal Entry.

    Posting checks the customer's credit state first for customer invoices
    (override of ``action_post``, checks first, then the standard posting).
    """

    _inherit = "account.move"

    def action_post(self):
        """
        Refuse customer invoices of blocked customers, then post as standard.

        :return: the standard result
        :raises UserError: if a customer invoice's customer is under absolute block
        """
        for move in self:
            if (
                move.move_type == "out_invoice"
                and move.commercial_partner_id.credit_state == "block"
            ):
                raise UserError(
                    self.env._(
                        "%(invoice)s cannot be posted: %(customer)s is under an absolute "
                        "credit block.",
                        invoice=move.display_name,
                        customer=move.commercial_partner_id.display_name,
                    )
                )
        return super().action_post()
