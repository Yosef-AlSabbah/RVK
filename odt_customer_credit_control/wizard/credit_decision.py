# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Credit Decision Dialog (file: wizard/credit_decision.py).

Defines credit.decision, the dialog Finance uses to change a customer's
credit state or to approve an order over a credit limit, always with a
reason. Finance users cannot edit contacts or orders in Odoo 19, so the
reason is captured here and passed to the action, which checks the user's
right itself.
"""

from odoo import api, fields, models

DECISIONS = [
    ("flag", "Put on Watch List"),
    ("unflag", "Remove Finance Flag"),
    ("hold", "Put on Credit Hold"),
    ("lift_hold", "Lift Credit Hold"),
    ("block", "Absolute Block"),
    ("unblock", "Lift Absolute Block"),
    ("approve", "Approve over Credit Limit"),
]
PARTNER_ACTIONS = {
    "flag": "action_credit_flag",
    "unflag": "action_credit_unflag",
    "hold": "action_credit_hold",
    "lift_hold": "action_credit_lift_hold",
    "block": "action_credit_block",
    "unblock": "action_credit_unblock",
}


class CreditDecision(models.TransientModel):
    """
    Credit Decision.

    One decision with its reason, applied to the customers or orders the
    dialog was opened from. The right to take it is checked by the action
    it runs, not here.
    """

    _name = "credit.decision"
    _description = "Credit Decision"

    decision = fields.Selection(
        selection=DECISIONS,
        string="Decision",
        required=True,
        help="What is decided for the selected customers or orders.",
    )
    reason = fields.Char(
        string="Reason",
        required=True,
        help="Why; recorded on the customer or the order.",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Customers",
        help="Customers whose credit state changes.",
    )
    order_ids = fields.Many2many(
        comodel_name="sale.order",
        string="Orders",
        help="Orders approved over the credit limit.",
    )

    @api.model
    def default_get(self, fields_list):
        """Fill the customers or orders from the records the dialog was opened on."""
        values = super().default_get(fields_list)
        model = self.env.context.get("active_model")
        ids = self.env.context.get("active_ids") or []
        if model == "res.partner" and "partner_ids" in fields_list:
            values["partner_ids"] = [fields.Command.set(ids)]
        if model == "sale.order" and "order_ids" in fields_list:
            values["order_ids"] = [fields.Command.set(ids)]
        return values

    def action_apply(self):
        """
        Apply the decision with its reason.

        :return: the action of the order approval, or a closing action
        """
        self.ensure_one()
        if self.decision == "approve":
            result = self.order_ids.action_credit_approve(self.reason)
            return (
                result
                if isinstance(result, dict)
                else {"type": "ir.actions.act_window_close"}
            )
        getattr(self.partner_ids, PARTNER_ACTIONS[self.decision])(self.reason)
        return {"type": "ir.actions.act_window_close"}
