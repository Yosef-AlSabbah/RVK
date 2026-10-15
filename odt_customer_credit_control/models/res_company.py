# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Company Credit Settings (file: models/res_company.py).

Adds to res.company the monthly credit ceiling that caps the company's credit
sales, and the number of overdue days after which a customer goes on credit
hold. Each company keeps its own values, so RVK and Waterline stay apart.
"""

from odoo import fields, models


class ResCompany(models.Model):
    """
    Company.

    Carries the credit policy of one company:
      - Monthly credit ceiling: the most credit sales the company takes in a
        calendar month; 0 means no ceiling.
      - Hold days: a customer goes on credit hold once any invoice is overdue
        by more than this many days.
    """

    _inherit = "res.company"

    credit_ceiling = fields.Monetary(
        string="Monthly Credit Ceiling",
        currency_field="currency_id",
        help="Most credit sales the company accepts in one calendar month, in the "
        "company currency. Each customer's cap is a share of it. 0 means no ceiling.",
    )
    hold_days = fields.Integer(
        string="Credit Hold After (Days Overdue)",
        default=60,
        help="The nightly credit check puts a customer on credit hold once any of "
        "its invoices is overdue by more than this many days.",
    )
