# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Quotation Send Checks (file: models/sale_order.py).

Extends sale.order so that a quotation is sent only when its payment term is
set and approved, the term's advance meets the company's special-item minimum
when the quotation holds a special item, and sending to a customer on the
credit watch list has been approved. The approvals record who approved and
when.
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_compare

TERM_APPROVER_GROUP = "account.group_account_manager"
SEND_APPROVER_GROUP = "odt_quotation_payment_terms.group_send_approver"
TERM_APPROVAL_FIELDS = ("term_approved_by_id", "term_approval_date")
SEND_APPROVAL_FIELDS = ("send_approved_by_id", "send_approval_date")


class SaleOrder(models.Model):
    """
    Sales Order.

    Checks before a quotation leaves (override of ``action_quotation_send``,
    checks first, then the standard composer):
      - No payment term: refused, naming the missing term.
      - A special line on a term whose advance is below the company's
        special-item minimum: refused, naming the minimum.
      - A term other than the customer's default, not approved by the Finance
        Manager: refused until approved.
      - A customer on the credit watch list, sending not approved by the
        Operations or Finance Manager: refused until approved.
    A term approval lapses when the term or the customer changes; a sending
    approval lapses when the customer changes.
    """

    _inherit = "sale.order"

    term_approved_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Payment Term Approved By",
        readonly=True,
        copy=False,
        tracking=True,
        ondelete="restrict",
        help="Finance Manager who approved a payment term other than the "
        "customer's default on this quotation.",
    )
    term_approval_date = fields.Datetime(
        string="Payment Term Approval Date",
        readonly=True,
        copy=False,
        help="When the payment term was approved.",
    )
    send_approved_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Sending Approved By",
        readonly=True,
        copy=False,
        tracking=True,
        ondelete="restrict",
        help="Operations or Finance Manager who approved sending this quotation to "
        "a customer on the credit watch list.",
    )
    send_approval_date = fields.Datetime(
        string="Sending Approval Date",
        readonly=True,
        copy=False,
        help="When sending to the watch-listed customer was approved.",
    )
    is_term_approval_needed = fields.Boolean(
        string="Payment Term Needs Approval",
        compute="_compute_is_term_approval_needed",
        help="The quotation's payment term is not the customer's default and the "
        "Finance Manager has not approved it yet.",
    )
    is_send_approval_needed = fields.Boolean(
        string="Sending Needs Approval",
        compute="_compute_is_send_approval_needed",
        help="The customer is on the credit watch list and sending the quotation "
        "has not been approved yet.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends(
        "state",
        "payment_term_id",
        "partner_id",
        "company_id",
        "term_approved_by_id",
    )
    def _compute_is_term_approval_needed(self):
        """
        Flag quotations on a term other than the customer's default, not approved.

        The default is the customer's payment term in the quotation's company.
        A quotation without a term is not flagged: the missing term is refused
        on its own.
        """
        for order in self:
            order.is_term_approval_needed = bool(
                order._is_quotation()
                and order.payment_term_id
                and not order.term_approved_by_id
                and order.payment_term_id != order._default_payment_term()
            )

    @api.depends(
        "state",
        "partner_id.commercial_partner_id.credit_state",
        "send_approved_by_id",
    )
    def _compute_is_send_approval_needed(self):
        """Flag quotations to a watch-listed customer whose sending is not approved."""
        for order in self:
            order.is_send_approval_needed = bool(
                order._is_quotation()
                and order.partner_id.commercial_partner_id.credit_state == "watch"
                and not order.send_approved_by_id
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def write(self, vals):
        """
        Guard the approvals and let them lapse when what they approved changes.

        Approval fields are written by the approval actions only (they check
        the right, then write with ``sudo()``); a direct write of an approval by
        a user without the right is refused. Changing the payment term clears
        the term approval; changing the customer clears both approvals.

        :raises AccessError: if a user without the right writes an approval
        """
        if not self.env.su:
            if any(vals.get(name) for name in TERM_APPROVAL_FIELDS):
                self._check_approval_right(TERM_APPROVER_GROUP)
            if any(vals.get(name) for name in SEND_APPROVAL_FIELDS):
                self._check_approval_right(SEND_APPROVER_GROUP)
        lapse_term = lapse_send = self.browse()
        if "payment_term_id" in vals:
            lapse_term |= self.filtered(
                lambda o: o.payment_term_id.id != (vals["payment_term_id"] or False)
            )
        if "partner_id" in vals:
            moved = self.filtered(
                lambda o: o.partner_id.id != (vals["partner_id"] or False)
            )
            lapse_term |= moved
            lapse_send |= moved
        result = super().write(vals)
        lapse_term = lapse_term.filtered("term_approved_by_id")
        lapse_send = lapse_send.filtered("send_approved_by_id")
        if lapse_term:
            # Clearing an approval needs no right: it only makes the check strict again.
            lapse_term.sudo().write(dict.fromkeys(TERM_APPROVAL_FIELDS, False))
        if lapse_send:
            # Same reason: clearing only makes the watch-list check strict again.
            lapse_send.sudo().write(dict.fromkeys(SEND_APPROVAL_FIELDS, False))
        return result

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_quotation_send(self):
        """
        Open the email composer for quotations that pass the send checks (override).

        The checks run first on the quotations; the standard method then runs
        unchanged, so an approved term and a normal customer send exactly as
        standard. Confirmed orders (order confirmation emails) are not checked.

        :return: the standard composer action
        :raises UserError: if a quotation fails a check (see the class docstring)
        """
        self._check_quotation_send()
        return super().action_quotation_send()

    def action_approve_payment_term(self):
        """
        Approve the quotations' payment term, recording the approver and the date.

        Only the Finance Manager approves, and only a term that needs approval.

        :raises AccessError: if the user is not a Finance Manager
        :raises UserError: if a quotation's term does not need approval
        """
        self._check_approval_right(TERM_APPROVER_GROUP)
        for order in self:
            if not order.is_term_approval_needed:
                raise UserError(
                    self.env._("%s does not need a payment term approval.", order.name)
                )
        # Right checked above; the Finance Manager need not hold sales rights.
        self.sudo().write(
            {
                "term_approved_by_id": self.env.user.id,
                "term_approval_date": fields.Datetime.now(),
            }
        )
        return True

    def action_approve_sending(self):
        """
        Approve sending the quotations to a watch-listed customer.

        Only the Operations Manager and the Finance Manager (the send approver
        group) approve; the approver and the date are recorded.

        :raises AccessError: if the user is not a send approver
        :raises UserError: if a quotation does not need the approval
        """
        self._check_approval_right(SEND_APPROVER_GROUP)
        for order in self:
            if not order.is_send_approval_needed:
                raise UserError(
                    self.env._("%s does not need a sending approval.", order.name)
                )
        # Right checked above; approvers need not own the quotation.
        self.sudo().write(
            {
                "send_approved_by_id": self.env.user.id,
                "send_approval_date": fields.Datetime.now(),
            }
        )
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_quotation(self):
        """Return whether the order is still a quotation (draft or sent)."""
        self.ensure_one()
        return self.state in ("draft", "sent")

    def _default_payment_term(self):
        """
        Return the customer's default payment term in the quotation's company.

        :return: an account.payment.term record, possibly empty
        """
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id.with_company(self.company_id)
        return partner.property_payment_term_id

    def _check_approval_right(self, group):
        """
        Refuse the approval to users outside the group.

        :param str group: xml id of the group that may approve
        :raises AccessError: if the user is not in the group
        """
        if self.env.user.has_group(group):
            return
        if group == TERM_APPROVER_GROUP:
            message = self.env._(
                "Only the Finance Manager can approve a quotation's payment term."
            )
        else:
            message = self.env._(
                "Only the Operations Manager or the Finance Manager can approve "
                "sending a quotation to a customer on the credit watch list."
            )
        raise AccessError(message)

    def _check_quotation_send(self):
        """
        Refuse to send quotations that fail a send check.

        The checks run in this order, the first failing one is reported: the
        payment term is set; the special-item minimum advance is met; the term
        is the customer's default or approved; sending to a watch-listed
        customer is approved.

        :raises UserError: naming the quotation and what is missing
        """
        for order in self.filtered(lambda o: o._is_quotation()):
            term = order.payment_term_id
            if not term:
                raise UserError(
                    self.env._(
                        "%s has no payment term: select the payment term agreed with "
                        "the customer before sending the quotation.",
                        order.name,
                    )
                )
            minimum = order.company_id.special_min_advance
            has_special = any(
                line.is_special for line in order.order_line if not line.display_type
            )
            if (
                has_special
                and minimum
                and float_compare(term.advance_pct, minimum, precision_digits=2) < 0
            ):
                raise UserError(
                    self.env._(
                        "%(order)s holds special items, which need a payment term "
                        "with at least %(minimum)s%% advance; %(term)s has "
                        "%(advance)s%%. Choose a term with at least %(minimum)s%% "
                        "advance.",
                        order=order.name,
                        minimum="%g" % minimum,
                        term=term.display_name,
                        advance="%g" % term.advance_pct,
                    )
                )
            if order.is_term_approval_needed:
                raise UserError(
                    self.env._(
                        "%(order)s is on %(term)s, which is not the customer's default "
                        "payment term: the Finance Manager must approve it on the "
                        "quotation before it is sent.",
                        order=order.name,
                        term=term.display_name,
                    )
                )
            if order.is_send_approval_needed:
                raise UserError(
                    self.env._(
                        "%(customer)s is on the credit watch list: the Operations "
                        "Manager or the Finance Manager must approve sending "
                        "%(order)s.",
                        customer=order.partner_id.commercial_partner_id.display_name,
                        order=order.name,
                    )
                )
