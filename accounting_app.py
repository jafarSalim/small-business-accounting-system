"""
Lightweight Accounting & Inventory System
-----------------------------------------
A single-file Flask application for small-business accounting, inventory,
customer accounts, payments, transactions, and daily reports.

This version is intentionally flat so it can be uploaded to GitHub without
nested source folders.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "accounting.db"

app = Flask(__name__)
app.secret_key = os.environ.get("ACCOUNTING_SECRET_KEY", "change-this-secret-key-before-production")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT UNIQUE,
            quantity REAL NOT NULL DEFAULT 0,
            purchase_price REAL NOT NULL DEFAULT 0,
            sale_price REAL NOT NULL DEFAULT 0,
            reorder_level REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            notes TEXT,
            opening_balance REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK(kind IN ('sale','purchase')),
            product_id INTEGER NOT NULL,
            account_id INTEGER,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            total REAL NOT NULL,
            transaction_date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('received','paid')),
            payment_date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def scalar(query: str, params=()):
    row = get_db().execute(query, params).fetchone()
    return row[0] if row else 0


def account_balance(account_id: int) -> float:
    db = get_db()
    opening = scalar("SELECT opening_balance FROM accounts WHERE id=?", (account_id,)) or 0
    sales = scalar(
        "SELECT COALESCE(SUM(total),0) FROM transactions WHERE account_id=? AND kind='sale'",
        (account_id,),
    ) or 0
    purchases = scalar(
        "SELECT COALESCE(SUM(total),0) FROM transactions WHERE account_id=? AND kind='purchase'",
        (account_id,),
    ) or 0
    received = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payments WHERE account_id=? AND direction='received'",
        (account_id,),
    ) or 0
    paid = scalar(
        "SELECT COALESCE(SUM(amount),0) FROM payments WHERE account_id=? AND direction='paid'",
        (account_id,),
    ) or 0
    # Positive = customer owes the business; negative = business owes the account.
    return float(opening + sales - purchases - received + paid)


BASE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} - Accounting System</title>
<style>
:root{--bg:#f4f7fb;--card:#fff;--text:#1f2937;--muted:#6b7280;--primary:#2563eb;--danger:#dc2626;--border:#e5e7eb}
*{box-sizing:border-box} body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text)}
nav{background:#111827;color:#fff;padding:12px 22px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
nav a{color:#fff;text-decoration:none} nav .brand{font-weight:700;margin-right:auto}
.container{max-width:1180px;margin:24px auto;padding:0 16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px;margin-bottom:18px;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.stat{font-size:28px;font-weight:700}.muted{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;background:#fff} th,td{padding:10px;border-bottom:1px solid var(--border);text-align:left}
th{background:#f9fafb} input,select,textarea{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;margin:5px 0 12px}
button,.btn{background:var(--primary);color:#fff;border:0;border-radius:8px;padding:9px 14px;text-decoration:none;display:inline-block;cursor:pointer}
.btn-danger{background:var(--danger)} .btn-secondary{background:#4b5563}
.flash{padding:10px;border-radius:8px;background:#dbeafe;margin-bottom:12px}
.row{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}@media(max-width:700px){.row{grid-template-columns:1fr}}
.right{text-align:right}.positive{color:#b91c1c;font-weight:700}.negative{color:#047857;font-weight:700}
</style>
</head>
<body>
{% if session.get('user_id') %}
<nav>
  <div class="brand">Accounting System</div>
  <a href="{{ url_for('dashboard') }}">Dashboard</a>
  <a href="{{ url_for('products') }}">Inventory</a>
  <a href="{{ url_for('accounts') }}">Accounts</a>
  <a href="{{ url_for('transactions') }}">Transactions</a>
  <a href="{{ url_for('daily_report') }}">Reports</a>
  <a href="{{ url_for('logout') }}">Logout</a>
</nav>
{% endif %}
<div class="container">
{% with messages = get_flashed_messages() %}
  {% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}
{% endwith %}
{{ body|safe }}
</div>
</body>
</html>
"""


def page(title: str, body_template: str, **context):
    body = render_template_string(body_template, **context)
    return render_template_string(BASE_TEMPLATE, title=title, body=body)


# ---------------------------------------------------------------------------
# Authentication / setup
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    init_db()
    users = scalar("SELECT COUNT(*) FROM users")
    if not users:
        return redirect(url_for("setup"))
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    init_db()
    if scalar("SELECT COUNT(*) FROM users") > 0:
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form["username"].strip()
        full_name = request.form["full_name"].strip()
        password = request.form["password"]
        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO users(username,password_hash,full_name) VALUES(?,?,?)",
                (username, generate_password_hash(password), full_name),
            )
            db.commit()
            flash("Administrator created. Please sign in.")
            return redirect(url_for("login"))

    return page("Initial Setup", """
    <div class="card" style="max-width:520px;margin:50px auto">
      <h2>Create the first administrator</h2>
      <p class="muted">No default username or password is included in the public repository.</p>
      <form method="post">
        <label>Full name</label><input name="full_name" required>
        <label>Username</label><input name="username" required>
        <label>Password</label><input name="password" type="password" minlength="8" required>
        <button>Create administrator</button>
      </form>
    </div>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()
    if request.method == "POST":
        user = get_db().execute(
            "SELECT * FROM users WHERE username=?", (request.form["username"].strip(),)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.")

    return page("Login", """
    <div class="card" style="max-width:430px;margin:70px auto">
      <h2>Sign in</h2>
      <form method="post">
        <label>Username</label><input name="username" required>
        <label>Password</label><input type="password" name="password" required>
        <button>Login</button>
      </form>
    </div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    today = date.today().isoformat()
    stats = {
        "products": scalar("SELECT COUNT(*) FROM products"),
        "stock_value": scalar("SELECT COALESCE(SUM(quantity*purchase_price),0) FROM products"),
        "sales_today": scalar(
            "SELECT COALESCE(SUM(total),0) FROM transactions WHERE kind='sale' AND transaction_date=?",
            (today,),
        ),
        "purchases_today": scalar(
            "SELECT COALESCE(SUM(total),0) FROM transactions WHERE kind='purchase' AND transaction_date=?",
            (today,),
        ),
    }
    low_stock = get_db().execute(
        "SELECT * FROM products WHERE quantity <= reorder_level ORDER BY quantity ASC LIMIT 8"
    ).fetchall()
    return page("Dashboard", """
    <h1>Dashboard</h1>
    <div class="grid">
      <div class="card"><div class="muted">Products</div><div class="stat">{{ stats.products }}</div></div>
      <div class="card"><div class="muted">Inventory cost value</div><div class="stat">{{ '%.2f'|format(stats.stock_value) }}</div></div>
      <div class="card"><div class="muted">Sales today</div><div class="stat">{{ '%.2f'|format(stats.sales_today) }}</div></div>
      <div class="card"><div class="muted">Purchases today</div><div class="stat">{{ '%.2f'|format(stats.purchases_today) }}</div></div>
    </div>
    <div class="card">
      <h3>Low-stock products</h3>
      <table><tr><th>Product</th><th>SKU</th><th>Quantity</th><th>Reorder level</th></tr>
      {% for p in low_stock %}
        <tr><td>{{ p.name }}</td><td>{{ p.sku or '-' }}</td><td>{{ p.quantity }}</td><td>{{ p.reorder_level }}</td></tr>
      {% else %}<tr><td colspan="4">No low-stock products.</td></tr>{% endfor %}
      </table>
    </div>
    """, stats=stats, low_stock=low_stock)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@app.route("/products")
@login_required
def products():
    rows = get_db().execute("SELECT * FROM products ORDER BY name").fetchall()
    return page("Inventory", """
    <div style="display:flex;justify-content:space-between;align-items:center">
      <h1>Inventory</h1><a class="btn" href="{{ url_for('product_add') }}">Add product</a>
    </div>
    <div class="card">
    <table><tr><th>Name</th><th>SKU</th><th>Qty</th><th>Purchase</th><th>Sale</th><th>Reorder</th></tr>
    {% for p in rows %}
      <tr><td>{{ p.name }}</td><td>{{ p.sku or '-' }}</td><td>{{ p.quantity }}</td>
      <td>{{ '%.2f'|format(p.purchase_price) }}</td><td>{{ '%.2f'|format(p.sale_price) }}</td><td>{{ p.reorder_level }}</td></tr>
    {% else %}<tr><td colspan="6">No products yet.</td></tr>{% endfor %}
    </table></div>
    """, rows=rows)


@app.route("/products/add", methods=["GET", "POST"])
@login_required
def product_add():
    if request.method == "POST":
        db = get_db()
        try:
            db.execute(
                """INSERT INTO products(name,sku,quantity,purchase_price,sale_price,reorder_level)
                   VALUES(?,?,?,?,?,?)""",
                (
                    request.form["name"].strip(),
                    request.form.get("sku", "").strip() or None,
                    float(request.form.get("quantity") or 0),
                    float(request.form.get("purchase_price") or 0),
                    float(request.form.get("sale_price") or 0),
                    float(request.form.get("reorder_level") or 0),
                ),
            )
            db.commit()
            flash("Product added.")
            return redirect(url_for("products"))
        except sqlite3.IntegrityError:
            flash("SKU already exists.")

    return page("Add Product", """
    <div class="card"><h2>Add product</h2>
    <form method="post">
      <div class="row"><div><label>Name</label><input name="name" required></div>
      <div><label>SKU</label><input name="sku"></div></div>
      <div class="row"><div><label>Initial quantity</label><input name="quantity" type="number" step="0.01" value="0"></div>
      <div><label>Reorder level</label><input name="reorder_level" type="number" step="0.01" value="0"></div></div>
      <div class="row"><div><label>Purchase price</label><input name="purchase_price" type="number" step="0.01" value="0"></div>
      <div><label>Sale price</label><input name="sale_price" type="number" step="0.01" value="0"></div></div>
      <button>Save</button>
    </form></div>
    """)


# ---------------------------------------------------------------------------
# Accounts / payments
# ---------------------------------------------------------------------------

@app.route("/accounts")
@login_required
def accounts():
    rows = get_db().execute("SELECT * FROM accounts ORDER BY name").fetchall()
    enriched = [(r, account_balance(r["id"])) for r in rows]
    return page("Accounts", """
    <div style="display:flex;justify-content:space-between;align-items:center">
      <h1>Accounts</h1><a class="btn" href="{{ url_for('account_add') }}">Add account</a>
    </div>
    <div class="card"><table>
    <tr><th>Name</th><th>Phone</th><th>Balance</th><th></th></tr>
    {% for a,balance in enriched %}
      <tr><td>{{ a.name }}</td><td>{{ a.phone or '-' }}</td>
      <td class="{{ 'positive' if balance > 0 else 'negative' }}">{{ '%.2f'|format(balance) }}</td>
      <td><a href="{{ url_for('account_detail', account_id=a.id) }}">Open</a></td></tr>
    {% else %}<tr><td colspan="4">No accounts yet.</td></tr>{% endfor %}
    </table></div>
    """, enriched=enriched)


@app.route("/accounts/add", methods=["GET", "POST"])
@login_required
def account_add():
    if request.method == "POST":
        db = get_db()
        db.execute(
            "INSERT INTO accounts(name,phone,address,notes,opening_balance) VALUES(?,?,?,?,?)",
            (
                request.form["name"].strip(),
                request.form.get("phone", "").strip(),
                request.form.get("address", "").strip(),
                request.form.get("notes", "").strip(),
                float(request.form.get("opening_balance") or 0),
            ),
        )
        db.commit()
        flash("Account added.")
        return redirect(url_for("accounts"))

    return page("Add Account", """
    <div class="card"><h2>Add customer / supplier account</h2>
    <form method="post">
      <label>Name</label><input name="name" required>
      <div class="row"><div><label>Phone</label><input name="phone"></div>
      <div><label>Opening balance</label><input name="opening_balance" type="number" step="0.01" value="0"></div></div>
      <label>Address</label><input name="address">
      <label>Notes</label><textarea name="notes"></textarea>
      <button>Save</button>
    </form></div>
    """)


@app.route("/accounts/<int:account_id>", methods=["GET"])
@login_required
def account_detail(account_id):
    db = get_db()
    account = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not account:
        return "Account not found", 404
    tx = db.execute(
        "SELECT t.*,p.name product_name FROM transactions t JOIN products p ON p.id=t.product_id WHERE account_id=? ORDER BY transaction_date DESC,id DESC",
        (account_id,),
    ).fetchall()
    payments = db.execute(
        "SELECT * FROM payments WHERE account_id=? ORDER BY payment_date DESC,id DESC", (account_id,)
    ).fetchall()
    balance = account_balance(account_id)
    return page("Account Detail", """
    <h1>{{ account.name }}</h1>
    <div class="grid">
      <div class="card"><div class="muted">Current balance</div><div class="stat">{{ '%.2f'|format(balance) }}</div></div>
      <div class="card"><div class="muted">Phone</div><div>{{ account.phone or '-' }}</div></div>
    </div>
    <div class="card">
      <h3>Record payment</h3>
      <form method="post" action="{{ url_for('payment_add', account_id=account.id) }}">
        <div class="row">
          <div><label>Direction</label><select name="direction"><option value="received">Received from account</option><option value="paid">Paid to account</option></select></div>
          <div><label>Amount</label><input type="number" step="0.01" min="0.01" name="amount" required></div>
        </div>
        <div class="row"><div><label>Date</label><input type="date" name="payment_date" value="{{ today }}" required></div>
        <div><label>Notes</label><input name="notes"></div></div>
        <button>Save payment</button>
      </form>
    </div>
    <div class="card"><h3>Transactions</h3><table>
      <tr><th>Date</th><th>Type</th><th>Product</th><th>Qty</th><th>Total</th></tr>
      {% for t in tx %}<tr><td>{{ t.transaction_date }}</td><td>{{ t.kind }}</td><td>{{ t.product_name }}</td><td>{{ t.quantity }}</td><td>{{ '%.2f'|format(t.total) }}</td></tr>
      {% else %}<tr><td colspan="5">No transactions.</td></tr>{% endfor %}
    </table></div>
    <div class="card"><h3>Payments</h3><table>
      <tr><th>Date</th><th>Direction</th><th>Amount</th><th>Notes</th></tr>
      {% for p in payments %}<tr><td>{{ p.payment_date }}</td><td>{{ p.direction }}</td><td>{{ '%.2f'|format(p.amount) }}</td><td>{{ p.notes }}</td></tr>
      {% else %}<tr><td colspan="4">No payments.</td></tr>{% endfor %}
    </table></div>
    """, account=account, balance=balance, tx=tx, payments=payments, today=date.today().isoformat())


@app.route("/accounts/<int:account_id>/payment", methods=["POST"])
@login_required
def payment_add(account_id):
    amount = float(request.form["amount"])
    if amount <= 0:
        flash("Amount must be positive.")
        return redirect(url_for("account_detail", account_id=account_id))
    db = get_db()
    db.execute(
        "INSERT INTO payments(account_id,amount,direction,payment_date,notes) VALUES(?,?,?,?,?)",
        (
            account_id,
            amount,
            request.form["direction"],
            request.form["payment_date"],
            request.form.get("notes", "").strip(),
        ),
    )
    db.commit()
    flash("Payment recorded.")
    return redirect(url_for("account_detail", account_id=account_id))


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

@app.route("/transactions")
@login_required
def transactions():
    rows = get_db().execute(
        """SELECT t.*,p.name product_name,a.name account_name
           FROM transactions t
           JOIN products p ON p.id=t.product_id
           LEFT JOIN accounts a ON a.id=t.account_id
           ORDER BY transaction_date DESC,t.id DESC LIMIT 250"""
    ).fetchall()
    return page("Transactions", """
    <div style="display:flex;justify-content:space-between;align-items:center">
      <h1>Transactions</h1><a class="btn" href="{{ url_for('transaction_add') }}">New transaction</a>
    </div>
    <div class="card"><table>
      <tr><th>Date</th><th>Type</th><th>Product</th><th>Account</th><th>Qty</th><th>Total</th></tr>
      {% for t in rows %}<tr><td>{{ t.transaction_date }}</td><td>{{ t.kind }}</td><td>{{ t.product_name }}</td>
      <td>{{ t.account_name or '-' }}</td><td>{{ t.quantity }}</td><td>{{ '%.2f'|format(t.total) }}</td></tr>
      {% else %}<tr><td colspan="6">No transactions yet.</td></tr>{% endfor %}
    </table></div>
    """, rows=rows)


@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def transaction_add():
    db = get_db()
    products = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    accounts_list = db.execute("SELECT * FROM accounts ORDER BY name").fetchall()

    if request.method == "POST":
        kind = request.form["kind"]
        product_id = int(request.form["product_id"])
        account_id = int(request.form["account_id"]) if request.form.get("account_id") else None
        quantity = float(request.form["quantity"])
        unit_price = float(request.form["unit_price"])
        if quantity <= 0 or unit_price < 0:
            flash("Quantity must be positive and price cannot be negative.")
            return redirect(url_for("transaction_add"))

        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not product:
            flash("Product not found.")
            return redirect(url_for("transaction_add"))
        if kind == "sale" and product["quantity"] < quantity:
            flash("Insufficient stock for this sale.")
            return redirect(url_for("transaction_add"))

        total = quantity * unit_price
        db.execute(
            """INSERT INTO transactions(kind,product_id,account_id,quantity,unit_price,total,transaction_date,notes)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                kind, product_id, account_id, quantity, unit_price, total,
                request.form["transaction_date"], request.form.get("notes", "").strip()
            ),
        )
        if kind == "purchase":
            db.execute("UPDATE products SET quantity=quantity+? WHERE id=?", (quantity, product_id))
        else:
            db.execute("UPDATE products SET quantity=quantity-? WHERE id=?", (quantity, product_id))
        db.commit()
        flash("Transaction saved.")
        return redirect(url_for("transactions"))

    return page("New Transaction", """
    <div class="card"><h2>New sale / purchase</h2>
    {% if not products %}<p>Please add at least one product first.</p>{% else %}
    <form method="post">
      <div class="row"><div><label>Type</label><select name="kind"><option value="sale">Sale</option><option value="purchase">Purchase</option></select></div>
      <div><label>Date</label><input type="date" name="transaction_date" value="{{ today }}" required></div></div>
      <label>Product</label><select name="product_id" required>{% for p in products %}<option value="{{ p.id }}">{{ p.name }} (stock {{ p.quantity }})</option>{% endfor %}</select>
      <label>Account (optional)</label><select name="account_id"><option value="">Cash / none</option>{% for a in accounts_list %}<option value="{{ a.id }}">{{ a.name }}</option>{% endfor %}</select>
      <div class="row"><div><label>Quantity</label><input type="number" step="0.01" min="0.01" name="quantity" required></div>
      <div><label>Unit price</label><input type="number" step="0.01" min="0" name="unit_price" required></div></div>
      <label>Notes</label><input name="notes">
      <button>Save transaction</button>
    </form>{% endif %}</div>
    """, products=products, accounts_list=accounts_list, today=date.today().isoformat())


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.route("/reports/daily")
@login_required
def daily_report():
    report_date = request.args.get("date", date.today().isoformat())
    db = get_db()
    rows = db.execute(
        """SELECT t.*,p.name product_name,a.name account_name
           FROM transactions t
           JOIN products p ON p.id=t.product_id
           LEFT JOIN accounts a ON a.id=t.account_id
           WHERE t.transaction_date=?
           ORDER BY t.id DESC""",
        (report_date,),
    ).fetchall()
    sales = sum(r["total"] for r in rows if r["kind"] == "sale")
    purchases = sum(r["total"] for r in rows if r["kind"] == "purchase")
    profit_proxy = sales - purchases

    return page("Daily Report", """
    <h1>Daily Report</h1>
    <div class="card"><form method="get"><div class="row"><div><label>Date</label><input type="date" name="date" value="{{ report_date }}"></div>
    <div style="padding-top:25px"><button>Load report</button></div></div></form></div>
    <div class="grid">
      <div class="card"><div class="muted">Sales</div><div class="stat">{{ '%.2f'|format(sales) }}</div></div>
      <div class="card"><div class="muted">Purchases</div><div class="stat">{{ '%.2f'|format(purchases) }}</div></div>
      <div class="card"><div class="muted">Net cash-flow proxy</div><div class="stat">{{ '%.2f'|format(profit_proxy) }}</div></div>
    </div>
    <div class="card"><table><tr><th>Type</th><th>Product</th><th>Account</th><th>Qty</th><th>Total</th></tr>
    {% for t in rows %}<tr><td>{{ t.kind }}</td><td>{{ t.product_name }}</td><td>{{ t.account_name or '-' }}</td><td>{{ t.quantity }}</td><td>{{ '%.2f'|format(t.total) }}</td></tr>
    {% else %}<tr><td colspan="5">No transactions for this date.</td></tr>{% endfor %}
    </table></div>
    <p class="muted">The net figure above is a simple sales-minus-purchases cash-flow indicator, not a full accrual-accounting profit calculation.</p>
    """, report_date=report_date, rows=rows, sales=sales, purchases=purchases, profit_proxy=profit_proxy)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=8000, debug=True)
