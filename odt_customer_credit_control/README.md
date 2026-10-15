# Customer Credit Control (Domain Layer)

<p align="center">
  <img src="https://www.odootec.com/logo.png" alt="OdooTec Logo" width="200"/>
</p>

<p align="center">
  <strong>Keeps sales within the company's credit policy, every month and for every customer</strong><br/>
  Monthly credit ceiling • Customer caps • Finance Manager approval • Credit hold and block
</p>

<p align="center">
  <strong>Author:</strong> OdooTec <br/>
  <strong>Official Website:</strong> <a href="https://www.odootec.com">www.odootec.com</a> • <strong>Inquiries:</strong> <a href="mailto:info@odootec.com">info@odootec.com</a>
</p>

<p align="center">
  <a href="#what-this-module-does">What This Module Does</a> •
  <a href="#architectural-position">Architecture</a> •
  <a href="#credit-rules">Credit Rules</a> •
  <a href="#models--extensions">Models</a> •
  <a href="#ui--views">Views</a> •
  <a href="#installation--configuration">Installation</a> •
  <a href="#support">Support</a>
</p>

---

> **IMPORTANT NOTICE FOR TECHNICAL TEAM**
>
> Credit sales are read from the `credit.exposure` SQL view everywhere (the
> confirmation check, the quotation share and the report). Never total orders
> another way, and refresh the view's cache (`invalidate_model()`) before
> reading it inside a transaction: its row ids are positional.

---

## What This Module Does

`odt_customer_credit_control` is the **Credit Control Module (Domain Layer)** of the RVK implementation. It stops credit sales from running past the company's monthly ceiling and each customer's cap, and stops new business with customers who have old overdue invoices:

1. **Monthly credit ceiling and customer caps**: confirming a credit order that would take the customer over its monthly cap, or the company over its monthly ceiling, waits for the Finance Manager's approval.
2. **Finance Manager approval**: the Finance Manager approves with a reason; the order confirms and records who approved, when and why.
3. **Customer credit states**: normal, watch list, credit hold and absolute block, kept by a nightly check and by Finance.
4. **Blocks**: customers on hold cannot confirm orders or receive deliveries; customers under block also get no quotations and no invoices.
5. **Weekly watch list**: Finance Managers receive the watch-listed and held customers, largest overdue first.
6. **Integration**: extends Sales (order confirmation), Inventory (delivery validation) and Accounting (customer invoice posting, payment terms).

---

## Architectural Position

```
┌─────────────────────────────────────────────────────────────┐
│                     CONSUMERS (LATER)                       │
│                odt_quotation_payment_terms                  │
└──────────────────────────────┬──────────────────────────────┘
                               │ reads the credit state, advance and special marks
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       DOMAIN LAYER                          │
│                odt_customer_credit_control                  │
│   • credit.exposure (monthly totals, SQL view)              │
│   • credit.decision (Finance decision dialog)               │
│   • res.partner / res.company / sale.order extensions       │
│   • account.payment.term / product.template extensions      │
└──────────────────────────────┬──────────────────────────────┘
                               │ inherits
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         ODOO CORE                           │
│              sale_management, stock, account                │
└─────────────────────────────────────────────────────────────┘
```

---

## Credit Rules

### Credit sales

| Counted | Not counted |
| :--- | :--- |
| Confirmed orders whose payment term advance is below 100% | Orders on a 100% advance term |
| Line totals with VAT, in the company currency | Down-payment lines |
| The calendar month of confirmation, per company | Lines of products that are special **and** excluded from credit totals |

### At confirmation

| Situation | Result |
| :--- | :--- |
| Customer on credit hold or absolute block | Refused |
| Customer's month total + order > cap (cap % × ceiling) | Waits for approval |
| Company's month total + order > ceiling | Waits for approval |
| Exactly on the cap or the ceiling | Confirms |
| Approved by the Finance Manager | Confirms |

### Credit states

| State | Set by | Lifted by | Blocks |
| :--- | :--- | :--- | :--- |
| Watch List | nightly check (overdue invoice) or Finance (flag with a reason) | nightly check when nothing is overdue and no flag remains | nothing here (the send approval is in `odt_quotation_payment_terms`) |
| Credit Hold | nightly check (an invoice overdue more than the company's hold days, 60 by default) or the Finance Manager | the Finance Manager only; the same invoices never set it again | order confirmation, delivery validation |
| Absolute Block | the Finance Manager | the Finance Manager | quotations, order confirmation, deliveries, customer invoices |

---

## Models & Extensions

### 1. `credit.exposure` (Monthly Credit Exposure)

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `partner_id` | `Many2one` | The customer (commercial entity). |
| `company_id` | `Many2one` | The selling company. |
| `month` | `Date` | First day of the month of confirmation. |
| `credit_sales` | `Monetary` | Credit sales of the month, with VAT. |
| `credit_ceiling` | `Monetary` | The company's monthly ceiling. |
| `share_pct` | `Float` | Credit sales as a share of the ceiling. |
| `cap_pct` | `Float` | The customer's cap. |

### 2. `credit.decision` (Credit Decision)

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `decision` | `Selection` | Watch list, remove flag, hold, lift hold, block, lift block, approve. |
| `reason` | `Char` | Why; recorded on the customer or the order. |
| `partner_ids` | `Many2many` | The customers decided on. |
| `order_ids` | `Many2many` | The orders approved. |

### 3. `res.partner` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `credit_state` | `Selection` | Normal, Watch List, Credit Hold, Absolute Block. |
| `credit_cap_pct` | `Float` | Monthly cap as a share of the company ceiling. |
| `is_credit_flagged` | `Boolean` | Flagged by Finance. |
| `credit_state_reason` | `Char` | Reason of the last credit decision. |
| `hold_cleared_invoice_ids` | `Many2many` | Invoices a lifted hold covered. |

### 4. `res.company` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `credit_ceiling` | `Monetary` | Monthly credit ceiling. |
| `hold_days` | `Integer` | Overdue days that trigger a credit hold. |

### 5. `sale.order` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `credit_approval` | `Selection` | Not Needed, Waiting for Approval, Approved. |
| `credit_approval_note` | `Char` | Approval reason. |
| `credit_approved_by_id` | `Many2one` | Approving Finance Manager. |
| `credit_approval_date` | `Datetime` | Approval date. |
| `credit_share_pct` | `Float` | The customer's share of the ceiling this month. |
| `credit_cap_pct` | `Float` | The customer's cap (related). |

### 6. `account.payment.term` and `product.template` Extensions

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `advance_pct` | `Float` | Share paid in advance; 100 = not a credit sale. |
| `is_special` | `Boolean` | Special item. |
| `is_credit_excluded` | `Boolean` | A special item left out of credit totals. |

---

## UI & Views

1. **Sales → Reporting → Credit Exposure**: this month's credit sales per customer and company, with share and cap.
2. **Customer form → Credit Control tab**: the credit state, the Finance buttons (watch list, hold, lift, block), the cap and the invoices a lifted hold covered.
3. **Quotation**: the customer's share and cap beside the payment term; a red banner and an **Approve Credit** button (Finance Manager) when an order waits.
4. **Company form → Credit Control tab**: ceiling and hold days. **Payment term**: advance %. **Product**: Special Item and Excluded from Credit Totals.
5. **Contacts search**: filters Credit Watch List and Credit Hold or Block.

---

## Dependencies

| Module | Why it is required |
| :--- | :--- |
| `sale_management` | Orders and their confirmation. |
| `stock` | Delivery validation block. |
| `account` | Overdue invoices, payment terms, customer invoice posting. |

External Python packages: none.

---

## Installation & Configuration

1. Add the workspace `addons` folder to the `addons_path` and update the Apps list.
2. Install **Customer Credit Control**.
3. Finance Managers need **Accounting / Administrator**; Finance users who flag customers need **Accounting / Invoicing**.
4. Per company (Company form → Credit Control): set the monthly ceiling and the hold days. Per customer: set the cap. Per payment term: set the advance %. Per product: mark special and excluded items.
5. The nightly check and the weekly email are scheduled actions (Settings → Technical → Scheduled Actions).

---

## Known Limitations

* Returned instrument deposits (REQ-026) do not yet put a customer on the watch list; they will once that module exists.
* The weekly email goes to the company's Finance Managers (users with an email address).
* Credit totals use the confirmation month in UTC.
* The module extends three apps (Sales, Inventory, Accounting) as one credit policy; splitting them into bridge modules is a design decision for the SDD.

---

## Licensing & Terms

This module is licensed under the **OdooTec Development Licence (ODTL-1), version 1.4**. See the `LICENSE` file.

* Ownership, commercial and distribution rights are held exclusively by **OdooTec**.
* Deployment, modification and use are governed by the signed agreement between OdooTec and the licensed client.
* Redistribution, sublicensing or publication of this source code without OdooTec's written permission is prohibited.

---

## Support

For technical assistance or inquiries:
* **Vendor**: OdooTec
* **Author**: OdooTec
* **Website**: [https://www.odootec.com](https://www.odootec.com)
* **Email**: [info@odootec.com](mailto:info@odootec.com)
