"""
INVEXA — Inventory & Sales Management System
=============================================
A complete rewrite of the original "Inventory Pro" project with a fresh,
premium UI/UX and a few extra features layered on top:

    - Full Customers module (previously customers could only be created
      inline from the "New Sale" screen — now they have their own list,
      add and edit pages).
    - A real analytics dashboard: revenue trend, top-selling products and
      stock value split by category, all rendered with Chart.js.
    - CSV export for Products and Sales.
    - Global product/sales search + filters.
    - A dedicated Stock Ledger (stock in / stock out / full history).
    - Light & dark theme toggle.

The SQLite schema below is intentionally identical (table + column names)
to the one the original notebook created, so an existing ``inventory.db``
file can be dropped in next to this file and everything — products,
sales, customers, stock history, the admin login — keeps working exactly
as it did before. No data migration is required.
"""

import csv
import io
import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, Response, flash, g, redirect, render_template,
    request, session, url_for
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "inventory.db")

APP_NAME = "INVEXA"

app = Flask(__name__)
app.secret_key = "invexa_secret_key_change_me"


# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create every table used by the app (schema matches the original
    project exactly, so existing databases stay compatible)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            purchase_price REAL NOT NULL,
            selling_price REAL NOT NULL,
            quantity INTEGER DEFAULT 0,
            minimum_stock INTEGER DEFAULT 5,
            supplier TEXT,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            subtotal REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            total_amount REAL DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            subtotal REAL,
            FOREIGN KEY (sale_id) REFERENCES sales(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            previous_stock INTEGER NOT NULL,
            new_stock INTEGER NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # Seed a default admin account only if the users table is empty, so an
    # existing database (and its existing accounts) is never touched.
    row = cur.execute("SELECT COUNT(*) FROM users").fetchone()
    if row[0] == 0:
        cur.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("admin", "admin123"),
        )

    conn.commit()
    conn.close()


# ----------------------------------------------------------------------
# Auth helpers
# ----------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    low_stock_count = 0
    if session.get("logged_in"):
        db = get_db()
        low_stock_count = db.execute(
            "SELECT COUNT(*) FROM products WHERE quantity <= minimum_stock"
        ).fetchone()[0]
    return {
        "app_name": APP_NAME,
        "current_user": session.get("username"),
        "low_stock_count": low_stock_count,
    }


# ----------------------------------------------------------------------
# Auth routes
# ----------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("logged_in") else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password),
        ).fetchone()

        if user:
            session.clear()
            session["logged_in"] = True
            session["username"] = user["username"]
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()

    total_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_customers = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    total_sales = db.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    total_revenue = db.execute(
        "SELECT COALESCE(SUM(total_amount), 0) FROM sales"
    ).fetchone()[0]
    stock_value = db.execute(
        "SELECT COALESCE(SUM(quantity * purchase_price), 0) FROM products"
    ).fetchone()[0]

    low_stock = db.execute("""
        SELECT products.*, categories.name AS category_name
        FROM products
        LEFT JOIN categories ON categories.id = products.category_id
        WHERE quantity <= minimum_stock
        ORDER BY quantity ASC
        LIMIT 8
    """).fetchall()

    recent_sales = db.execute("""
        SELECT sales.id, customers.name AS customer_name, sales.sale_date, sales.total_amount
        FROM sales
        LEFT JOIN customers ON customers.id = sales.customer_id
        ORDER BY sales.id DESC
        LIMIT 6
    """).fetchall()

    # --- Revenue trend (last 14 days) ---
    since = (datetime.now() - timedelta(days=13)).strftime("%Y-%m-%d")
    trend_rows = db.execute("""
        SELECT date(sale_date) AS d, COALESCE(SUM(total_amount), 0) AS total
        FROM sales
        WHERE date(sale_date) >= ?
        GROUP BY date(sale_date)
        ORDER BY d ASC
    """, (since,)).fetchall()
    trend_map = {r["d"]: r["total"] for r in trend_rows}
    trend_labels, trend_values = [], []
    for i in range(13, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend_labels.append(day[5:])  # MM-DD
        trend_values.append(round(trend_map.get(day, 0), 2))

    # --- Top selling products ---
    top_products = db.execute("""
        SELECT products.name, SUM(sale_items.quantity) AS qty
        FROM sale_items
        JOIN products ON products.id = sale_items.product_id
        GROUP BY sale_items.product_id
        ORDER BY qty DESC
        LIMIT 5
    """).fetchall()

    # --- Stock value by category ---
    cat_value = db.execute("""
        SELECT COALESCE(categories.name, 'Uncategorized') AS name,
               COALESCE(SUM(products.quantity * products.purchase_price), 0) AS value
        FROM products
        LEFT JOIN categories ON categories.id = products.category_id
        GROUP BY products.category_id
        HAVING value > 0
        ORDER BY value DESC
        LIMIT 6
    """).fetchall()

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_customers=total_customers,
        total_sales=total_sales,
        total_revenue=total_revenue,
        stock_value=stock_value,
        low_stock=low_stock,
        recent_sales=recent_sales,
        trend_labels=trend_labels,
        trend_values=trend_values,
        top_product_labels=[r["name"] for r in top_products],
        top_product_values=[r["qty"] for r in top_products],
        cat_labels=[r["name"] for r in cat_value],
        cat_values=[round(r["value"], 2) for r in cat_value],
    )


# ----------------------------------------------------------------------
# Products
# ----------------------------------------------------------------------

@app.route("/products")
@login_required
def products():
    db = get_db()
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", "")
    status = request.args.get("status", "")

    sql = """
        SELECT products.*, categories.name AS category_name
        FROM products
        LEFT JOIN categories ON categories.id = products.category_id
        WHERE 1=1
    """
    params = []

    if q:
        sql += " AND products.name LIKE ?"
        params.append(f"%{q}%")
    if category_id:
        sql += " AND products.category_id = ?"
        params.append(category_id)
    if status == "low":
        sql += " AND products.quantity <= products.minimum_stock AND products.quantity > 0"
    elif status == "out":
        sql += " AND products.quantity <= 0"

    sql += " ORDER BY products.name"

    product_list = db.execute(sql, params).fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()

    return render_template(
        "products.html",
        products=product_list,
        categories=categories,
        q=q,
        selected_category=category_id,
        selected_status=status,
    )


@app.route("/products/add", methods=["GET", "POST"])
@login_required
def add_product():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id") or None
        purchase_price = request.form.get("purchase_price")
        selling_price = request.form.get("selling_price")
        quantity = request.form.get("quantity", "0")
        minimum_stock = request.form.get("minimum_stock", "5")
        supplier = request.form.get("supplier", "").strip()

        error = None
        if not name:
            error = "Product name is required."
        else:
            try:
                purchase_price = float(purchase_price)
                selling_price = float(selling_price)
                quantity = int(quantity)
                minimum_stock = int(minimum_stock)
            except (TypeError, ValueError):
                error = "Please enter valid numbers for price / quantity fields."

        if not error and (purchase_price < 0 or selling_price < 0 or quantity < 0 or minimum_stock < 0):
            error = "Numeric fields cannot be negative."

        if error:
            flash(error, "error")
            categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
            suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
            return render_template("add_product.html", categories=categories, suppliers=suppliers, form=request.form)

        db.execute("""
            INSERT INTO products (name, category_id, purchase_price, selling_price, quantity, minimum_stock, supplier)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, category_id, purchase_price, selling_price, quantity, minimum_stock, supplier))
        product_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        if quantity > 0:
            db.execute("""
                INSERT INTO stock_movements (product_id, movement_type, quantity, previous_stock, new_stock, note)
                VALUES (?, 'IN', ?, 0, ?, 'Initial stock on product creation')
            """, (product_id, quantity, quantity))

        db.commit()
        flash(f'"{name}" was added to the catalog.', "success")
        return redirect(url_for("products"))

    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return render_template("add_product.html", categories=categories, suppliers=suppliers, form={})


@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id") or None
        purchase_price = request.form.get("purchase_price")
        selling_price = request.form.get("selling_price")
        minimum_stock = request.form.get("minimum_stock", "5")
        supplier = request.form.get("supplier", "").strip()

        error = None
        if not name:
            error = "Product name is required."
        else:
            try:
                purchase_price = float(purchase_price)
                selling_price = float(selling_price)
                minimum_stock = int(minimum_stock)
            except (TypeError, ValueError):
                error = "Please enter valid numbers for price fields."

        if error:
            flash(error, "error")
            categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
            suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
            return render_template("edit_product.html", product=product, categories=categories, suppliers=suppliers)

        db.execute("""
            UPDATE products
            SET name = ?, category_id = ?, purchase_price = ?, selling_price = ?,
                minimum_stock = ?, supplier = ?
            WHERE id = ?
        """, (name, category_id, purchase_price, selling_price, minimum_stock, supplier, product_id))
        db.commit()
        flash(f'"{name}" was updated.', "success")
        return redirect(url_for("products"))

    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    suppliers = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return render_template("edit_product.html", product=product, categories=categories, suppliers=suppliers)


@app.route("/products/delete/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):
    db = get_db()
    product = db.execute("SELECT name FROM products WHERE id = ?", (product_id,)).fetchone()

    try:
        db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        flash(f'"{product["name"]}" was deleted.' if product else "Product deleted.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash(
            f'"{product["name"] if product else "This product"}" has sales or stock history attached '
            "and can't be deleted. Set its quantity to 0 instead to retire it from active stock.",
            "error",
        )

    return redirect(url_for("products"))


@app.route("/products/export")
@login_required
def export_products():
    db = get_db()
    rows = db.execute("""
        SELECT products.name, categories.name AS category, products.purchase_price,
               products.selling_price, products.quantity, products.minimum_stock, products.supplier
        FROM products LEFT JOIN categories ON categories.id = products.category_id
        ORDER BY products.name
    """).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Category", "Purchase Price", "Selling Price", "Quantity", "Minimum Stock", "Supplier"])
    for r in rows:
        writer.writerow([r["name"], r["category"], r["purchase_price"], r["selling_price"], r["quantity"], r["minimum_stock"], r["supplier"]])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=invexa_products.csv"},
    )


# ----------------------------------------------------------------------
# Categories
# ----------------------------------------------------------------------

@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    db = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "error")
        else:
            try:
                db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
                db.commit()
                flash(f'Category "{name}" created.', "success")
            except sqlite3.IntegrityError:
                flash(f'Category "{name}" already exists.', "error")
        return redirect(url_for("categories"))

    category_list = db.execute("""
        SELECT categories.*, COUNT(products.id) AS product_count
        FROM categories
        LEFT JOIN products ON products.category_id = categories.id
        GROUP BY categories.id
        ORDER BY categories.name
    """).fetchall()
    return render_template("categories.html", categories=category_list)


@app.route("/categories/edit/<int:category_id>", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    db = get_db()
    category = db.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if category is None:
        flash("Category not found.", "error")
        return redirect(url_for("categories"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "error")
            return render_template("edit_category.html", category=category)
        try:
            db.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
            db.commit()
            flash("Category updated.", "success")
        except sqlite3.IntegrityError:
            flash(f'Category "{name}" already exists.', "error")
            return render_template("edit_category.html", category=category)
        return redirect(url_for("categories"))

    return render_template("edit_category.html", category=category)


@app.route("/categories/delete/<int:category_id>", methods=["POST"])
@login_required
def delete_category(category_id):
    db = get_db()
    db.execute("UPDATE products SET category_id = NULL WHERE category_id = ?", (category_id,))
    db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    db.commit()
    flash("Category deleted.", "success")
    return redirect(url_for("categories"))


# ----------------------------------------------------------------------
# Suppliers
# ----------------------------------------------------------------------

@app.route("/suppliers")
@login_required
def suppliers():
    db = get_db()
    supplier_list = db.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return render_template("suppliers.html", suppliers=supplier_list)


@app.route("/suppliers/add", methods=["GET", "POST"])
@login_required
def add_supplier():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            return render_template("add_supplier.html", form=request.form)

        db.execute("INSERT INTO suppliers (name, phone, email, address) VALUES (?, ?, ?, ?)",
                   (name, phone, email, address))
        db.commit()
        flash(f'Supplier "{name}" added.', "success")
        return redirect(url_for("suppliers"))

    return render_template("add_supplier.html", form={})


@app.route("/suppliers/edit/<int:supplier_id>", methods=["GET", "POST"])
@login_required
def edit_supplier(supplier_id):
    db = get_db()
    supplier = db.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if supplier is None:
        flash("Supplier not found.", "error")
        return redirect(url_for("suppliers"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            return render_template("edit_supplier.html", supplier=supplier)

        db.execute("UPDATE suppliers SET name=?, phone=?, email=?, address=? WHERE id=?",
                   (name, phone, email, address, supplier_id))
        db.commit()
        flash("Supplier updated.", "success")
        return redirect(url_for("suppliers"))

    return render_template("edit_supplier.html", supplier=supplier)


@app.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
@login_required
def delete_supplier(supplier_id):
    db = get_db()
    db.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    db.commit()
    flash("Supplier deleted.", "success")
    return redirect(url_for("suppliers"))


# ----------------------------------------------------------------------
# Customers  (new: previously customers had no management page at all)
# ----------------------------------------------------------------------

@app.route("/customers")
@login_required
def customers():
    db = get_db()
    q = request.args.get("q", "").strip()
    sql = """
        SELECT customers.*,
               COUNT(sales.id) AS order_count,
               COALESCE(SUM(sales.total_amount), 0) AS lifetime_value
        FROM customers
        LEFT JOIN sales ON sales.customer_id = customers.id
        WHERE 1=1
    """
    params = []
    if q:
        sql += " AND customers.name LIKE ?"
        params.append(f"%{q}%")
    sql += " GROUP BY customers.id ORDER BY customers.name"

    customer_list = db.execute(sql, params).fetchall()
    return render_template("customers.html", customers=customer_list, q=q)


@app.route("/customers/add", methods=["GET", "POST"])
@login_required
def add_customer():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Customer name is required.", "error")
            return render_template("add_customer.html", form=request.form)

        db.execute("INSERT INTO customers (name, phone, email, address) VALUES (?, ?, ?, ?)",
                   (name, phone, email, address))
        db.commit()
        flash(f'Customer "{name}" added.', "success")
        return redirect(url_for("customers"))

    return render_template("add_customer.html", form={})


@app.route("/customers/edit/<int:customer_id>", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if customer is None:
        flash("Customer not found.", "error")
        return redirect(url_for("customers"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Customer name is required.", "error")
            return render_template("edit_customer.html", customer=customer)

        db.execute("UPDATE customers SET name=?, phone=?, email=?, address=? WHERE id=?",
                   (name, phone, email, address, customer_id))
        db.commit()
        flash("Customer updated.", "success")
        return redirect(url_for("customers"))

    return render_template("edit_customer.html", customer=customer)


@app.route("/customers/delete/<int:customer_id>", methods=["POST"])
@login_required
def delete_customer(customer_id):
    db = get_db()
    customer = db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()

    try:
        db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        db.commit()
        flash(f'"{customer["name"]}" was deleted.' if customer else "Customer deleted.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash(
            f'"{customer["name"] if customer else "This customer"}" has sales on record '
            "and can't be deleted, to keep past invoices intact.",
            "error",
        )

    return redirect(url_for("customers"))


# ----------------------------------------------------------------------
# Sales
# ----------------------------------------------------------------------

@app.route("/sales")
@login_required
def sales():
    db = get_db()
    q = request.args.get("q", "").strip()

    sql = """
        SELECT sales.id, customers.name AS customer_name, sales.sale_date, sales.total_amount
        FROM sales
        LEFT JOIN customers ON customers.id = sales.customer_id
        WHERE 1=1
    """
    params = []
    if q:
        sql += " AND customers.name LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY sales.id DESC"

    sale_list = db.execute(sql, params).fetchall()
    return render_template("sales.html", sales=sale_list, q=q)


@app.route("/sales/export")
@login_required
def export_sales():
    db = get_db()
    rows = db.execute("""
        SELECT sales.id, customers.name AS customer_name, sales.sale_date, sales.subtotal,
               sales.discount, sales.total_amount
        FROM sales
        LEFT JOIN customers ON customers.id = sales.customer_id
        ORDER BY sales.id DESC
    """).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Sale ID", "Customer", "Date", "Subtotal", "Discount", "Total"])
    for r in rows:
        writer.writerow([r["id"], r["customer_name"], r["sale_date"], r["subtotal"], r["discount"], r["total_amount"]])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=invexa_sales.csv"},
    )


@app.route("/sales/create", methods=["GET", "POST"])
@login_required
def create_sale():
    db = get_db()

    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        product_id = request.form.get("product_id")
        quantity = request.form.get("quantity")
        discount_percent = request.form.get("discount_percent", "0")

        def render_error(message, code=400):
            customers_ = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
            products_ = db.execute("SELECT * FROM products ORDER BY name").fetchall()
            return render_template("create_sale.html", customers=customers_, products=products_, error=message), code

        try:
            product_id = int(product_id)
            quantity = int(quantity)
            discount_percent = float(discount_percent or 0)
        except (TypeError, ValueError):
            return render_error("Please provide a valid product and quantity.")

        if quantity <= 0:
            return render_error("Quantity must be greater than 0.")
        if discount_percent < 0 or discount_percent > 100:
            return render_error("Discount must be between 0 and 100.")

        # Resolve / create the customer
        if customer_id == "new":
            new_name = request.form.get("new_customer_name", "").strip()
            new_phone = request.form.get("new_customer_phone", "").strip()
            if not new_name:
                return render_error("New customer name is required.")
            cur = db.cursor()
            cur.execute("INSERT INTO customers (name, phone, email, address) VALUES (?, ?, '', '')",
                        (new_name, new_phone))
            customer_id = cur.lastrowid
        else:
            try:
                customer_id = int(customer_id)
            except (TypeError, ValueError):
                return render_error("Please select a valid customer.")
            exists = db.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
            if not exists:
                return render_error("Customer not found.", 404)

        product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return render_error("Product not found.", 404)
        if product["quantity"] < quantity:
            return render_error(f"Not enough stock. Available: {product['quantity']}")

        unit_price = float(product["selling_price"] or 0)
        subtotal = unit_price * quantity
        discount_amount = subtotal * discount_percent / 100
        total_amount = subtotal - discount_amount

        try:
            cur = db.cursor()
            cur.execute("""
                INSERT INTO sales (customer_id, subtotal, discount, total_amount)
                VALUES (?, ?, ?, ?)
            """, (customer_id, subtotal, discount_amount, total_amount))
            sale_id = cur.lastrowid

            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, total_price, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sale_id, product_id, quantity, unit_price, total_amount, subtotal))

            previous_stock = product["quantity"]
            new_stock = previous_stock - quantity
            cur.execute("UPDATE products SET quantity = ? WHERE id = ?", (new_stock, product_id))

            cur.execute("""
                INSERT INTO stock_movements (product_id, movement_type, quantity, previous_stock, new_stock, note)
                VALUES (?, 'SALE', ?, ?, ?, ?)
            """, (product_id, quantity, previous_stock, new_stock, f"Sale #{sale_id}"))

            db.commit()
        except Exception as e:
            db.rollback()
            return render_error(f"Sale could not be completed: {e}", 500)

        flash(f"Sale #{sale_id} completed.", "success")
        return redirect(url_for("sales_invoice", sale_id=sale_id))

    customers_ = db.execute("SELECT * FROM customers ORDER BY name").fetchall()
    products_ = db.execute("SELECT * FROM products WHERE quantity > 0 ORDER BY name").fetchall()
    return render_template("create_sale.html", customers=customers_, products=products_, error=None)


@app.route("/sales/invoice/<int:sale_id>")
@login_required
def sales_invoice(sale_id):
    db = get_db()
    sale = db.execute("""
        SELECT sales.*, customers.name AS customer_name, customers.phone AS customer_phone,
               customers.address AS customer_address
        FROM sales
        LEFT JOIN customers ON customers.id = sales.customer_id
        WHERE sales.id = ?
    """, (sale_id,)).fetchone()

    if sale is None:
        flash("Sale not found.", "error")
        return redirect(url_for("sales"))

    items = db.execute("""
        SELECT sale_items.*, products.name AS product_name
        FROM sale_items
        JOIN products ON products.id = sale_items.product_id
        WHERE sale_items.sale_id = ?
    """, (sale_id,)).fetchall()

    return render_template("invoice.html", sale=sale, items=items)


# ----------------------------------------------------------------------
# Stock
# ----------------------------------------------------------------------

@app.route("/stock")
@login_required
def stock():
    db = get_db()
    q = request.args.get("q", "").strip()
    sql = """
        SELECT products.*, categories.name AS category_name
        FROM products
        LEFT JOIN categories ON categories.id = products.category_id
        WHERE 1=1
    """
    params = []
    if q:
        sql += " AND products.name LIKE ?"
        params.append(f"%{q}%")
    sql += " ORDER BY products.name"

    product_list = db.execute(sql, params).fetchall()
    return render_template("stock.html", products=product_list, q=q)


@app.route("/stock/in/<int:product_id>", methods=["POST"])
@login_required
def stock_in(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("stock"))

    try:
        quantity = int(request.form.get("quantity"))
    except (TypeError, ValueError):
        flash("Enter a valid quantity.", "error")
        return redirect(url_for("stock"))

    if quantity <= 0:
        flash("Quantity must be greater than 0.", "error")
        return redirect(url_for("stock"))

    note = request.form.get("note", "").strip() or "Manual stock in"
    previous_stock = product["quantity"]
    new_stock = previous_stock + quantity

    db.execute("UPDATE products SET quantity = ? WHERE id = ?", (new_stock, product_id))
    db.execute("""
        INSERT INTO stock_movements (product_id, movement_type, quantity, previous_stock, new_stock, note)
        VALUES (?, 'IN', ?, ?, ?, ?)
    """, (product_id, quantity, previous_stock, new_stock, note))
    db.commit()

    flash(f'Added {quantity} units to "{product["name"]}".', "success")
    return redirect(url_for("stock"))


@app.route("/stock/out/<int:product_id>", methods=["POST"])
@login_required
def stock_out(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("stock"))

    try:
        quantity = int(request.form.get("quantity"))
    except (TypeError, ValueError):
        flash("Enter a valid quantity.", "error")
        return redirect(url_for("stock"))

    if quantity <= 0:
        flash("Quantity must be greater than 0.", "error")
        return redirect(url_for("stock"))
    if quantity > product["quantity"]:
        flash(f'Only {product["quantity"]} units of "{product["name"]}" are available.', "error")
        return redirect(url_for("stock"))

    note = request.form.get("note", "").strip() or "Manual stock out"
    previous_stock = product["quantity"]
    new_stock = previous_stock - quantity

    db.execute("UPDATE products SET quantity = ? WHERE id = ?", (new_stock, product_id))
    db.execute("""
        INSERT INTO stock_movements (product_id, movement_type, quantity, previous_stock, new_stock, note)
        VALUES (?, 'OUT', ?, ?, ?, ?)
    """, (product_id, quantity, previous_stock, new_stock, note))
    db.commit()

    flash(f'Removed {quantity} units from "{product["name"]}".', "success")
    return redirect(url_for("stock"))


@app.route("/stock/history")
@login_required
def stock_history():
    db = get_db()
    product_id = request.args.get("product", "")

    sql = """
        SELECT stock_movements.*, products.name AS product_name
        FROM stock_movements
        JOIN products ON products.id = stock_movements.product_id
        WHERE 1=1
    """
    params = []
    if product_id:
        sql += " AND stock_movements.product_id = ?"
        params.append(product_id)
    sql += " ORDER BY stock_movements.id DESC LIMIT 300"

    movements = db.execute(sql, params).fetchall()
    all_products = db.execute("SELECT id, name FROM products ORDER BY name").fetchall()
    return render_template("stock_history.html", movements=movements, products=all_products, selected_product=product_id)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    print("=" * 47)
    print(f"{APP_NAME} SERVER STARTING")
    print("=" * 47)
    print("APP FILE:", os.path.abspath(__file__))
    print("DATABASE:", DB_PATH)
    print("DATABASE EXISTS:", os.path.exists(DB_PATH))
    app.run(host="0.0.0.0", port=5000, debug=True)
