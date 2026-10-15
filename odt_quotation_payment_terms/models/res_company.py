# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Company Special-Item Advance (file: models/res_company.py).

Adds to res.company the minimum advance a quotation's payment term must carry
when the quotation holds a special item. Each company sets its own minimum,
as the credit policy sets the percentages per company.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    """
    Company.

    Carries the special-item minimum advance of one company:
      - A quotation with a special line is sent only on a payment term whose
        advance is at least this share.
      - 0 means no minimum.
    """

    _inherit = "res.company"

    special_min_advance = fields.Float(
        string="Special Items Minimum Advance (%)",
        digits=(5, 2),
        help="Smallest advance, from 0 to 100%, a payment term must carry for a "
        "quotation holding a special item to be sent. 0 means no minimum.",
    )

    @api.constrains("special_min_advance")
    def _check_special_min_advance(self):
        """
        Keep the special-item minimum advance between 0 and 100.

        :raises ValidationError: if the minimum is below 0 or above 100
        """
        for company in self:
            if not 0 <= company.special_min_advance <= 100:
                raise ValidationError(
                    self.env._(
                        "The special items minimum advance is between 0 and 100%."
                    )
                )
