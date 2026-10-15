# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Shareholder Contacts (file: models/res_partner.py).

Marks the contacts that are shareholders, so their payments are kept off
payroll expense accounts.
"""

from odoo import fields, models


class ResPartner(models.Model):
    """Contact: the shareholder mark."""

    _inherit = "res.partner"

    is_shareholder = fields.Boolean(
        string="Shareholder",
        help="Payments to this contact can never be posted to a payroll expense "
        "account; they go to the shareholder's account.",
    )
