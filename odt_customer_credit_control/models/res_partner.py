# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Customer Credit State (file: models/res_partner.py).

Adds to res.partner the customer's credit state (normal, watch list, credit
hold, absolute block), its monthly credit cap, the actions Finance uses to
change the state, the nightly credit check and the weekly watch-list email.
"""

import logging

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

CREDIT_STATES = [
    ("normal", "Normal"),
    ("watch", "Watch List"),
    ("hold", "Credit Hold"),
    ("block", "Absolute Block"),
]
MANAGER_FIELDS = {"credit_state", "credit_cap_pct", "hold_cleared_invoice_ids"}
FINANCE_FIELDS = {"is_credit_flagged", "credit_state_reason"}
MANAGER_GROUP = "account.group_account_manager"
FINANCE_GROUP = "account.group_account_invoice"


class ResPartner(models.Model):
    """
    Partner.

    Credit state of a customer:
      - Watch List: an overdue invoice (set and cleared by the nightly check) or
        a flag Finance sets by hand with a reason.
      - Credit Hold: set nightly once an invoice is more than the company's hold
        days overdue, or by the Finance Manager; only the Finance Manager lifts
        it, and a lifted hold is not set again for the same invoices.
      - Absolute Block: set and lifted by the Finance Manager only.
    The state and the cap change only through these rules: the write check
    refuses anyone else.
    """

    _inherit = "res.partner"

    credit_state = fields.Selection(
        selection=CREDIT_STATES,
        string="Credit State",
        default="normal",
        required=True,
        copy=False,
        tracking=True,
        help="Normal; Watch List (an overdue invoice or a flag by Finance); Credit "
        "Hold (no new orders or deliveries); Absolute Block (no quotations, orders, "
        "deliveries or invoices).",
    )
    credit_cap_pct = fields.Float(
        string="Monthly Credit Cap (%)",
        digits=(5, 2),
        help="Most credit sales this customer may take in a calendar month, as a share "
        "of the selling company's monthly credit ceiling. 0 means no cap.",
    )
    is_credit_flagged = fields.Boolean(
        string="Flagged by Finance",
        copy=False,
        help="Set by Finance for an open dispute or an order problem; keeps the "
        "customer on the watch list until Finance removes it.",
    )
    credit_state_reason = fields.Char(
        string="Credit State Reason",
        copy=False,
        help="Why Finance flagged the customer, or put it on hold or block, or lifted "
        "the hold.",
    )
    hold_cleared_invoice_ids = fields.Many2many(
        comodel_name="account.move",
        relation="res_partner_hold_cleared_move_rel",
        column1="partner_id",
        column2="move_id",
        string="Invoices Covered by a Lifted Hold",
        copy=False,
        help="Overdue invoices the Finance Manager accepted when lifting a credit "
        "hold; they do not set the hold again. Paid invoices drop out nightly.",
    )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def write(self, vals):
        """
        Refuse credit changes by users without the right.

        The credit state, the cap and the covered invoices change only for the
        Finance Manager or the system (the nightly check); the flag and the
        reason also for Finance.

        :raises AccessError: if the user may not change a credit field written
        """
        if not self.env.su and vals.keys() & (MANAGER_FIELDS | FINANCE_FIELDS):
            user = self.env.user
            if vals.keys() & MANAGER_FIELDS and not user.has_group(MANAGER_GROUP):
                raise AccessError(
                    self.env._(
                        "Only the Finance Manager can change a customer's credit state or cap."
                    )
                )
            if not (user.has_group(MANAGER_GROUP) or user.has_group(FINANCE_GROUP)):
                raise AccessError(
                    self.env._("Only Finance can flag a customer for credit.")
                )
        return super().write(vals)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_credit_flag(self, reason):
        """
        Put the customer on the watch list by hand, for an open dispute or an order problem.

        The flag keeps the customer on the list until Finance removes it.

        :param str reason: why the customer is flagged (required)
        :raises AccessError: if the user is not in Finance
        :raises UserError: if no reason is given
        """
        self._check_credit_right(FINANCE_GROUP)
        reason = self._require_credit_reason(reason)
        for partner in self:
            vals = {"is_credit_flagged": True, "credit_state_reason": reason}
            if partner.credit_state == "normal":
                vals["credit_state"] = "watch"
            # Rights checked above; Finance users may not edit contacts in Odoo 19.
            partner.sudo().write(vals)

    def action_credit_unflag(self, reason):
        """
        Remove the Finance flag; the nightly check then sets the state from invoices.

        :param str reason: why the flag is removed (required)
        """
        self._check_credit_right(FINANCE_GROUP)
        reason = self._require_credit_reason(reason)
        # Rights checked above; Finance users may not edit contacts in Odoo 19.
        self.sudo().write({"is_credit_flagged": False, "credit_state_reason": reason})

    def action_credit_hold(self, reason):
        """
        Put the customer on credit hold by hand.

        :param str reason: why (required)
        :raises AccessError: if the user is not the Finance Manager
        :raises UserError: if no reason is given
        """
        self._check_credit_right(MANAGER_GROUP)
        reason = self._require_credit_reason(reason)
        # Rights checked above; the Finance Manager may not edit contacts in Odoo 19.
        self.sudo().write({"credit_state": "hold", "credit_state_reason": reason})

    def action_credit_block(self, reason):
        """
        Put the customer under absolute block.

        :param str reason: why (required)
        :raises AccessError: if the user is not the Finance Manager
        :raises UserError: if no reason is given
        """
        self._check_credit_right(MANAGER_GROUP)
        reason = self._require_credit_reason(reason)
        # Rights checked above; the Finance Manager may not edit contacts in Odoo 19.
        self.sudo().write({"credit_state": "block", "credit_state_reason": reason})

    def action_credit_lift_hold(self, reason):
        """
        Lift a credit hold.

        The invoices overdue past the hold days at this moment are remembered,
        so the nightly check does not set the hold again for them; a further
        invoice passing the hold days sets it again.

        :param str reason: why the hold is lifted (required)
        :raises AccessError: if the user is not the Finance Manager
        :raises UserError: if a customer is not on hold or no reason is given
        """
        self._check_credit_right(MANAGER_GROUP)
        reason = self._require_credit_reason(reason)
        today = fields.Date.context_today(self)
        for partner in self:
            if partner.credit_state != "hold":
                raise UserError(
                    self.env._("%s is not on credit hold.", partner.display_name)
                )
            overdue = partner._overdue_invoices(today)
            covered = overdue.filtered(
                lambda move: self._days_overdue(move, today) > move.company_id.hold_days
            )
            # Rights checked above; the Finance Manager may not edit contacts in Odoo 19.
            partner.sudo().write(
                {
                    "credit_state": (
                        "watch" if overdue or partner.is_credit_flagged else "normal"
                    ),
                    "credit_state_reason": reason,
                    "hold_cleared_invoice_ids": [
                        fields.Command.link(move.id) for move in covered
                    ],
                }
            )

    def action_credit_unblock(self, reason):
        """
        Lift an absolute block.

        :param str reason: why the block is lifted (required)
        :raises AccessError: if the user is not the Finance Manager
        :raises UserError: if a customer is not blocked or no reason is given
        """
        self._check_credit_right(MANAGER_GROUP)
        reason = self._require_credit_reason(reason)
        today = fields.Date.context_today(self)
        for partner in self:
            if partner.credit_state != "block":
                raise UserError(self.env._("%s is not blocked.", partner.display_name))
            overdue = partner._overdue_invoices(today)
            # Rights checked above; the Finance Manager may not edit contacts in Odoo 19.
            partner.sudo().write(
                {
                    "credit_state": (
                        "watch" if overdue or partner.is_credit_flagged else "normal"
                    ),
                    "credit_state_reason": reason,
                }
            )

    # ------------------------------------------------------------------
    # Scheduled actions
    # ------------------------------------------------------------------

    @api.model
    def _cron_credit_check(self):
        """
        Nightly credit check: set each customer's state from its invoices.

        - Absolute block and credit hold are kept: only the Finance Manager
          lifts them.
        - An invoice overdue by more than its company's hold days, not covered
          by a lifted hold, puts the customer on credit hold.
        - Any overdue invoice, or a Finance flag, puts it on the watch list.
        - Otherwise the customer is normal.
        Paid invoices drop out of the invoices a lifted hold covered.
        """
        today = fields.Date.context_today(self)
        # The check reads every company's overdue invoices and only changes
        # credit states, so it runs as superuser.
        partners = self.sudo().with_context(active_test=False)
        overdue = partners.env["account.move"].search(self._overdue_domain(today))
        by_partner = {}
        for move in overdue:
            by_partner.setdefault(
                move.commercial_partner_id, partners.env["account.move"]
            )
            by_partner[move.commercial_partner_id] |= move
        candidates = partners.search(
            [
                "|",
                "|",
                ("credit_state", "=", "watch"),
                ("is_credit_flagged", "=", True),
                ("hold_cleared_invoice_ids", "!=", False),
            ]
        ) | partners.browse([p.id for p in by_partner])
        for partner in candidates:
            moves = by_partner.get(partner, partners.env["account.move"])
            settled = partner.hold_cleared_invoice_ids.filtered(
                lambda m: m.payment_state in ("paid", "in_payment", "reversed")
                or m.amount_residual <= 0
            )
            vals = {}
            if settled:
                vals["hold_cleared_invoice_ids"] = [
                    fields.Command.unlink(m.id) for m in settled
                ]
            if partner.credit_state not in ("hold", "block"):
                late = moves.filtered(
                    lambda m: self._days_overdue(m, today) > m.company_id.hold_days
                    and m not in partner.hold_cleared_invoice_ids
                )
                state = (
                    "hold"
                    if late
                    else ("watch" if moves or partner.is_credit_flagged else "normal")
                )
                if state != partner.credit_state:
                    vals["credit_state"] = state
            if vals:
                partner.write(vals)
        _logger.info(
            "Credit check on %s: %s customers reviewed", today, len(candidates)
        )

    @api.model
    def _cron_credit_watch_report(self):
        """
        Weekly email of watch-listed and held customers, per company.

        Each company's Finance Managers receive the customers with their overdue
        amount, oldest due date and salesperson, largest overdue first.
        """
        today = fields.Date.context_today(self)
        # The report covers every company's customers and invoices; it only reads.
        env = self.sudo().env
        partners = env["res.partner"].search(
            [("credit_state", "in", ("watch", "hold"))]
        )
        overdue = env["account.move"].search(
            self._overdue_domain(today)
            + [("commercial_partner_id", "in", partners.ids)]
        )
        managers = env.ref(MANAGER_GROUP).all_user_ids
        for company in overdue.company_id:
            moves = overdue.filtered(lambda m: m.company_id == company)
            rows = {}
            for move in moves:
                row = rows.setdefault(
                    move.commercial_partner_id,
                    {"amount": 0.0, "oldest": move.invoice_date_due},
                )
                row["amount"] += move.amount_residual_signed
                row["oldest"] = min(row["oldest"], move.invoice_date_due)
            recipients = managers.filtered(
                lambda u: company in u.company_ids and u.partner_id.email
            )
            if not rows or not recipients:
                continue
            ordered = sorted(rows.items(), key=lambda item: -item[1]["amount"])
            env["mail.mail"].create(
                {
                    "subject": self.env._(
                        "%(company)s: credit watch list, %(day)s",
                        company=company.name,
                        day=today,
                    ),
                    "body_html": self._credit_report_body(company, ordered),
                    "recipient_ids": [fields.Command.set(recipients.partner_id.ids)],
                    "email_from": company.email or env.user.email_formatted,
                    "auto_delete": False,
                }
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _overdue_domain(self, today):
        """
        Return the domain of open customer invoices due before the given day.

        :param date today: the day of the check
        :rtype: list
        """
        return [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "not in", ("paid", "in_payment", "reversed")),
            ("amount_residual", ">", 0),
            ("invoice_date_due", "<", today),
        ]

    def _overdue_invoices(self, today):
        """Return the customer's open invoices due before the given day."""
        self.ensure_one()
        return (
            self.env["account.move"]
            .sudo()  # Finance acts on customers of every company; invoices are only read
            .search(
                self._overdue_domain(today)
                + [("commercial_partner_id", "=", self.commercial_partner_id.id)]
            )
        )

    @api.model
    def _days_overdue(self, move, today):
        """Return how many days the invoice is past its due date on the given day."""
        return (today - move.invoice_date_due).days

    def _check_credit_right(self, group):
        """
        Refuse the action to users outside the group (the Finance Manager always may).

        :raises AccessError: if the user lacks the group
        """
        user = self.env.user
        if not (self.env.su or user.has_group(MANAGER_GROUP) or user.has_group(group)):
            if group == MANAGER_GROUP:
                raise AccessError(
                    self.env._(
                        "Only the Finance Manager can change a customer's credit state."
                    )
                )
            raise AccessError(
                self.env._("Only Finance can flag a customer for credit.")
            )

    @api.model
    def _require_credit_reason(self, reason):
        """
        Refuse a manual credit change without a reason.

        :param str reason: the reason given
        :return: the reason, stripped
        :raises UserError: if no reason is given
        """
        if not (reason or "").strip():
            raise UserError(
                self.env._("Give the reason for changing the credit state.")
            )
        return reason.strip()

    @api.model
    def _credit_report_body(self, company, ordered):
        """
        Return the HTML table of the weekly watch-list email.

        :param company: the company the customers bought from
        :param list ordered: (customer, {"amount", "oldest"}) pairs, largest first
        :rtype: Markup
        """
        head = Markup(
            "<tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th></tr>"
        ) % (
            self.env._("Customer"),
            self.env._("Credit State"),
            self.env._("Overdue Amount"),
            self.env._("Oldest Due Date"),
            self.env._("Salesperson"),
        )
        states = dict(self._fields["credit_state"]._description_selection(self.env))
        rows = Markup("").join(
            Markup(
                "<tr><td>%s</td><td>%s</td><td style='text-align:right'>%s</td><td>%s</td><td>%s</td></tr>"
            )
            % (
                partner.display_name,
                states[partner.credit_state],
                company.currency_id.format(data["amount"]),
                data["oldest"],
                partner.user_id.name or "",
            )
            for partner, data in ordered
        )
        intro = escape(
            self.env._(
                "Customers on the watch list or on credit hold, largest overdue amount first."
            )
        )
        return Markup("<p>%s</p><table border='1' cellpadding='4'>%s%s</table>") % (
            intro,
            head,
            rows,
        )
