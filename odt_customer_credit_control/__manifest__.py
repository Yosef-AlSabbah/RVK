# Part of OdooTec. See LICENSE file for full copyright and licensing details.

{
    "name": "Customer Credit Control",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Caps monthly credit sales per customer and company, and holds or blocks customers with overdue invoices.",
    "description": """
Customer Credit Control
=======================
Keeps sales within the company's credit policy. Each month's credit sales are
capped per customer and per company, an order over a limit waits for the
Finance Manager's approval, and customers with overdue invoices move through
four credit states that stop new business until Finance releases them.

Key Capabilities:
-----------------
1. **Monthly credit ceiling** (`credit.exposure`, `sale.order`):

   - Credit sales are the confirmed orders whose payment term is not full
     advance, with VAT, per customer, company and calendar month, leaving out
     special products excluded from credit totals.
   - Confirming an order that would take the customer over its cap, or the
     company over its ceiling, waits for Finance Manager approval, which
     records who approved, when and why.

2. **Customer credit states** (`res.partner`):

   - Normal, watch list, credit hold and absolute block.
   - A nightly check watch-lists customers with an overdue invoice and puts
     them on hold once an invoice is more than the company's hold days
     overdue; only the Finance Manager lifts a hold or a block.
   - A weekly email lists watch-listed and held customers, largest overdue
     first.

3. **Integration**:

   - Extends sale order confirmation, delivery validation and customer
     invoice posting to refuse held or blocked customers, and adds the advance
     share to payment terms and the special marks to products.
    """,
    "author": "OdooTec",
    "website": "https://www.odootec.com",
    "license": "Other proprietary",
    "depends": [
        "sale_management",
        "stock",
        "account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "wizard/credit_decision_views.xml",
        "views/credit_exposure_views.xml",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
        "views/account_payment_term_views.xml",
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
