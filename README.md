# Kranthi High School (KHS) — Billing & Receipt Management System

A complete, offline-capable fee billing and receipt generation application designed for **Windows PC** with future readiness for **Android Mobile**.

---

## 🚀 Quick Start (One-Click Launch)

Simply double-click the included launcher in this folder:
```
START_KHS_BILLING.bat
```
This automatically launches the server using the **self-contained portable runtime** (no external Python or node installation required) and opens your browser directly at:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🔑 Login Accounts (3-Tier RBAC)

| Tier | Role | Username | Password | Permissions |
|---|---|---|---|---|
| **T1** | Super Admin | `superadmin` | `admin123` | Full master control, system audit, fee structures, instant discount approvals, user management |
| **T2** | Admin / Principal | `admin` | `admin123` | Fee structure adjustments, review & approve/reject front desk discount requests, daily collection oversight |
| **T3** | Front Desk / Billing Desk | `frontdesk` | `desk123` | Student lookup, installment payments, receipt generation, student admission with discount requests |

---

## 🌟 Implemented Features

### 1. Admission with Day Scholar / Residential & Optional Transport
- Choose between **Day Scholar** or **Residential (Hostel / Boarding)**.
- For Day Scholars, check **"Opt for School Transport / Bus Facility"** to enable the transport fee input and route details.
- Standard class base fee is automatically retrieved from the Fee Master.

### 2. Discount Approval Workflow (T3 $\rightarrow$ T1/T2)
- Front desk (T3) can enter a requested discount and justification (e.g. Sibling discount, merit aid).
- The admission is recorded with discount status `Pending`.
- T1 and T2 see a live notification badge and approval desk where they can **Approve** (with full or adjusted amount) or **Reject**.
- Student's total agreed annual fee and subsequent installments automatically adjust.

### 3. Flexible Installment Engine & Balance Tracking
- Parents can pay in **3, 4, 5, or ad-hoc installments**.
- The system accurately calculates:
  - Total Agreed Annual Fee
  - Previously Paid Amount
  - Amount Paid Today (Installment #N)
  - **Remaining Balance Due**
- Payment Modes: **Cash, UPI / QR, Cheque, Bank Transfer / NEFT**.

### 4. Official Printable Receipt & Free WhatsApp Delivery
- **Instant Printable Receipt**: Branded with Kranthi High School logo, affiliation details, student information, and authorized signature block.
- **48-Hour Secure Digital Download**: Generates a tamper-proof web token link.
- **100% Free WhatsApp Integration**: Front desk can click "Send to Parent on WhatsApp" to open WhatsApp Web/Desktop with a pre-formatted message and receipt link pre-filled.

### 5. 9:00 PM IST End-of-Day Summary & Financial Reports
- Real-time aggregation of today's collections.
- Clear split: **Cash in Hand vs. UPI / QR vs. Cheque / Bank Transfer**.
- Ready-to-copy summary message for WhatsApp or SMS dispatch to Super Admin and Admin.

### 6. Bulletproof Offline Backup
- Master SQLite database stored in `khs_billing.db`.
- One-click **"Backup DB"** button in the header bar.
- Completely free of vendor fees, cloud lock-ins, or monthly subscription costs.
