# Supplier Payment Control (Domain Layer)

<p align="center">
  <img src="https://www.odootec.com/logo.png" alt="OdooTec Logo" width="200"/>
</p>

<p align="center">
  <strong>Pays vendors only for what was ordered and received, once, after the right approvals</strong><br/>
  Matched bills only • Approval levels by amount • Duplicate block • Shareholders off payroll
</p>

<p align="center">
  <strong>Author:</strong> OdooTec <br/>
  <strong>Official Website:</strong> <a href="https://www.odootec.com">www.odootec.com</a> • <strong>Inquiries:</strong> <a href="mailto:info@odootec.com">info@odootec.com</a>
</p>

<p align="center">
  <a href="#what-this-module-does">What This Module Does</a> •
  <a href="#architectural-position">Architecture</a> •
  <a href="#payment-rules">Payment Rules</a> •
  <a href="#models--extensions">Models</a> •
  <a href="#ui--views">Views</a> •
  <a href="#installation--configuration">Installation</a> •
  <a href="#support">Support</a>
</p>

---

> **IMPORTANT NOTICE FOR TECHNICAL TEAM**
>
> Every vendor payment check goes through `account.payment.action_post`.
> Payments registered from bills carry the context key
> `defer_payment_approval`: a payment that still needs an approval or a
> duplicate release is then left in draft for the approvers instead of
> failing the registration. Never post vendor payments around `action_post`.
> When Register Payment generates the entry while creating the payment (a
> payment method with an outstanding account), standard Odoo 19 marks it In
> Process without calling `action_post`; the `_generate_journal_entry`
> override puts a waiting payment back to draft with its entry unposted.

---

## What This Module Does

`odt_supplier_payment_control` is the **Supplier Payment Control Module (Domain Layer)** of the RVK implementation. It controls what leaves the bank towards vendors:

1. **Matched bills only**: a vendor bill whose Should Be Paid (three-way match) is not Yes cannot be paid, singly or in a batch; the refusal names the bill.
2. **Service bills exempt**: a service bill raised without a purchase order is paid without a match.
3. **Exceptions released by Finance**: the Finance Manager sets an Exception bill to Yes (standard Should Be Paid field); it is then paid through the approval levels.
4. **Approval levels by amount**: above each company threshold a vendor payment needs the Finance Manager, then also the Operations Manager, then also the Chief Executive; each approval stores the approver and the date.
5. **Duplicate block**: a payment with the same vendor, amount and reference as an earlier one is blocked until an administrator releases it; the release is logged on both payments.
6. **Trusted accounts and shareholders**: a vendor payment to an untrusted bank account is refused, and a payment to a shareholder cannot post to a payroll expense account.
7. **Import documents**: the packing list and weight certificate of an import shipment are attached to the vendor bill (standard attachments).

---

## Architectural Position

```
┌─────────────────────────────────────────────────────────────┐
│                         CONSUMERS                           │
│               (none yet in the RVK module set)              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       DOMAIN LAYER                          │
│               odt_supplier_payment_control                  │
│   • payment.approval (one approval per level)               │
│   • account.payment / account.batch.payment extensions      │
│   • account.payment.register (Register Payment) extension   │
│   • res.company / res.partner / account.account / bills     │
└──────────────────────────────┬──────────────────────────────┘
                               │ inherits
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         ODOO CORE                           │
│  account_accountant, account_batch_payment, purchase,       │
│  account_3way_match (Vendor Bill: Release to Pay)           │
└─────────────────────────────────────────────────────────────┘
```

---

## Payment Rules

### Paying a vendor bill

| Bill | Register Payment or batch |
| :--- | :--- |
| Should Be Paid = Yes | Paid |
| Should Be Paid = No or Exception | Refused, naming the bill |
| Service bill without a purchase order | Paid (exempt) |
| Customer invoice | Standard |

### Approval levels (per company)

| Amount in company currency | Approvals needed before posting |
| :--- | :--- |
| up to threshold 1 (included) | none |
| above threshold 1 | Finance Manager |
| above threshold 2 | Finance Manager, Operations Manager |
| above threshold 3 | Finance Manager, Operations Manager, Chief Executive |

A threshold of 0 leaves its level unused. Levels are approved in order; the Approve button gives the next level, and only its group can give it (Accounting / Administrator, Payment approver (Operations), Payment approver (Chief Executive)).

### Approval status

| Status | Meaning |
| :--- | :--- |
| To Approve: … | waits for that level |
| Approved | every level needed is given; can be posted |
| Blocked | repeats an earlier payment; waits for an administrator |
| Posted | in process or paid |

### Other refusals at posting

| Situation | Result |
| :--- | :--- |
| Recipient bank account not trusted | Refused |
| Shareholder payment on an account marked Payroll Expense Account | Refused, naming the account; post it to the shareholder's account |

---

## Models & Extensions

### 1. `payment.approval` (Payment Approval)

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `payment_id` | `Many2one` | The vendor payment approved. |
| `level` | `Selection` | Finance Manager, Operations Manager or Chief Executive. |
| `user_id` | `Many2one` | The approver. |
| `date` | `Datetime` | When the approval was given. |
| `company_id` | `Many2one` | The payment's company (multi-company rule). |
| `amount` | `Monetary` | The payment amount (related). |
| `partner_id` | `Many2one` | The vendor (related). |

### 2. `account.payment` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `approval_state` | `Selection` | Draft, To Approve per level, Approved, Posted, Blocked. |
| `approval_ids` | `One2many` | The approvals given. |
| `duplicate_of_id` | `Many2one` | The earlier payment this one repeats. |
| `is_duplicate_released` | `Boolean` | Released by an administrator. |

### 3. `res.company` Extension

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `approval_threshold_1` | `Monetary` | Finance Manager approval above. |
| `approval_threshold_2` | `Monetary` | Operations Manager approval above. |
| `approval_threshold_3` | `Monetary` | Chief Executive approval above. |

### 4. `res.partner` and `account.account` Extensions

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `is_shareholder` | `Boolean` | The contact is a shareholder. |
| `is_payroll` | `Boolean` | The account is a payroll expense account. |

### 5. `account.move`, `account.payment.register` and `account.batch.payment` Extensions

No new field: the bill tells whether it is cleared to pay; Register Payment and batch validation refuse bills that are not.

---

## UI & Views

1. **Vendor payment form**: approval status, **Approve** (next level's approver) and **Release Duplicate** (administrators) buttons, a red banner on a blocked duplicate, the destination account, and an Approvals tab.
2. **Payments list and search**: approval status column; filters To Approve and Blocked Duplicates.
3. **Accounting → Vendors → Payment Approvals**: every approval given, by level and approver.
4. **Company form → Payment Approval tab**: the three thresholds.
5. **Contact form → Sales & Purchase**: Shareholder. **Account form**: Payroll Expense Account.

---

## Dependencies

| Module | Why it is required |
| :--- | :--- |
| `account_accountant` | Vendor bills and payments. |
| `account_batch_payment` | Batch payments. |
| `purchase` | Bills matched to purchase orders. |
| `account_3way_match` | Should Be Paid (three-way matching) on vendor bills. |

External Python packages: none.

---

## Installation & Configuration

1. Add the modules folder to the `addons_path` and update the Apps list.
2. Install **Supplier Payment Control** (it installs Vendor Bill: Release to Pay and Batch Payment).
3. Per company (Company form → Payment Approval): set the three thresholds RVK confirms (REQ-131).
4. Give the Operations Manager **Vendor Payment Approval / Payment approver (Operations)** and the Chief Executive **Payment approver (Chief Executive)**; the Finance Manager needs **Accounting / Administrator**.
5. Mark shareholders on their contact and payroll expense accounts on the chart of accounts; mark verified vendor bank accounts as trusted.

---

## Known Limitations

* Until a company sets its thresholds, no approval is required.
* Approvals are given in order; one user holding several approver groups approves one level per click.
* Releasing a duplicate does not reset the earlier payment; the release is recorded on both.
* A daily payment run, standing bank instructions and automatic payment of recurring bills are not included.

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
