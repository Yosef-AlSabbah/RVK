# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Payment Approval (file: models/payment_approval.py).

One approval given on an outgoing vendor payment at one level (Finance
Manager, Operations Manager or Chief Executive), with the approver and the
date. Approvals are created by the payment's Approve button and are never
edited or deleted: no group has write or delete access.
"""

from odoo import fields, models

from .account_payment import APPROVAL_LEVELS


class PaymentApproval(models.Model):
    """An approval given on a vendor payment at one level."""

    _name = "payment.approval"
    _description = "Payment approval"
    _order = "date, id"
    _rec_name = "payment_id"

    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Payment",
        required=True,
        index=True,
        ondelete="cascade",
        help="The vendor payment approved; its approvals go with it.",
    )
    level = fields.Selection(
        selection=APPROVAL_LEVELS,
        string="Level",
        required=True,
        help="The approval level given: above the company's first, second or "
        "third threshold.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Approver",
        required=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
        help="The user who gave the approval.",
    )
    date = fields.Datetime(
        string="Approval Date",
        required=True,
        default=fields.Datetime.now,
        help="When the approval was given.",
    )
    company_id = fields.Many2one(
        related="payment_id.company_id",
        string="Company",
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="payment_id.currency_id",
        string="Currency",
    )
    amount = fields.Monetary(
        related="payment_id.amount",
        string="Amount",
        currency_field="currency_id",
        help="The amount of the payment approved.",
    )
    partner_id = fields.Many2one(
        related="payment_id.partner_id",
        string="Vendor",
        help="The vendor paid.",
    )
