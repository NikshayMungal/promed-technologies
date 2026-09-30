# Debtors Desk — Streamlit starter project

A runnable local review workbench inspired by the Debtors Clerk responsibilities supplied. Fictional demonstration data only; not affiliated with Promed Technologies.

## Windows PowerShell: start here

Install Python 3.11 or newer. Extract the ZIP, open PowerShell in this folder, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL shown in the terminal. Select **Import data → Load fictional demonstration data**, then open Overview, Receipt matching, and Statements & reminders.

No PowerShell activation-policy change is required. SQLite is the default so the demonstration runs without a database server. To use your MySQL database, follow the section below.

## Included functionality

- Validated CSV imports with exact header order, date and currency checks, duplicate-ID and customer-reference checks.
- Persistent, complete snapshots with import history.
- Outstanding and overdue totals, days-past-due ageing and credit-limit flags.
- Receipt proposals based on exact invoice reference or balanced remittance splits.
- Partial payments, split remittances, duplicate-allocation prevention within a batch, customer mismatch and unknown-reference exceptions.
- CSV age analysis and allocation-review exports, plain-text customer statements and reminder drafts.
- MySQL connection support and a zero-configuration SQLite demonstration mode.
- Unit tests and a GitHub Actions test workflow.

## Data contract

Use files in sample_data as templates. Export data from Sage and map its columns to these exact headers; this application does not assume a specific Sage export layout. Dates: YYYY-MM-DD. Amounts: non-negative decimal numbers with no currency symbol or thousands separator and at most two decimal places. Currency: ZAR only. Identifiers are case-sensitive.

Import customers, invoices and receipts together as one complete snapshot. Remittances are optional. A header-only receipts file is allowed when you only want reporting. Unknown customer links fail validation. Receipt customer_id and reference may be blank, but matching then requires investigation. Credit notes, refunds, negative transactions, foreign currencies and OCR extraction are not supported.

Invoice outstanding_amount must be the OPEN balance from Sage at the stated snapshot date. Do not upload original invoice amounts as outstanding balances where payments already exist. Receipt inputs must represent an UNPOSTED review batch, excluding payments already reflected in those balances. The app cannot determine from CSV alone whether a bank transaction has already been posted in Sage. It does not deduplicate bank transactions across different snapshots.

Reports use the imported snapshot date, not a reconstructed historical ledger. Matching proposals never reduce the imported balance. Refresh the Sage export after actual posting. Do not import this review worksheet directly into Sage: an approved, version-specific connector/import mapping is still required.

## Sample test walkthrough (snapshot date 2026-09-30)

1. Overview should show **R27,500 outstanding**, **R15,500 overdue** and **5 open invoices**.
2. Receipt matching should show **R27,750 imported**, **R19,000 proposed**, **R8,750 requiring review**.
3. PAY001 proposes R5,000 to INV001. PAY002 splits R12,000 to INV003 and R1,000 to INV004. PAY003 proposes a partial R1,000 to INV005.
4. PAY004 requires identity/reference investigation. PAY005 cannot reuse INV001's reserved balance. PAY006 has a customer mismatch.
5. C001's statement still shows R8,000: proposals are not posted payments.
6. Upload invalid_receipts.csv alongside the other sample inputs: the negative amount must be rejected without saving a snapshot.

## MySQL setup

Create a separate application database in MySQL Workbench using an administrator account:

```sql
CREATE DATABASE debtors_automation CHARACTER SET utf8mb4;
CREATE USER 'debtors_app'@'localhost' IDENTIFIED BY 'CHANGE_THIS_PASSWORD';
GRANT SELECT, INSERT, CREATE ON debtors_automation.* TO 'debtors_app'@'localhost';
```

Edit .env:

```ini
DB_MODE=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=debtors_automation
MYSQL_USER=debtors_app
MYSQL_PASSWORD=your_actual_password
```

Restart the app. It creates its own debtors_snapshots table. It never connects directly to Sage database tables. Switching database modes does not migrate existing snapshots. For remote MySQL, configure the approved network access and TLS settings with your administrator; the provided example is local-only.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## GitHub

Create an empty repository and upload the extracted project contents, including the .github folder. Keep .env, actual customer exports, local databases and credentials out of GitHub. Sample records are fictional. The included workflow runs checks on pushes and pull requests. A GitHub repository alone does not host the running app or its database.

## Scope and deployment

This is a functional prototype for local use, not a complete replacement for Sage or a finished production finance system. There is no live Sage connection, bank feed, scheduled job, outgoing email, PDF statement generation, document archive, credit-note processing, approval workflow or user authentication. A local snapshot history is not a tamper-proof audit trail. MySQL stores JSON snapshots, not a general ledger.

Before company deployment, add authenticated access, roles, backups, approved Sage integration, durable storage and reviewed posting controls. Keep the default local binding for this version. Accounting decisions, disputes, credit changes, month-end sign-off and actual postings remain with authorised staff.

## Implementation references

- Streamlit execution: https://docs.streamlit.io/develop/concepts/architecture/run-your-app
- SQLAlchemy MySQL support: https://docs.sqlalchemy.org/en/20/dialects/mysql.html
- Sage 300 developer resources: https://developer.sage.com/300/

Dependency ranges in requirements.txt permit compatible releases; record a pinned dependency set after validating your own deployment environment.
