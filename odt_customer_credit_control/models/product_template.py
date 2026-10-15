# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Product Credit Marks (file: models/product_template.py).

Adds to product.template the special-item mark and the flag that leaves a
special item out of the monthly credit totals.
"""

from odoo import fields, models


class ProductTemplate(models.Model):
    """
    Product Template.

    A product can be marked special, and a special product can be excluded
    from the credit totals: order lines of a product that is both special and
    excluded do not count as credit sales.
    """

    _inherit = "product.template"

    is_special = fields.Boolean(
        string="Special Item",
        help="Marks the product as a special item under the company's sales policy.",
    )
    is_credit_excluded = fields.Boolean(
        string="Excluded from Credit Totals",
        help="When the product is also a special item, its order lines are left out "
        "of the customer's and the company's monthly credit sales.",
    )
