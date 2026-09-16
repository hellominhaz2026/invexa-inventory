# INVEXA — Inventory & Sales Management System

A complete redesign of the original "Inventory Pro" Flask project — same data,
same database, brand new premium UI/UX, and a few new features.

## What changed vs. the original project

- **All-new UI/UX.** A dark/light "ledger" theme (deep teal + brass gold +
  teal accents, serif/sans/mono type system) — built from scratch, nothing
  reused from the old templates.
- **Customers module.** The old app could only create a customer *inline*
  while making a sale. INVEXA adds a full Customers page: list, search, add,
  edit, and each customer now shows order count + lifetime value.
- **Analytics dashboard.** Revenue trend (14 days), top-selling products, and
  stock value by category — all charted with Chart.js, computed live from
  your database.
- **CSV export** for both Products and Sales.
- **Stock Ledger.** One screen to see current stock, do a quick stock-in /
  stock-out with a note, and a full movement history log.
- **Safer deletes.** Deleting a product or customer that already has sales
  attached is now blocked with a clear message (instead of crashing) — your
  invoice history is never silently broken.
- **Light / dark theme toggle**, mobile-friendly collapsible sidebar,
  printable invoices.

## Your data is safe

`app.py` creates tables with `CREATE TABLE IF NOT EXISTS` using the **exact
same table and column names** as the original project (`users`, `categories`,
`products`, `customers`, `suppliers`, `sales`, `sale_items`,
`stock_movements`, `stock_transactions`). If you already have an
`inventory.db`, just copy it into this folder next to `app.py` — no
migration needed, nothing will be dropped or renamed. The login stays the
same too (default `admin` / `admin123` if it's a fresh database).

## Run it locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`.

To use your existing data, copy your old `inventory.db` into this folder
(next to `app.py`) before starting the server.

## Run it in Google Colab (same workflow as before)

```python
!pip install flask -q

# If you have an existing inventory.db in Drive, copy it in first:
# import shutil; shutil.copy("/content/drive/MyDrive/inventory_project/inventory.db", "/content/invexa/inventory.db")

import subprocess, time
process = subprocess.Popen(["python", "/content/invexa/app.py"])
time.sleep(3)

from google.colab.output import eval_js
print(eval_js("google.colab.kernel.proxyPort(5000)"))
```

(Upload/unzip this `invexa` folder to `/content/invexa` first.)

## Project structure

```
invexa/
├── app.py                  # All routes + database setup
├── requirements.txt
├── inventory.db             # created automatically on first run
├── templates/                # 18 Jinja2 templates (all-new UI)
└── static/
    ├── css/style.css        # Design system
    └── js/main.js            # Theme toggle, charts, POS calculator, etc.
```

## Notes

- Passwords are still stored in plain text in the `users` table, matching the
  original project, so your existing accounts keep working unchanged. If you
  ever open this up beyond trusted local use, switch to hashed passwords
  (`werkzeug.security.generate_password_hash`) first.
- Currency is shown as ৳ (BDT), matching the original.
