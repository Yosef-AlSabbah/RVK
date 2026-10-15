# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Payroll Expense Accounts (file: models/account_account.py).

Marks the expense accounts that hold payroll, so a payment to a shareholder
can never be posted to them.
"""

from odoo import fields, models


class AccountAccount(models.Model):
    """Account: the payroll expense mark."""

    _inherit = "account.account"

    is_payroll = fields.Boolean(
        string="Payroll Expense Account",
        help="Salaries and other payroll expenses. A payment to a contact marked "
        "shareholder cannot be posted to this account.",
    )
