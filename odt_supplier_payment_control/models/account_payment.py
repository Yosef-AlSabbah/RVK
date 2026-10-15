# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Vendor Payment Control (file: models/account_payment.py).

Extends account.payment with approval levels by amount, the duplicate block
and its administrator release, the trusted-account check and the shareholder
rule. Only outgoing vendor payments are controlled; customer payments and
incoming payments behave exactly as standard.
"""

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

APPROVAL_LEVELS = [
    ("finance", "Finance Manager"),
    ("operations", "Operations Manager"),
    ("ceo", "Chief Executive"),
]

# Level -> (company threshold field, group that approves it), in approval order.
LEVEL_RULES = {
    "finance": ("approval_threshold_1", "account.group_account_manager"),
    "operations": (
        "approval_threshold_2",
        "odt_supplier_payment_control.group_ops_approver",
    ),
    "ceo": ("approval_threshold_3", "odt_supplier_payment_control.group_ceo_approver"),
}


class AccountPayment(models.Model):
    """
    Payment.

    An outgoing vendor payment needs one approval per level its amount
    exceeds, cannot repeat an earlier payment unless an administrator released
    it, cannot go to an untrusted recipient account, and a shareholder
    payment cannot post to a payroll expense account. Posting checks all of
    this first (override of ``action_post``), then posts as standard.
    """

    _inherit = "account.payment"

    approval_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("to_approve_finance", "To Approve: Finance Manager"),
            ("to_approve_operations", "To Approve: Operations Manager"),
            ("to_approve_ceo", "To Approve: Chief Executive"),
            ("approved", "Approved"),
            ("posted", "Posted"),
            ("blocked", "Blocked"),
        ],
        string="Approval Status",
        compute="_compute_approval_state",
        store=True,
        copy=False,
        help="Where an outgoing vendor payment stands in the approvals its amount "
        "requires. Blocked: it repeats an earlier payment and waits for an "
        "administrator. Empty on payments the control does not cover.",
    )
    approval_ids = fields.One2many(
        comodel_name="payment.approval",
        inverse_name="payment_id",
        string="Approvals",
        readonly=True,
        copy=False,
        help="The approvals given, one per level, with approver and date.",
    )
    duplicate_of_id = fields.Many2one(
        comodel_name="account.payment",
        string="Duplicate Of",
        compute="_compute_duplicate_of_id",
        store=True,
        copy=False,
        ondelete="set null",
        index="btree_not_null",
        help="An earlier outgoing vendor payment with the same vendor, amount and "
        "memo. This payment is blocked until an administrator releases it.",
    )
    is_duplicate_released = fields.Boolean(
        string="Duplicate Released",
        copy=False,
        readonly=True,
        tracking=True,
        help="An administrator released this payment although it repeats an "
        "earlier one.",
    )

    @api.depends(
        "state",
        "amount",
        "currency_id",
        "date",
        "company_id",
        "payment_type",
        "partner_type",
        "approval_ids.level",
        "duplicate_of_id",
        "is_duplicate_released",
    )
    def _compute_approval_state(self):
        """Derive the approval status from the state, the amount and the approvals."""
        for payment in self:
            if not payment._is_vendor_payment():
                payment.approval_state = False
            elif payment.state in ("in_process", "paid"):
                payment.approval_state = "posted"
            elif payment.state != "draft":
                payment.approval_state = "draft"
            elif payment.duplicate_of_id and not payment.is_duplicate_released:
                payment.approval_state = "blocked"
            else:
                missing = payment._get_missing_approval_levels()
                payment.approval_state = (
                    f"to_approve_{missing[0]}" if missing else "approved"
                )

    @api.depends("state", "partner_id", "amount", "memo", "company_id", "payment_type")
    def _compute_duplicate_of_id(self):
        """
        Find the earlier outgoing vendor payment this draft repeats.

        The key is vendor, company, amount and a non-empty memo; cancelled and
        rejected payments do not count. Only drafts are recomputed, so a
        posted payment keeps what it was posted with.
        """
        for payment in self:
            if payment.state != "draft" or not payment._is_vendor_payment():
                payment.duplicate_of_id = payment.duplicate_of_id
                continue
            payment.duplicate_of_id = payment._find_duplicate()

    @api.constrains("state", "destination_account_id", "partner_id")
    def _check_shareholder_account(self):
        """
        Never let a shareholder payment sit on a payroll expense account.

        :raises ValidationError: a payment in process or paid to a contact
            marked shareholder uses an account marked payroll
        """
        for payment in self:
            if (
                payment.state in ("in_process", "paid")
                and payment._is_shareholder_on_payroll()
            ):
                raise ValidationError(payment._shareholder_message())

    def action_post(self):
        """
        Post as standard once the payment controls pass.

        Outgoing vendor payments are checked first: an unreleased duplicate,
        a missing approval level, an untrusted recipient account, or a
        shareholder payment to a payroll expense account is refused. Under the
        ``defer_payment_approval`` context (set when payments are registered
        from bills) a payment that waits for approval or a duplicate release
        stays in draft instead, so it reaches the approvers.

        :return: the standard result
        :raises UserError: if a controlled payment fails a check
        """
        defer = self.env.context.get("defer_payment_approval")
        to_post = self
        for payment in self.filtered(lambda p: p._is_vendor_payment()):
            error = payment._get_payment_control_error(waiting=not defer)
            if error:
                raise UserError(error)
            if defer and payment._is_waiting():
                to_post -= payment
        return super(AccountPayment, to_post).action_post()

    def _generate_journal_entry(
        self, write_off_line_vals=None, force_balance=None, line_ids=None
    ):
        """
        Keep a waiting vendor payment in draft when its entry is generated.

        The Register Payment dialog can create the entry while creating the
        payment (a write-off, or the exact balance of the bills), and standard
        then marks the payment In Process without calling action_post. A
        vendor payment that still waits for an approval or a duplicate release
        is put back to draft, with its entry left unposted, so the approvers
        see it; action_post posts that entry once the controls pass.

        :return: the standard result
        """
        res = super()._generate_journal_entry(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
            line_ids=line_ids,
        )
        waiting = self.filtered(
            lambda p: p._is_vendor_payment()
            and p.state == "in_process"
            and p.move_id.state == "draft"
            and p._is_waiting()
        )
        if waiting:
            waiting.write({"state": "draft"})
        return res

    def action_approve(self):
        """
        Give the next approval level this payment needs, as the current user.

        :return: True
        :raises UserError: the payment is not a draft vendor payment waiting
            for approval, or it is a blocked duplicate
        :raises AccessError: the user does not hold the level's approver group
        """
        self.ensure_one()
        if not self._is_vendor_payment() or self.state != "draft":
            raise UserError(
                self.env._("Only draft outgoing vendor payments are approved.")
            )
        if self.duplicate_of_id and not self.is_duplicate_released:
            raise UserError(self._duplicate_message())
        missing = self._get_missing_approval_levels()
        if not missing:
            raise UserError(
                self.env._(
                    "%(payment)s needs no further approval.", payment=self.display_name
                )
            )
        level = missing[0]
        group = LEVEL_RULES[level][1]
        if not self.env.user.has_group(group):
            raise AccessError(
                self.env._(
                    "This payment waits for the %(level)s's approval, which you "
                    "cannot give.",
                    level=self._level_label(level),
                )
            )
        self.env["payment.approval"].create({"payment_id": self.id, "level": level})
        # sudo: approvers hold read-only accounting rights; posting in the
        # chatter needs write access, and the message only records the approval.
        self.sudo().message_post(
            body=self.env._(
                "Approved at the %(level)s level by %(user)s.",
                level=self._level_label(level),
                user=self.env.user.name,
            )
        )
        return True

    def action_release_duplicate(self):
        """
        Release a blocked duplicate (administrators only), logged on both payments.

        Reopening the earlier transaction is recorded here: the earlier
        payment stays as it is (resetting it would reverse money already
        sent); this payment may proceed through its approvals.

        :return: True
        :raises AccessError: the user is not an administrator
        :raises UserError: the payment is not a blocked duplicate
        """
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                self.env._("Only an administrator can release a duplicate payment.")
            )
        for payment in self:
            if not payment.duplicate_of_id or payment.is_duplicate_released:
                raise UserError(
                    self.env._(
                        "%(payment)s is not a blocked duplicate.",
                        payment=payment.display_name,
                    )
                )
            # sudo: the administrator group was checked above; an administrator
            # may hold no accounting rights to write the payment or its chatter.
            payment.sudo().is_duplicate_released = True
            body = self.env._(
                "Duplicate released by %(user)s: %(payment)s may be paid although it "
                "repeats %(earlier)s (same vendor, amount and reference).",
                user=self.env.user.name,
                payment=payment.display_name,
                earlier=payment.duplicate_of_id.display_name,
            )
            for record in payment | payment.duplicate_of_id:
                # sudo: same administrator check; the note only records the release.
                record.sudo().message_post(body=Markup("<p>%s</p>") % body)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _level_label(self, level):
        """Return the translated label of an approval level."""
        field = self.env["payment.approval"]._fields["level"]
        return dict(field._description_selection(self.env))[level]

    def _is_vendor_payment(self):
        """Return whether this payment is an outgoing vendor payment (the controlled kind)."""
        self.ensure_one()
        return self.payment_type == "outbound" and self.partner_type == "supplier"

    def _get_company_amount(self):
        """Return the payment amount in the company currency, at the payment date."""
        self.ensure_one()
        company = self.company_id
        currency = self.currency_id or company.currency_id
        return currency._convert(
            self.amount,
            company.currency_id,
            company,
            self.date or fields.Date.context_today(self),
        )

    def _get_required_approval_levels(self):
        """
        Return the levels this payment's amount requires, in approval order.

        A level is required when its company threshold is set and the amount,
        in company currency, is strictly above it.

        :return: list of level keys ('finance', 'operations', 'ceo')
        """
        self.ensure_one()
        company = self.company_id
        amount = self._get_company_amount()
        levels = []
        for level, (threshold_field, _group) in LEVEL_RULES.items():
            threshold = company[threshold_field]
            if threshold and company.currency_id.compare_amounts(amount, threshold) > 0:
                levels.append(level)
        return levels

    def _get_missing_approval_levels(self):
        """Return the required levels not yet approved, in approval order."""
        self.ensure_one()
        # sudo: invoicing users may not read approvals; only their levels are used.
        given = set(self.sudo().approval_ids.mapped("level"))
        return [
            level
            for level in self._get_required_approval_levels()
            if level not in given
        ]

    def _is_waiting(self):
        """Return whether the payment waits for an approval or a duplicate release."""
        self.ensure_one()
        return bool(
            (self.duplicate_of_id and not self.is_duplicate_released)
            or self._get_missing_approval_levels()
        )

    def _find_duplicate(self):
        """
        Return the earliest other payment with the same vendor, amount and memo.

        :return: an account.payment record, or an empty recordset
        """
        self.ensure_one()
        if not (self.partner_id and self.amount and self.memo):
            return self.browse()
        domain = [
            ("partner_id", "=", self.partner_id.id),
            ("company_id", "=", self.company_id.id),
            ("payment_type", "=", "outbound"),
            ("partner_type", "=", "supplier"),
            ("amount", "=", self.amount),
            ("memo", "=", self.memo),
            ("state", "not in", ("canceled", "rejected")),
        ]
        if self._origin.id:
            domain.append(("id", "<", self._origin.id))
        # sudo: the block must see every earlier payment of the company, even
        # one the current user cannot read.
        return self.sudo().search(domain, order="id", limit=1).sudo(False)

    def _is_shareholder_on_payroll(self):
        """Return whether a shareholder payment uses a payroll expense account."""
        self.ensure_one()
        return bool(
            self.partner_id.is_shareholder and self.destination_account_id.is_payroll
        )

    def _shareholder_message(self):
        """Return the refusal naming the payroll expense account."""
        return self.env._(
            "%(account)s is a payroll expense account: a payment to shareholder "
            "%(partner)s cannot be posted to it. Post it to the shareholder's "
            "account instead.",
            account=self.destination_account_id.display_name,
            partner=self.partner_id.display_name,
        )

    def _duplicate_message(self):
        """Return the refusal naming the earlier payment this one repeats."""
        return self.env._(
            "%(payment)s repeats %(earlier)s (same vendor, amount and reference). "
            "It is blocked until an administrator releases it.",
            payment=self.display_name,
            earlier=self.duplicate_of_id.display_name,
        )

    def _get_payment_control_error(self, waiting=True):
        """
        Return why this vendor payment cannot be posted, or False.

        :param bool waiting: also report a missing approval or an unreleased
            duplicate (False when registering from bills, where those payments
            are left in draft for the approvers)
        :return: the message, or False
        """
        self.ensure_one()
        if self._is_shareholder_on_payroll():
            return self._shareholder_message()
        bank = self.partner_bank_id
        if bank and not bank.allow_out_payment:
            return self.env._(
                "The bank account %(account)s of %(partner)s is not trusted. Verify it "
                "with the vendor and mark it trusted before paying it.",
                account=bank.display_name,
                partner=self.partner_id.display_name,
            )
        if not waiting:
            return False
        if self.duplicate_of_id and not self.is_duplicate_released:
            return self._duplicate_message()
        missing = self._get_missing_approval_levels()
        if missing:
            return self.env._(
                "%(payment)s cannot be posted before these approvals: %(levels)s.",
                payment=self.display_name,
                levels=", ".join(self._level_label(level) for level in missing),
            )
        return False
