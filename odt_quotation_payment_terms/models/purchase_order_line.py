# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Purchase Order Line Special Marking (file: models/purchase_order_line.py).

Shows on purchase order lines the special marking held on the product, so a
purchase raised for a special sales line carries the marking down the chain.
"""

from odoo import fields, models


class PurchaseOrderLine(models.Model):
    """
    Purchase Order Line.

    The special marking is read from the product, never typed on the line.
    """

    _inherit = "purchase.order.line"

    is_special = fields.Boolean(
        string="Special Item",
        related="product_id.is_special",
        help="The product is a special item, as on the sales order line the "
        "purchase was raised for.",
    )
