# Small Business Accounting & Inventory System

A lightweight Python web application for small-business accounting, inventory, customer/supplier accounts, payments, transactions, and daily reporting.

This GitHub edition is intentionally distributed as a **flat repository** with a single Python application file. It is a cleaned and simplified version suitable for learning, demonstration, and small local deployments.

## Features

- First-run administrator setup
- Secure password hashing
- Login/logout
- Inventory and stock levels
- Purchase and sale transactions
- Customer/supplier accounts
- Account balances
- Payment recording
- Low-stock alerts
- Daily sales and purchase reports
- SQLite database created automatically
- Responsive browser interface
- No default public password

## Files

```text
accounting_app.py
requirements.txt
README.md
LICENSE
.gitignore
```

The application creates `accounting.db` automatically on first run. The database is excluded from GitHub by `.gitignore`.

## Installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
```

Activate the environment, then install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python accounting_app.py
```

Open:

```text
http://127.0.0.1:8000
```

On first launch, the application redirects to `/setup` so you can create the first administrator.

## Security

Before any non-local deployment, define a strong Flask secret key:

### Windows PowerShell

```powershell
$env:ACCOUNTING_SECRET_KEY="replace-with-a-long-random-secret"
python accounting_app.py
```

### Linux / macOS

```bash
export ACCOUNTING_SECRET_KEY="replace-with-a-long-random-secret"
python accounting_app.py
```

For internet-facing production use, run behind a production WSGI server and HTTPS. The built-in Flask development server is intended for local development only.

## Balance Convention

For customer/supplier accounts:

- Sales increase the balance.
- Purchases decrease the balance.
- Money received from the account decreases the balance.
- Money paid to the account increases the balance.

A positive balance therefore means the account owes the business under this simplified convention.

## Reporting Note

The daily report's `sales - purchases` figure is a simple cash-flow-style indicator. It is **not** a full accounting profit calculation and does not include cost of goods sold, depreciation, taxes, expenses, or accrual adjustments.

## Original Project Cleanup

The supplied project archive contained a Django application together with a complete local virtual environment, Python cache files, and a local SQLite database. Those generated/local files are not appropriate for a public GitHub repository.

This edition keeps the core accounting workflow in a compact single-file application so the repository can remain flat, as requested.

## License

MIT License.
