# Quotation Payment Terms (Domain Layer)

<p align="center">
  <img src="https://www.odootec.com/logo.png" alt="OdooTec Logo" width="200"/>
</p>

<p align="center">
  <strong>A quotation leaves only on a payment term that is agreed, approved and fit for what it sells</strong><br/>
  Send checks • Finance Manager term approval • Special-item minimum advance • Watch-list sending approval
</p>

<p align="center">
  <strong>Author:</strong> OdooTec <br/>
  <strong>Official Website:</strong> <a href="https://www.odootec.com">www.odootec.com</a> • <strong>Inquiries:</strong> <a href="mailto:info@odootec.com">info@odootec.com</a>
</p>

<p align="center">
  <a href="#what-this-module-does">What This Module Does</a> •
  <a href="#architectural-position">Architecture</a> •
  <a href="#send-rules">Send Rules</a> •
  <a href="#models--extensions">Models</a> •
  <a href="#ui--views">Views</a> •
  <a href="#installation--configuration">Installation</a> •
  <a href="#support">Support</a>
</p>

---

> **IMPORTANT NOTICE FOR TECHNICAL TEAM**
>
> The checks live in `sale.order._check_quotation_send()`, called by the
> `action_quotation_send` override before `super()`. Approval fields are written
> only by `action_approve_payment_term()` and `action_approve_sending()`, which
> check the right first; never write them another way.

---

## What This Module Does

`odt_quotation_payment_terms` is the **Quotation Payment Terms Module (Domain Layer)** of the RVK implementation. It stops quotations from leaving on terms agreed informally and found later:

1. **Payment term required**: a quotation without a payment term cannot be sent, and the message names the missing term.
2. **Default term approved, others by the Finance Manager**: the customer's default payment term is approved; any other term is approved by the Finance Manager on the quotation, with the approver and date shown.
3. **Special-item minimum advance**: a quotation holding a special item is sent only on a term whose advance reaches the company's minimum for special items.
4. **Watch-list sending approval**: a quotation to a customer on the credit watch list is sent only after the Operations Manager or the Finance Manager approves it, with the approver and date shown.
5. **Special marking down the chain**: the product's special marking shows on quotation, order and purchase lines.
6. **Integration**: extends Sales (sending quotations) and Purchase (order lines), on top of Customer Credit Control.

---

## Architectural Position

```
┌─────────────────────────────────────────────────────────────┐
│                     CONSUMERS (LATER)                       │
│                           none                              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       DOMAIN LAYER                          │
│                odt_quotation_payment_terms                  │
│   • sale.order (send checks, approvals)                     │
│   • sale.order.line / purchase.order.line (special mark)    │
│   • res.company (special-item minimum advance)              │
└──────────────────────────────┬──────────────────────────────┘
                               │ reads advance %, special mark, credit state
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               odt_customer_credit_control                   │
│               sale_management, purchase                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Send Rules

### Checks when the salesperson presses Send (quotations only)

| Order | Situation | Result |
| :--- | :--- | :--- |
| 1 | No payment term | Refused, naming the missing term |
| 2 | A special line, and the term's advance is below the company's special-item minimum | Refused, naming the minimum |
| 3 | The term is not the customer's default and is not approved | Refused until the Finance Manager approves |
| 4 | The customer is on the credit watch list and sending is not approved | Refused until the Operations or Finance Manager approves |
| — | Approved term (or the customer's default) and a normal customer | Sent exactly as standard |

### Approvals

| Approval | Who | Recorded | Lapses when |
| :--- | :--- | :--- | :--- |
| Payment term | Finance Manager (Accounting / Administrator) | approver and date | the term or the customer changes |
| Sending to a watch-listed customer | Quotation Send Approver (Operations Manager, Finance Manager) | approver and date | the customer changes |

The Sales Manager does not approve either; a term approval does not lift the special-item minimum.

---

## Models & Extensions

### 1. `sale.order` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `term_approved_by_id` | `Many2one` | Finance Manager who approved a non-default term. |
| `term_approval_date` | `Datetime` | When the term was approved. |
| `send_approved_by_id` | `Many2one` | Manager who approved sending to a watch-listed customer. |
| `send_approval_date` | `Datetime` | When sending was approved. |
| `is_term_approval_needed` | `Boolean` | The term waits for the Finance Manager (computed). |
| `is_send_approval_needed` | `Boolean` | Sending waits for approval (computed). |

### 2. `res.company` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `special_min_advance` | `Float` | Minimum advance (%) for quotations holding special items; 0 = none. |

### 3. `sale.order.line` and `purchase.order.line` Extensions

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `is_special` | `Boolean` | The product's special marking (related, read-only). |

---

## UI & Views

1. **Quotation**: **Approve Payment Term** (Finance Manager) and **Approve Sending** (send approvers) buttons, a red banner while an approval waits, and the approvals in the Other Info tab.
2. **Quotation and order lines**: an optional Special Item column.
3. **Purchase order lines**: an optional Special Item column.
4. **Company form → Credit Control tab**: Special Items Minimum Advance (%).

---

## Dependencies

| Module | Why it is required |
| :--- | :--- |
| `sale_management` | Quotations, payment terms and sending. |
| `purchase` | Purchase order lines carry the special marking. |
| `odt_customer_credit_control` | Advance % on payment terms, the special mark on products, the customer credit state. |

External Python packages: none.

---

## Installation & Configuration

1. Add the modules folder to the `addons_path` and update the Apps list.
2. Install **Quotation Payment Terms** (installs Customer Credit Control if missing).
3. Give the Operations Manager and the Finance Manager **Quotation Approval / Quotation Send Approver**; Finance Managers also need **Accounting / Administrator**.
4. Per company (Company form → Credit Control): set the special items minimum advance. Per payment term: set the advance %. Per customer: set the default payment term (Sales & Purchase tab).
5. Instalment terms for large projects are standard payment terms with one line per milestone.

---

## Known Limitations

* The special marking shows on purchase lines; manufacturing orders do not show it (Manufacturing is not a dependency).
* **Mark as Sent** (without an email) is standard and not checked.
* Instalment lines are not linked to project deliverables; due dates come from the payment term lines.
* A confirmed order re-sent (order confirmation email) is not checked again.

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
