# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Shared fixtures for the credit control tests.

Two companies (RVK with a 5,000,000 SAR ceiling and Waterline), the customers
of the spec, an untaxed product and a special product excluded from credit,
the Net 30 and 100% Advance terms, and one user per role.
"""

from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.tests import TransactionCase, new_test_user


class CreditControlCase(TransactionCase):
    """Fixtures and helpers shared by every credit control test."""

    @classmethod
    def setUpClass(cls):
        """Create the companies, customers, products, terms and users."""
        super().setUpClass()
        cls.rvk = cls.env.company
        cls.sar = cls.env.ref("base.SAR")
        cls.sar.active = True
        cls.rvk.write({"credit_ceiling": 5_000_000, "hold_days": 60})
        # On a database configured by create-db the second company already exists.
        cls.waterline = cls.env["res.company"].search(
            [("name", "=", "Waterline")], limit=1
        )
        if not cls.waterline:
            cls.waterline = cls.env["res.company"].create(
                {"name": "Waterline", "currency_id": cls.sar.id}
            )
        cls.waterline.credit_ceiling = 2_000_000
        # A company created before Inventory was installed has no warehouse, and
        # sale_stock (auto-installed with Sales and Inventory) needs one to confirm.
        warehouses = cls.env["stock.warehouse"]
        if "warehouse_id" in cls.env["sale.order"]._fields and not warehouses.search(
            [("company_id", "=", cls.waterline.id)], limit=1
        ):
            warehouses.create(
                {"name": "Waterline", "code": "WTL", "company_id": cls.waterline.id}
            )
        cls.env.user.company_ids |= cls.waterline

        partners = cls.env["res.partner"]
        cls.al_nakheel = partners.create(
            {"name": "Al Nakheel Contracting", "is_company": True, "credit_cap_pct": 10}
        )
        cls.gulf_pipes = partners.create(
            {"name": "Gulf Pipes Trading", "is_company": True, "credit_cap_pct": 10}
        )
        cls.big_buyer = partners.create(
            {
                "name": "National Water Projects",
                "is_company": True,
                "credit_cap_pct": 100,
            }
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Gate Valve DN200",
                "type": "consu",
                "list_price": 1.0,
                "taxes_id": [Command.clear()],
                "invoice_policy": "order",
            }
        )
        cls.special_product = cls.env["product.product"].create(
            {
                "name": "Special Hydrant",
                "type": "consu",
                "list_price": 1.0,
                "taxes_id": [Command.clear()],
                "is_special": True,
                "is_credit_excluded": True,
            }
        )

        terms = cls.env["account.payment.term"]
        cls.net30 = terms.create(
            {
                "name": "Net 30 (credit tests)",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100, "nb_days": 30}
                    )
                ],
            }
        )
        cls.advance = terms.create(
            {
                "name": "100% Advance (credit tests)",
                "advance_pct": 100,
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100, "nb_days": 0}
                    )
                ],
            }
        )

        company_ids = [cls.rvk.id, cls.waterline.id]
        cls.salesperson = new_test_user(
            cls.env,
            login="credit_salesperson",
            groups="sales_team.group_sale_salesman_all_leads",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.finance_manager = new_test_user(
            cls.env,
            login="credit_finance_manager",
            name="Huda Finance Manager",
            email="finance.manager@rvk.example",
            groups="account.group_account_manager,sales_team.group_sale_salesman_all_leads",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.accountant = new_test_user(
            cls.env,
            login="credit_accountant",
            groups="account.group_account_invoice",
            company_id=cls.rvk.id,
            company_ids=company_ids,
        )
        cls.rvk_user = new_test_user(
            cls.env,
            login="credit_rvk_only",
            groups="sales_team.group_sale_salesman_all_leads",
            company_id=cls.rvk.id,
            company_ids=[cls.rvk.id],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def make_order(self, partner, amount, term=None, company=None, lines=None):
        """
        Create a quotation of one line (or the given lines) for the customer.

        :param partner: the customer
        :param float amount: the amount of the single line, untaxed
        :param term: payment term, Net 30 by default
        :param company: selling company, RVK by default
        :param list lines: (product, amount) pairs instead of the single line
        :return: the quotation
        """
        company = company or self.rvk
        lines = lines or [(self.product, amount)]
        return (
            self.env["sale.order"]
            .with_company(company)
            .create(
                {
                    "partner_id": partner.id,
                    "company_id": company.id,
                    "payment_term_id": (term or self.net30).id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_uom_qty": 1,
                                "price_unit": price,
                                "tax_ids": [Command.clear()],
                            }
                        )
                        for product, price in lines
                    ],
                }
            )
        )

    def confirm_on(self, order, day):
        """Confirm the order with the clock set to the given day."""
        with freeze_time(day):
            return order.action_confirm()

    def exposure(self, partner, company, month):
        """
        Return the exposure line of a customer, company and month.

        :param date month: any day of the month
        :return: the credit.exposure line, or an empty recordset
        """
        self.env.flush_all()
        self.env["credit.exposure"].invalidate_model()
        return self.env["credit.exposure"].search(
            [
                ("partner_id", "=", partner.id),
                ("company_id", "=", company.id),
                ("month", "=", month.replace(day=1)),
            ]
        )

    def company_total(self, company, month):
        """Return the company's credit sales of the month."""
        self.env.flush_all()
        self.env["credit.exposure"].invalidate_model()
        lines = self.env["credit.exposure"].search(
            [("company_id", "=", company.id), ("month", "=", month.replace(day=1))]
        )
        return sum(lines.mapped("credit_sales"))

    def make_invoice(self, partner, amount, due, company=None, move_type="out_invoice"):
        """
        Create and post an invoice due on the given day.

        The invoice date and the due date are the day given, and the clock is
        set to that day when posting: the Saudi localization refuses invoices
        dated after today.

        :param date due: the due date
        :return: the posted invoice
        """
        move = (
            self.env["account.move"]
            .with_company(company or self.rvk)
            .create(
                {
                    "move_type": move_type,
                    "partner_id": partner.id,
                    "invoice_date": due,
                    "invoice_date_due": due,
                    "invoice_payment_term_id": False,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "quantity": 1,
                                "price_unit": amount,
                                "tax_ids": [Command.clear()],
                            }
                        )
                    ],
                }
            )
        )
        with freeze_time(f"{due} 12:00:00"):
            move.action_post()
        self.assertEqual(move.invoice_date_due, due)
        return move

    def freeze(self, day):
        """Return a context manager that sets the clock to the given moment."""
        return freeze_time(day)

    def run_credit_check(self, day):
        """Run the nightly credit check as the scheduler would, on the given day."""
        with freeze_time(day):
            self.env["res.partner"]._cron_credit_check()

    OCT = date(2026, 10, 1)
    NOV = date(2026, 11, 1)

    def set_state(self, partner, action, reason="Finance decision"):
        """Have the Finance Manager run a credit state action with a reason."""
        getattr(partner.with_user(self.finance_manager), action)(reason)

    def make_picking(self, partner, code):
        """
        Create a ready transfer of one unit for the partner.

        :param str code: 'outgoing' for a delivery, 'incoming' for a receipt
        :return: the transfer, ready to validate
        """
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.rvk.id)], limit=1
        )
        picking_type = (
            warehouse.out_type_id if code == "outgoing" else warehouse.in_type_id
        )
        source = picking_type.default_location_src_id or self.env.ref(
            "stock.stock_location_suppliers"
        )
        dest = picking_type.default_location_dest_id or self.env.ref(
            "stock.stock_location_customers"
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id,
                "location_id": source.id,
                "location_dest_id": dest.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "location_id": source.id,
                            "location_dest_id": dest.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.move_ids.quantity = 1
        return picking
