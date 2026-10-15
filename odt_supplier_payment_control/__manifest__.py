# Part of OdooTec. See LICENSE file for full copyright and licensing details.

{
    "name": "Supplier Payment Control",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Pays vendors only for matched bills, once, after the approvals each amount requires.",
    "description": """
Supplier Payment Control
========================
Controls what leaves the company's bank accounts towards vendors. Bills that
do not match their purchase order and receipt cannot be paid, vendor payments
wait for the approvals their amount requires, a payment repeating an earlier
one is blocked until an administrator releases it, and payments to
shareholders never post to payroll expense accounts.

Key Capabilities:
-----------------
1. **Pay matched bills only** (`account.move`, `account.payment.register`,
   `account.batch.payment`):

   - Registering a payment, singly or in a batch, is refused for a vendor
     bill whose Should Be Paid (three-way match) is not Yes, naming the bill.
   - Service bills raised without a purchase order are exempt; a bill in
     Exception is paid once the Finance Manager sets it to Yes.

2. **Approval levels by amount** (`account.payment`, `payment.approval`):

   - Each company sets three thresholds: above the first a vendor payment
     needs the Finance Manager, above the second also the Operations
     Manager, above the third also the Chief Executive.
   - A payment cannot be posted until every level is approved; each
     approval stores the approver and the date.

3. **Duplicate block**:

   - A vendor payment with the same vendor, amount and reference as an
     earlier one is blocked; only an administrator releases it, and the
     release is logged on both payments.

4. **Trusted accounts and shareholders**:

   - A vendor payment to a recipient bank account that is not trusted is
     refused.
   - A payment to a contact marked shareholder cannot post to an account
     marked as a payroll expense account.
    """,
    "author": "OdooTec",
    "website": "https://www.odootec.com",
    "license": "Other proprietary",
    "depends": [
        "account_accountant",
        "account_batch_payment",
        "purchase",
        "account_3way_match",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/payment_approval_views.xml",
        "views/account_payment_views.xml",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
        "views/account_account_views.xml",
    ],
    "installable": True,
    "application": False,
}
