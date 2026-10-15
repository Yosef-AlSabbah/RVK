# Part of OdooTec. See LICENSE file for full copyright and licensing details.

{
    "name": "Quotation Payment Terms",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Sends a quotation only on an approved payment term, with the special-item advance met and watch-listed customers approved.",
    "description": """
Quotation Payment Terms
=======================
Makes sure a quotation leaves only on a payment term agreed and approved
before it is sent, with the advance special items need, and with a manager's
approval when the customer is on the credit watch list.

Key Capabilities:
-----------------
1. **Send checks** (`sale.order`, Send button):

   - A quotation without a payment term cannot be sent; the missing term is
     named.
   - A quotation holding a special item is sent only on a term whose advance
     reaches the company's special-item minimum.
   - A term other than the customer's default needs the Finance Manager's
     approval on the quotation.
   - A quotation to a customer on the credit watch list needs the Operations
     Manager's or the Finance Manager's approval.

2. **Approvals on the quotation** (`sale.order`): each approval records who
   approved and when, and lapses when the term or the customer changes.

3. **Special marking** (`sale.order.line`, `purchase.order.line`): the
   product's special marking shows on quotation, order and purchase lines.

4. **Integration**: uses the advance share of payment terms, the special mark
   of products and the customer credit state from Customer Credit Control;
   instalment terms for large projects stay standard payment term lines.
    """,
    "author": "OdooTec",
    "website": "https://www.odootec.com",
    "license": "Other proprietary",
    "depends": [
        "sale_management",
        "purchase",
        "odt_customer_credit_control",
    ],
    "data": [
        "security/security.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
        "views/res_company_views.xml",
    ],
    "installable": True,
    "application": False,
}
