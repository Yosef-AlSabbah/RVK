# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Bill Payment Block (file: models/account_move.py).

Tells whether a vendor bill may be paid: its Should Be Paid (three-way match
of the Vendor Bill: Release to Pay app) must be Yes, unless it is a service
bill raised without a purchase order. The packing list and weight certificate
of an import shipment are kept as standard attachments on the bill.
"""

from odoo import models


class AccountMove(models.Model):
    """Journal entry: whether a vendor bill is cleared to pay."""

    _inherit = "account.move"

    def _is_service_bill_without_order(self):
        """
        Return whether this bill is a service bill raised without a purchase order.

        :return: True when no line comes from a purchase order and every product
            line is a service
        """
        self.ensure_one()
        lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        return (
            bool(lines)
            and not lines.purchase_line_id
            and all(line.product_id.type == "service" for line in lines)
        )

    def _is_payment_blocked(self):
        """
        Return whether paying this move is refused.

        :return: True for a vendor bill whose Should Be Paid is not Yes and
            that is not a service bill without a purchase order
        """
        self.ensure_one()
        return (
            self.move_type == "in_invoice"
            and self.release_to_pay != "yes"
            and not self._is_service_bill_without_order()
        )
