# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Delivery Credit Block (file: models/stock_picking.py).

Extends stock.picking so that a delivery to a customer on credit hold or
absolute block cannot be validated. Receipts and internal transfers are not
affected, even when the partner is also a held customer.
"""

from odoo import models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    """
    Transfer.

    Validation of an outgoing delivery checks the customer's credit state
    first (override of ``button_validate``, checks first, then the standard
    validation).
    """

    _inherit = "stock.picking"

    def button_validate(self):
        """
        Refuse deliveries to held or blocked customers, then validate as standard.

        :return: the standard result (True or a wizard action)
        :raises UserError: if an outgoing delivery's customer is on hold or block
        """
        for picking in self:
            partner = picking.partner_id.commercial_partner_id
            if picking.picking_type_code == "outgoing" and partner.credit_state in (
                "hold",
                "block",
            ):
                raise UserError(
                    self.env._(
                        "%(picking)s cannot be validated: %(customer)s is on credit hold "
                        "or block until the Finance Manager releases the customer.",
                        picking=picking.name,
                        customer=partner.display_name,
                    )
                )
        return super().button_validate()
