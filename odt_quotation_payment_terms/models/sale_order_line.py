# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Sales Order Line Special Marking (file: models/sale_order_line.py).

Shows on quotation and order lines the special marking held on the product,
so the special item is visible wherever the line is read.
"""

from odoo import fields, models


class SaleOrderLine(models.Model):
    """
    Sales Order Line.

    The special marking is read from the product, never typed on the line:
    marking or unmarking the product changes every line that shows it.
    """

    _inherit = "sale.order.line"

    is_special = fields.Boolean(
        string="Special Item",
        related="product_id.is_special",
        help="The product is a special item: its quotation needs the company's "
        "special-item minimum advance.",
    )
