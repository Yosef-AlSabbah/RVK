# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
Monthly Credit Exposure (file: models/credit_exposure.py).

Defines credit.exposure, a read-only SQL view with one line per customer,
company and calendar month: the customer's credit sales, the company's
monthly ceiling, the customer's share of it and its cap. It is computed when
read, so it never falls out of step with the orders.
"""

from odoo import fields, models, tools
from odoo.tools import SQL


class CreditExposure(models.Model):
    """
    Monthly Credit Exposure.

    One line per customer (commercial partner), company and month of
    confirmation:
      - Credit sales = confirmed orders whose payment term is not full advance,
        at their total with VAT in the company currency, without down
        payments and without lines of special products excluded from credit.
      - Share = credit sales / the company's monthly ceiling.
    """

    _name = "credit.exposure"
    _description = "Monthly Credit Exposure"
    _auto = False
    _order = "month desc, credit_sales desc"
    _rec_name = "partner_id"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
        ondelete="cascade",
        help="Customer (commercial entity) the credit sales belong to.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        readonly=True,
        ondelete="cascade",
        help="Company that made the sales; each company has its own ceiling.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        readonly=True,
        ondelete="cascade",
        help="Currency of the company; all amounts are in it.",
    )
    month = fields.Date(
        string="Month",
        readonly=True,
        help="First day of the calendar month of confirmation.",
    )
    credit_sales = fields.Monetary(
        string="Credit Sales",
        currency_field="currency_id",
        readonly=True,
        help="The customer's credit sales confirmed in the month, with VAT.",
    )
    credit_ceiling = fields.Monetary(
        string="Monthly Ceiling",
        currency_field="currency_id",
        readonly=True,
        help="The company's monthly credit ceiling.",
    )
    share_pct = fields.Float(
        string="Share of Ceiling (%)",
        readonly=True,
        help="Credit sales divided by the company's monthly ceiling.",
    )
    cap_pct = fields.Float(
        string="Customer Cap (%)",
        readonly=True,
        help="The customer's monthly cap, as a share of the ceiling.",
    )

    def _query(self):
        """
        Return the SQL that builds the view.

        :return: the SELECT of the view
        :rtype: SQL
        """
        return SQL("""
            SELECT
                ROW_NUMBER() OVER (ORDER BY sub.company_id, sub.month, sub.partner_id) AS id,
                sub.partner_id,
                sub.company_id,
                sub.currency_id,
                sub.month,
                sub.credit_sales,
                sub.credit_ceiling,
                CASE WHEN sub.credit_ceiling > 0
                    THEN sub.credit_sales / sub.credit_ceiling * 100.0 ELSE 0.0
                END AS share_pct,
                sub.cap_pct
            FROM (
                SELECT
                    customer.commercial_partner_id AS partner_id,
                    so.company_id AS company_id,
                    company.currency_id AS currency_id,
                    DATE_TRUNC('month', so.date_order)::date AS month,
                    SUM(
                        sol.price_total
                        / CASE COALESCE(so.currency_rate, 0)
                            WHEN 0 THEN 1.0 ELSE so.currency_rate END
                    ) AS credit_sales,
                    MAX(COALESCE(company.credit_ceiling, 0)) AS credit_ceiling,
                    MAX(COALESCE(commercial.credit_cap_pct, 0)) AS cap_pct
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                JOIN res_partner customer ON customer.id = so.partner_id
                JOIN res_partner commercial ON commercial.id = customer.commercial_partner_id
                JOIN res_company company ON company.id = so.company_id
                LEFT JOIN account_payment_term term ON term.id = so.payment_term_id
                LEFT JOIN product_product product ON product.id = sol.product_id
                LEFT JOIN product_template template ON template.id = product.product_tmpl_id
                WHERE so.state = 'sale'
                    AND sol.display_type IS NULL
                    AND NOT COALESCE(sol.is_downpayment, FALSE)
                    AND COALESCE(term.advance_pct, 0) < 100
                    AND NOT (
                        COALESCE(template.is_special, FALSE)
                        AND COALESCE(template.is_credit_excluded, FALSE)
                    )
                GROUP BY customer.commercial_partner_id, so.company_id,
                    company.currency_id, DATE_TRUNC('month', so.date_order)
            ) sub
            """)

    def init(self):
        """Create or replace the SQL view behind the model."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            SQL(
                "CREATE OR REPLACE VIEW %s AS (%s)",
                SQL.identifier(self._table),
                self._query(),
            )
        )
