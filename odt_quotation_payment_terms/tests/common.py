# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Shared fixtures for the quotation payment term tests.

RVK with a 50% special-item minimum advance, the customers of the spec with
their default terms, the payment terms the spec names (Net 30, Net 60, 30% and
50% advance, a three-milestone instalment term), a standard and a special gate
valve, and one user per role.
"""

from freezegun import freeze_time

from odoo import Command
from odoo.tests import TransactionCase, new_test_user


class QuotationTermsCase(TransactionCase):
    """Fixtures and helpers shared by every quotation payment term test."""

    @classmethod
    def setUpClass(cls):
        """Create the terms, customers, products and users."""
        super().setUpClass()
        cls.rvk = cls.env.company
        # No credit ceiling: confirmations in these tests are not credit-checked.
        cls.rvk.write({"special_min_advance": 50.0, "credit_ceiling": 0.0})

        terms = cls.env["account.payment.term"]
        cls.net30 = terms.create(
            {
                "name": "Net 30 (quotation tests)",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100, "nb_days": 30}
                    )
                ],
            }
        )
        cls.net60 = terms.create(
            {
                "name": "Net 60 (quotation tests)",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100, "nb_days": 60}
                    )
                ],
            }
        )
        cls.advance30 = terms.create(
            {
                "name": "30% Advance (quotation tests)",
                "advance_pct": 30,
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 30, "nb_days": 0}
                    ),
                    Command.create(
                        {"value": "percent", "value_amount": 70, "nb_days": 30}
                    ),
                ],
            }
        )
        cls.advance50 = terms.create(
            {
                "name": "50% Advance (quotation tests)",
                "advance_pct": 50,
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 50, "nb_days": 0}
                    ),
                    Command.create(
                        {"value": "percent", "value_amount": 50, "nb_days": 30}
                    ),
                ],
            }
        )
        cls.milestones = terms.create(
            {
                "name": "Project milestones 30/40/30 (quotation tests)",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 30, "nb_days": 0}
                    ),
                    Command.create(
                        {"value": "percent", "value_amount": 40, "nb_days": 60}
                    ),
                    Command.create(
                        {"value": "percent", "value_amount": 30, "nb_days": 120}
                    ),
                ],
            }
        )

        partners = cls.env["res.partner"].with_company(cls.rvk)
        cls.al_nakheel = partners.create(
            {
                "name": "Al Nakheel Contracting",
                "is_company": True,
                "email": "sales@alnakheel.example",
                "property_payment_term_id": cls.net30.id,
            }
        )
        cls.national_water = partners.create(
            {
                "name": "National Water Projects",
                "is_company": True,
                "email": "projects@nationalwater.example",
                "property_payment_term_id": cls.milestones.id,
            }
        )
        cls.vendor = partners.create({"name": "Valve Works Supply", "is_company": True})

        products = cls.env["product.product"]
        cls.valve = products.create(
            {
                "name": "Gate Valve DN200",
                "type": "consu",
                "list_price": 1000.0,
                "taxes_id": [Command.clear()],
                "invoice_policy": "order",
            }
        )
        cls.special_valve = products.create(
            {
                "name": "Special Gate Valve DN600",
                "type": "consu",
                "list_price": 25000.0,
                "taxes_id": [Command.clear()],
                "invoice_policy": "order",
                "is_special": True,
            }
        )

        cls.salesperson = new_test_user(
            cls.env,
            login="qpt_salesperson",
            name="Sami Salesperson",
            email="salesperson@rvk.example",
            groups="sales_team.group_sale_salesman_all_leads",
            company_id=cls.rvk.id,
        )
        cls.finance_manager = new_test_user(
            cls.env,
            login="qpt_finance_manager",
            name="Huda Finance Manager",
            email="finance.manager@rvk.example",
            groups="account.group_account_manager,"
            "odt_quotation_payment_terms.group_send_approver,"
            "sales_team.group_sale_salesman_all_leads",
            company_id=cls.rvk.id,
        )
        cls.operations_manager = new_test_user(
            cls.env,
            login="qpt_operations_manager",
            name="Omar Operations Manager",
            email="operations.manager@rvk.example",
            groups="odt_quotation_payment_terms.group_send_approver,"
            "sales_team.group_sale_salesman_all_leads",
            company_id=cls.rvk.id,
        )
        cls.sales_manager = new_test_user(
            cls.env,
            login="qpt_sales_manager",
            name="Salem Sales Manager",
            email="sales.manager@rvk.example",
            groups="sales_team.group_sale_manager",
            company_id=cls.rvk.id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def make_quotation(self, partner, term=None, products=None):
        """
        Create a quotation as the salesperson.

        :param partner: the customer
        :param term: the payment term; the customer's default when None, none when False
        :param list products: the products of the lines (one unit each), the valve by default
        :return: the quotation, in the salesperson's environment
        """
        vals = {
            "partner_id": partner.id,
            "user_id": self.salesperson.id,
            "order_line": [
                Command.create(
                    {
                        "product_id": product.id,
                        "product_uom_qty": 1,
                        "tax_ids": [Command.clear()],
                    }
                )
                for product in (products or [self.valve])
            ],
        }
        if term is not None:
            vals["payment_term_id"] = term.id if term else False
        return self.env["sale.order"].with_user(self.salesperson).create(vals)

    def send(self, order):
        """
        Send the quotation as the salesperson, as the Send button and composer do.

        :return: the composer action the Send button opened
        """
        order = order.with_user(self.salesperson)
        action = order.action_quotation_send()
        composer = (
            self.env["mail.compose.message"]
            .with_user(self.salesperson)
            .with_context(**action["context"])
            .create({})
        )
        composer.action_send_mail()
        return action

    def freeze(self, moment):
        """Return a context manager that sets the clock to the given moment."""
        return freeze_time(moment)

    def watch_list(self, partner):
        """Have the Finance Manager put the customer on the watch list."""
        partner.with_user(self.finance_manager).action_credit_flag("Open dispute")
