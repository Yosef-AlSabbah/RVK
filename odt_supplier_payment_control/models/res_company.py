# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Company Approval Thresholds (file: models/res_company.py).

Each company keeps the three amounts above which an outgoing vendor payment
needs the Finance Manager, also the Operations Manager, and also the Chief
Executive. A threshold of 0 leaves its level unused.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    """Company: the three vendor payment approval thresholds."""

    _inherit = "res.company"

    approval_threshold_1 = fields.Monetary(
        string="Finance Manager Approval Above",
        currency_field="currency_id",
        help="Vendor payments above this amount, in company currency, need the "
        "Finance Manager's approval. 0 = no approval at this level.",
    )
    approval_threshold_2 = fields.Monetary(
        string="Operations Manager Approval Above",
        currency_field="currency_id",
        help="Vendor payments above this amount also need the Operations "
        "Manager's approval. 0 = no approval at this level.",
    )
    approval_threshold_3 = fields.Monetary(
        string="Chief Executive Approval Above",
        currency_field="currency_id",
        help="Vendor payments above this amount also need the Chief Executive's "
        "approval. 0 = no approval at this level.",
    )

    @api.constrains(
        "approval_threshold_1", "approval_threshold_2", "approval_threshold_3"
    )
    def _check_approval_thresholds(self):
        """
        Keep the thresholds that are set rising from level 1 to level 3.

        :raises ValidationError: a threshold is negative, or a set threshold is
            not above the set threshold of a lower level
        """
        for company in self:
            thresholds = [
                company.approval_threshold_1,
                company.approval_threshold_2,
                company.approval_threshold_3,
            ]
            if any(amount < 0 for amount in thresholds):
                raise ValidationError(
                    self.env._("Approval thresholds cannot be negative.")
                )
            used = [amount for amount in thresholds if amount]
            if used != sorted(set(used)):
                raise ValidationError(
                    self.env._(
                        "Each approval threshold must be above the one of the level "
                        "before it."
                    )
                )
