# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Shared fixtures for the supplier payment control tests.

RVK with the test thresholds (50,000, 200,000 and 500,000 SAR) and Waterline,
the vendors of the spec, a valve billed on received quantities and a
consultancy service, the salaries (payroll) and shareholder current accounts,
and one user per role.
"""

from freezegun import freeze_time

from odoo import Command
from odoo.tests import TransactionCase, new_test_user

DAY = "2026-10-05"


class PaymentControlCase(TransactionCase):
    """Fixtures and helpers shared by every supplier payment control test."""

    @classmethod
    def setUpClass(cls):
        """Create the companies' settings, partners, products, accounts and users."""
        super().setUpClass()
        companies = cls.env["res.company"]
        cls.rvk = companies.search([("name", "=", "RVK")], limit=1) or cls.env.company
        cls.waterline = companies.search([("name", "=", "Waterline")], limit=1)
        if not cls.waterline:
            cls.waterline = companies.create(
                {"name": "Waterline", "currency_id": cls.rvk.currency_id.id}
            )
        if not cls.waterline.chart_template and cls.rvk.chart_template:
            # A fresh database has no Waterline accounting: give it RVK's chart.
            cls.env["account.chart.template"].try_loading(
                cls.rvk.chart_template, company=cls.waterline, install_demo=False
            )
        cls.env.user.company_ids |= cls.rvk | cls.waterline
        cls.env = cls.env(
            context=dict(
                cls.env.context, allowed_company_ids=[cls.rvk.id, cls.waterline.id]
            )
        )
        cls.rvk.write(
            {
                "approval_threshold_1": 50_000,
                "approval_threshold_2": 200_000,
                "approval_threshold_3": 500_000,
            }
        )
        journals = cls.env["account.journal"]
        cls.bank = journals.search(
            [("type", "=", "bank"), ("company_id", "=", cls.rvk.id)], limit=1
        )
        cls.waterline_bank = journals.search(
            [("type", "=", "bank"), ("company_id", "=", cls.waterline.id)], limit=1
        )

        partners = cls.env["res.partner"]
        cls.valvitalia = partners.create({"name": "Valvitalia", "is_company": True})
        cls.consultant = partners.create(
            {"name": "Gulf Advisory Consultants", "is_company": True}
        )
        cls.khalid = partners.create(
            {"name": "Khalid Al Rashid", "is_shareholder": True}
        )
        cls.customer = partners.create(
            {"name": "Al Nakheel Contracting", "is_company": True}
        )

        products = cls.env["product.product"]
        cls.valve = products.create(
            {
                "name": "Gate Valve DN200",
                "type": "consu",
                "is_storable": True,
                "purchase_method": "receive",
                "standard_price": 100.0,
                "supplier_taxes_id": [Command.clear()],
                "taxes_id": [Command.clear()],
            }
        )
        cls.consultancy = products.create(
            {
                "name": "Consultancy",
                "type": "service",
                "purchase_method": "purchase",
                "supplier_taxes_id": [Command.clear()],
                "taxes_id": [Command.clear()],
            }
        )

        accounts = cls.env["account.account"].with_company(cls.rvk)
        cls.salaries = accounts.create(
            {
                "code": "629901",
                "name": "Salaries and Wages (payment control tests)",
                "account_type": "expense",
                "is_payroll": True,
            }
        )
        cls.shareholder_account = accounts.create(
            {
                "code": "269901",
                "name": "Shareholder Current Account (payment control tests)",
                "account_type": "liability_current",
                "reconcile": True,
            }
        )

        company_ids = [cls.rvk.id, cls.waterline.id]
        cls.accountant = new_test_user(
            cls.env,
            login="spc_accountant",
            groups="account.group_account_user",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.finance_manager = new_test_user(
            cls.env,
            login="spc_finance_manager",
            name="Huda Finance Manager",
            groups="account.group_account_manager",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.ops_manager = new_test_user(
            cls.env,
            login="spc_ops_manager",
            name="Omar Operations Manager",
            groups="odt_supplier_payment_control.group_ops_approver",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.ceo = new_test_user(
            cls.env,
            login="spc_ceo",
            name="Faisal Chief Executive",
            groups="odt_supplier_payment_control.group_ceo_approver",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.administrator = new_test_user(
            cls.env,
            login="spc_administrator",
            name="Sami Administrator",
            groups="base.group_system,account.group_account_readonly",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.rvk_approver = new_test_user(
            cls.env,
            login="spc_rvk_approver",
            groups="odt_supplier_payment_control.group_ops_approver",
            company_id=cls.rvk.id,
            company_ids=[cls.rvk.id],
        )

    # ------------------------------------------------------------------
    # Purchases and bills
    # ------------------------------------------------------------------

    def make_order(self, qty, price=100.0):
        """
        Confirm a purchase order of valves from Valvitalia.

        :param float qty: valves ordered
        :param float price: unit price
        :return: the confirmed purchase order
        """
        with freeze_time(DAY):
            order = self.env["purchase.order"].create(
                {
                    "partner_id": self.valvitalia.id,
                    "company_id": self.rvk.id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": self.valve.id,
                                "product_qty": qty,
                                "price_unit": price,
                                "tax_ids": [Command.clear()],
                            }
                        )
                    ],
                }
            )
            order.button_confirm()
        return order

    def receive(self, order, qty):
        """Receive the given quantity of the order's valves (no backorder kept)."""
        picking = order.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel")
        )
        picking.move_ids.quantity = qty
        picking.move_ids.picked = True
        with freeze_time(DAY):
            picking.with_context(
                skip_backorder=True, picking_ids_not_to_backorder=picking.ids
            ).button_validate()
        self.assertEqual(order.order_line.qty_received, qty)

    def make_bill(self, partner, lines, ref=False, post=True):
        """
        Create a vendor bill dated DAY.

        :param partner: the vendor
        :param list lines: (product, quantity, price, purchase line or False)
        :param str ref: the vendor's bill reference
        :param bool post: post the bill
        :return: the bill
        """
        bill = (
            self.env["account.move"]
            .with_company(self.rvk)
            .create(
                {
                    "move_type": "in_invoice",
                    "partner_id": partner.id,
                    "ref": ref,
                    "invoice_date": DAY,
                    "invoice_date_due": DAY,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "quantity": qty,
                                "price_unit": price,
                                "purchase_line_id": po_line.id if po_line else False,
                                "tax_ids": [Command.clear()],
                            }
                        )
                        for product, qty, price, po_line in lines
                    ],
                }
            )
        )
        if post:
            with freeze_time(DAY):
                bill.action_post()
        return bill

    def order_bill(self, order, qty, ref="BILL-P00531"):
        """Bill the given quantity of the order's valves at the ordered price."""
        line = order.order_line
        return self.make_bill(
            self.valvitalia, [(self.valve, qty, line.price_unit, line)], ref=ref
        )

    def register(self, bills, user=None):
        """
        Register payment of the bills from the bank journal, as the accountant.

        :return: the payments created
        """
        wizard = (
            self.env["account.payment.register"]
            .with_user(user or self.accountant)
            .with_context(active_model="account.move", active_ids=bills.ids)
            .create({"payment_date": DAY, "journal_id": self.bank.id})
        )
        with freeze_time(DAY):
            wizard.action_create_payments()
        return bills.matched_payment_ids

    # ------------------------------------------------------------------
    # Payments and batches
    # ------------------------------------------------------------------

    def make_payment(self, partner, amount, memo="", **values):
        """
        Prepare a draft outgoing vendor payment from the RVK bank, as the accountant.

        :param float amount: amount in SAR
        :param str memo: the payment reference
        :return: the draft payment
        """
        vals = {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": partner.id,
            "amount": amount,
            "memo": memo,
            "date": DAY,
            "journal_id": self.bank.id,
        }
        vals.update(values)
        return (
            self.env["account.payment"]
            .with_user(self.accountant)
            .with_company(self.rvk)
            .create(vals)
        )

    def post(self, payment, user=None):
        """Post the payment with the clock on DAY, as the accountant by default."""
        with freeze_time(DAY):
            payment.with_user(user or self.accountant).action_post()

    def approve(self, payment, *users):
        """Have each user approve the payment, in order."""
        for user in users:
            with freeze_time(DAY):
                payment.with_user(user).action_approve()

    def make_batch(self, payments, batch_type="outbound"):
        """Put the payments in one batch payment of the RVK bank."""
        return self.env["account.batch.payment"].create(
            {
                "journal_id": self.bank.id,
                "batch_type": batch_type,
                "payment_method_id": payments.payment_method_id.id,
                "payment_ids": [Command.set(payments.ids)],
            }
        )
