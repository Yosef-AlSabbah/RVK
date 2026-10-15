# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Sale Order Credit Check (file: models/sale_order.py).

Extends sale.order so that confirming a credit order checks the customer's
monthly cap and the company's monthly ceiling first: an order that would
exceed either waits for the Finance Manager's approval, and customers on
credit hold or absolute block cannot confirm at all. Quotations cannot be
saved for a customer under absolute block.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SaleOrder(models.Model):
    """
    Sales Order.

    Credit rules at confirmation (override of ``action_confirm``, checks first,
    then the standard confirmation):
      - Customer on credit hold or absolute block: refused.
      - Credit order (payment term not full advance) that would take the
        customer's credit sales of the month above its cap, or the company's
        above its ceiling: left unconfirmed, waiting for approval.
      - An order the Finance Manager approved, or one landing exactly on a
        limit, confirms as standard.
    """

    _inherit = "sale.order"

    _credit_company_date_idx = models.Index(
        "(company_id, date_order) WHERE state = 'sale'"
    )

    credit_approval = fields.Selection(
        selection=[
            ("none", "Not Needed"),
            ("pending", "Waiting for Approval"),
            ("approved", "Approved"),
        ],
        string="Credit Approval",
        default="none",
        required=True,
        copy=False,
        tracking=True,
        help="Waiting for Approval: confirming the order would exceed the customer's "
        "monthly cap or the company's monthly ceiling, so the Finance Manager must "
        "approve it first.",
    )
    credit_approval_note = fields.Char(
        string="Credit Approval Reason",
        copy=False,
        help="Why the Finance Manager approved the order over the credit limit.",
    )
    credit_approved_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Credit Approved By",
        readonly=True,
        copy=False,
        ondelete="restrict",
        help="Finance Manager who approved the order over the credit limit.",
    )
    credit_approval_date = fields.Datetime(
        string="Credit Approval Date",
        readonly=True,
        copy=False,
        help="When the order was approved over the credit limit.",
    )
    credit_share_pct = fields.Float(
        string="Customer Credit Share (%)",
        compute="_compute_credit_share_pct",
        help="The customer's credit sales of the current month as a share of the "
        "company's monthly ceiling.",
    )
    credit_cap_pct = fields.Float(
        string="Customer Credit Cap (%)",
        related="partner_id.commercial_partner_id.credit_cap_pct",
        help="The customer's monthly cap, as a share of the company's ceiling.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("partner_id", "company_id")
    def _compute_credit_share_pct(self):
        """
        Compute the customer's share of the company ceiling this month.

        Read from the credit.exposure view, the same source as the exposure
        report, so the quotation and the report always agree.
        """
        month = fields.Datetime.now().date().replace(day=1)
        partners = self.partner_id.commercial_partner_id
        exposure = self.env["credit.exposure"]
        exposure.invalidate_model()
        lines = (
            # read-only totals of the orders' own customers and companies
            exposure.sudo().search(
                [
                    ("partner_id", "in", partners.ids),
                    ("company_id", "in", self.company_id.ids),
                    ("month", "=", month),
                ]
            )
            if partners
            else exposure
        )
        shares = {
            (line.partner_id.id, line.company_id.id): line.share_pct for line in lines
        }
        for order in self:
            key = (order.partner_id.commercial_partner_id.id, order.company_id.id)
            order.credit_share_pct = shares.get(key, 0.0)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains("partner_id")
    def _check_partner_credit_block(self):
        """
        Refuse a quotation for a customer under absolute block.

        :raises ValidationError: if a draft or sent order's customer is blocked
        """
        for order in self:
            partner = order.partner_id.commercial_partner_id
            if order.state in ("draft", "sent") and partner.credit_state == "block":
                raise ValidationError(
                    self.env._(
                        "%s is under an absolute credit block: no quotation can be "
                        "made for this customer.",
                        partner.display_name,
                    )
                )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_confirm(self):
        """
        Confirm the orders that pass the credit checks (override, checks first).

        Orders that need approval are marked waiting and are not confirmed;
        the standard confirmation then runs for the others. When some orders
        wait, a notification says so instead of the standard return value.

        :return: True, or a notification action when an order waits for approval
        :raises UserError: if a customer is on credit hold or absolute block
        """
        for order in self:
            partner = order.partner_id.commercial_partner_id
            if partner.credit_state in ("hold", "block"):
                raise UserError(
                    self.env._(
                        "%(customer)s is on %(state)s: the order cannot be confirmed "
                        "until the Finance Manager releases the customer.",
                        customer=partner.display_name,
                        state=dict(
                            partner._fields["credit_state"]._description_selection(
                                self.env
                            )
                        )[partner.credit_state],
                    )
                )
        waiting = self.filtered(lambda o: o._needs_credit_approval())
        if waiting:
            waiting.write({"credit_approval": "pending"})
            for order in waiting:
                order.message_post(
                    body=self.env._(
                        "Confirmation waits for credit approval: the order would exceed "
                        "the customer's monthly cap or the company's monthly ceiling."
                    )
                )
        to_confirm = self - waiting
        result = super(SaleOrder, to_confirm).action_confirm() if to_confirm else True
        if not waiting:
            return result
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "sticky": True,
                "title": self.env._("Credit approval needed"),
                "message": self.env._(
                    "%s waits for the Finance Manager's credit approval.",
                    ", ".join(waiting.mapped("name")),
                ),
            },
        }

    def action_credit_approve(self, reason):
        """
        Approve orders waiting for credit approval and confirm them.

        Only the Finance Manager approves, and a reason is required; the
        approver, the date and the reason are recorded on the order.

        :param str reason: why the orders are approved over the limit (required)
        :raises AccessError: if the user is not a Finance Manager
        :raises UserError: if an order is not waiting or no reason is given
        """
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(
                self.env._(
                    "Only the Finance Manager can approve an order over a credit limit."
                )
            )
        if not (reason or "").strip():
            raise UserError(
                self.env._("Give the reason for approving over the credit limit.")
            )
        for order in self:
            if order.credit_approval != "pending":
                raise UserError(
                    self.env._("%s is not waiting for credit approval.", order.name)
                )
        # Rights checked above; the Finance Manager need not hold sales rights to approve.
        orders = self.sudo()
        orders.write(
            {
                "credit_approval": "approved",
                "credit_approval_note": reason.strip(),
                "credit_approved_by_id": self.env.user.id,
                "credit_approval_date": fields.Datetime.now(),
            }
        )
        return orders.action_confirm()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_credit_sale(self):
        """Return whether the order is a credit sale: its term is not full advance."""
        self.ensure_one()
        return (self.payment_term_id.advance_pct or 0.0) < 100.0

    def _credit_amount(self):
        """
        Return the order's credit amount in the company currency.

        The total with VAT of its lines, without down payments and without lines
        of special products excluded from credit.

        :rtype: float
        """
        self.ensure_one()
        lines = self.order_line.filtered(
            lambda line: not line.display_type
            and not line.is_downpayment
            and not (line.product_id.is_special and line.product_id.is_credit_excluded)
        )
        rate = self.currency_rate or 1.0
        return sum(lines.mapped("price_total")) / rate

    def _needs_credit_approval(self):
        """
        Return whether confirming the order would exceed a credit limit.

        Approved orders and non-credit sales never need approval. The month is
        the month of confirmation; totals come from the credit.exposure view.

        :rtype: bool
        """
        self.ensure_one()
        if self.credit_approval == "approved" or not self._is_credit_sale():
            return False
        company = self.company_id
        ceiling = company.credit_ceiling
        partner = self.partner_id.commercial_partner_id
        cap = ceiling * partner.credit_cap_pct / 100.0
        if not ceiling:
            return False
        self.env.flush_all()
        self.env["credit.exposure"].invalidate_model()
        month = fields.Datetime.now().date().replace(day=1)
        lines = (
            self.env["credit.exposure"]
            .sudo()  # company-wide totals are needed whatever the user can read
            .search([("company_id", "=", company.id), ("month", "=", month)])
        )
        company_total = sum(lines.mapped("credit_sales"))
        customer_total = sum(
            lines.filtered(lambda line: line.partner_id == partner).mapped(
                "credit_sales"
            )
        )
        amount = self._credit_amount()
        currency = company.currency_id
        over_ceiling = currency.compare_amounts(company_total + amount, ceiling) > 0
        over_cap = (
            bool(cap) and currency.compare_amounts(customer_total + amount, cap) > 0
        )
        return over_ceiling or over_cap
