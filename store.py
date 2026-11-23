"""
store.py - everything about the database
=========================================
Tables, categories, the one-time upgrade from the old (v1) single-property
layout, automatic daily backups and posting of recurring bills.
All data lives in one SQLite file: data/expenses.db
"""
import os, shutil, sqlite3, datetime, calendar, glob
from zoneinfo import ZoneInfo
from flask import g

DATA_DIR = os.environ.get("DATA_DIR", "data")            # folder where the database lives
DB_FILE = os.path.join(DATA_DIR, "expenses.db")          # the database file itself
RECEIPT_DIR = os.path.join(DATA_DIR, "receipts")         # uploaded receipt photos / PDFs
BACKUP_DIR = os.path.join(DATA_DIR, "backups")           # automatic daily copies
KEEP_BACKUPS = int(os.environ.get("KEEP_BACKUPS", "14")) # how many daily copies to keep
TIMEZONE = os.environ.get("TZ", "America/New_York")      # so "today" matches your clock
DEFAULT_PROPERTY = os.environ.get("PROPERTY_NAME", "My Rental Property")  # name used on first start
SCHEMA_VERSION = 2

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# ---------- CATEGORIES ----------
# Each category is linked to its line on IRS Schedule E (Form 1040) so the tax
# summary fills itself in. None = not a deductible expense line (still counts
# toward cash flow).
EXPENSE_CATEGORIES = [
    ("Repairs", 14, "Fixing something that broke: plumber, appliance repair, patching"),
    ("Cleaning & maintenance", 7, "Routine upkeep: cleaning, lawn, filters, pest control"),
    ("Management fees", 11, "Monthly property manager fee"),
    ("Commissions", 8, "Leasing / agent fees for placing a tenant"),
    ("HOA dues", 19, "Homeowners association"),
    ("Insurance", 9, "Landlord / hazard / umbrella insurance"),
    ("Property taxes", 16, "Real estate taxes"),
    ("Mortgage interest", 12, "Interest part of the mortgage payment"),
    ("Mortgage principal", None, "Principal part of the payment - not deductible, but it is cash out"),
    ("Utilities", 17, "Water, trash, electric, gas you pay"),
    ("Supplies", 15, "Small items: bulbs, batteries, tools, office supplies"),
    ("Advertising", 5, "Listing sites, signs"),
    ("Auto & travel", 6, "Mileage, flights and meals for property trips"),
    ("Legal & professional", 10, "Accountant, attorney, inspections"),
    ("Other interest", 13, "Interest on other loans for the property"),
    ("Capital improvement", None, "Big upgrades (roof, HVAC, new appliances) - depreciated over years"),
    ("Other", 19, "Anything else"),
]
INCOME_CATEGORIES = [
    ("Rent", 3, "Monthly rent"),
    ("Late fees", 3, "Late rent fees charged to the tenant"),
    ("Pet fees", 3, "Pet rent or pet fees"),
    ("Kept security deposit", 3, "Part of a deposit you kept for damage or unpaid rent"),
    ("Other income", 3, "Laundry, parking, application fees..."),
]
EXPENSE_NAMES = [c[0] for c in EXPENSE_CATEGORIES]
INCOME_NAMES = [c[0] for c in INCOME_CATEGORIES]
CATEGORY_LINE = {c[0]: c[1] for c in EXPENSE_CATEGORIES + INCOME_CATEGORIES}
CATEGORY_HINT = {c[0]: c[2] for c in EXPENSE_CATEGORIES + INCOME_CATEGORIES}
# Not "operating" costs: left out of NOI / cap rate (they are financing or capital).
NON_OPERATING = {"Mortgage interest", "Mortgage principal", "Other interest", "Capital improvement"}
# Payments that never need a 1099-NEC (banks, insurers, government, HOA, utilities)
NO_1099 = ("Mortgage interest", "Mortgage principal", "Other interest", "Insurance", "Property taxes", "Utilities", "HOA dues")

SCHEDULE_E_LINES = [
    (3, "Rents received"), (5, "Advertising"), (6, "Auto and travel"), (7, "Cleaning and maintenance"),
    (8, "Commissions"), (9, "Insurance"), (10, "Legal and other professional fees"), (11, "Management fees"),
    (12, "Mortgage interest paid to banks"), (13, "Other interest"), (14, "Repairs"), (15, "Supplies"),
    (16, "Taxes"), (17, "Utilities"), (18, "Depreciation expense"), (19, "Other"),
]

# Recovery periods offered for capital improvements (years, label)
DEPRECIATION_CHOICES = [(27.5, "27.5 years - building parts (roof, HVAC, windows, flooring)"),
                        (15, "15 years - land improvements (fence, driveway, landscaping)"),
                        (7, "7 years - furniture"),
                        (5, "5 years - appliances, carpet")]

# Common maintenance tasks offered as one-tap suggestions (title, every N months)
SUGGESTED_TASKS = [("Replace HVAC filter", 3), ("Test smoke & CO detectors", 6), ("Clean gutters", 6),
                   ("Service HVAC system", 12), ("Flush water heater", 12), ("Pest control", 3),
                   ("Clean dryer vent", 12), ("Inspect roof", 12)]

# Old free-text categories from v1 -> new categories
OLD_CATEGORY_MAP = {"travel": "Auto & travel", "repairs": "Repairs", "maintenance": "Cleaning & maintenance",
                    "fees": "Other", "office": "Supplies", "other": "Other"}


def today():
    """Today's date in your time zone (set TZ in docker-compose.yml)."""
    try: return datetime.datetime.now(ZoneInfo(TIMEZONE)).date()
    except Exception: return datetime.date.today()


# ---------- CONNECTION ----------
def db():
    """Open (once per request) a connection to the database."""
    if "db" not in g:
        g.db = connect()
    return g.db

def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row                       # lets us read columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def close_db(_=None):
    conn = g.pop("db", None)
    if conn: conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, address TEXT, units INTEGER DEFAULT 1,
    purchase_date TEXT, purchase_price REAL, land_value REAL, closing_costs REAL,
    down_payment REAL, current_value REAL, in_service_date TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, trade TEXT, phone TEXT, email TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS leases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    unit TEXT, tenant TEXT NOT NULL, phone TEXT, email TEXT,
    start_date TEXT NOT NULL, end_date TEXT, rent REAL NOT NULL DEFAULT 0, deposit REAL DEFAULT 0,
    due_day INTEGER DEFAULT 1, grace_days INTEGER DEFAULT 5, notes TEXT);
CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    description TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL,
    every_months INTEGER NOT NULL DEFAULT 1, start_date TEXT NOT NULL, end_date TEXT,
    vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS recurring_posted (                 -- remembers which bills were already added
    recurring_id INTEGER NOT NULL, period TEXT NOT NULL, PRIMARY KEY (recurring_id, period));
CREATE TABLE IF NOT EXISTS transactions (                     -- every dollar in or out
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('expense','income')),
    date TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
    amount REAL NOT NULL, notes TEXT,
    vendor_id INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    lease_id INTEGER REFERENCES leases(id) ON DELETE SET NULL,
    recurring_id INTEGER REFERENCES recurring(id) ON DELETE SET NULL,
    depr_years REAL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS tx_prop_date ON transactions(property_id, date);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    filename TEXT, stored TEXT NOT NULL, uploaded TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS tasks (                            -- maintenance reminders
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    title TEXT NOT NULL, every_months INTEGER DEFAULT 0, next_due TEXT, done INTEGER DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS task_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    done_date TEXT NOT NULL, note TEXT,
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL);
"""


def init_db():
    """Create tables on first start, and upgrade an older database if found."""
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    conn = connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if version < SCHEMA_VERSION and "expenses" in tables:
        conn.close()
        shutil.copy(DB_FILE, os.path.join(DATA_DIR, "backup-before-upgrade.db"))   # safety copy
        conn = connect()
    conn.executescript(SCHEMA)
    if not conn.execute("SELECT 1 FROM properties").fetchone():
        conn.execute("INSERT INTO properties (name) VALUES (?)", (DEFAULT_PROPERTY,))
    if version < SCHEMA_VERSION and "expenses" in tables:
        migrate_v1(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()


def map_old_category(text):
    """Turn a v1 free-text category into one of the new categories."""
    t = (text or "").strip()
    for name in EXPENSE_NAMES:
        if name.lower() == t.lower(): return name, ""
    if t.lower() in OLD_CATEGORY_MAP: return OLD_CATEGORY_MAP[t.lower()], ""
    return "Other", (f"Old category: {t}" if t else "")


def migrate_v1(conn):
    """Move data from the old single-property tables into the new layout.
    The old tables are kept (renamed to legacy_*) and nothing is deleted."""
    pid = conn.execute("SELECT id FROM properties ORDER BY id LIMIT 1").fetchone()[0]
    for e in conn.execute("SELECT * FROM expenses").fetchall():
        cat, extra = map_old_category(e["category"])
        notes = [n for n in (e["notes"], extra) if n]
        date = e["date"]
        if not date:
            date = f"{e['year']}-01-01"; notes.append("No date in original record")
        conn.execute("INSERT INTO transactions (property_id,kind,date,description,category,amount,notes) VALUES (?,?,?,?,?,?,?)",
                     (pid, "expense", date, e["description"], cat, e["amount"], "; ".join(notes)))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "monthly" in tables:
        for m in conn.execute("SELECT * FROM monthly ORDER BY year, month").fetchall():
            date, note = f"{m['year']}-{m['month']:02d}-01", (m["note"] or "").strip()
            for col, desc, cat in (("mgmt_fee", "Management fee", "Management fees"),
                                   ("agent", "Due to agent", "Commissions"), ("hoa", "HOA", "HOA dues")):
                if m[col]:
                    conn.execute("INSERT INTO transactions (property_id,kind,date,description,category,amount,notes) VALUES (?,?,?,?,?,?,?)",
                                 (pid, "expense", date, desc, cat, m[col], note)); note = ""
        conn.execute("ALTER TABLE monthly RENAME TO legacy_monthly")
    conn.execute("ALTER TABLE expenses RENAME TO legacy_expenses")


# ---------- AUTOMATIC BACKUPS ----------
def daily_backup():
    """Once a day, save a copy of the database in data/backups (keeps the newest KEEP_BACKUPS)."""
    if KEEP_BACKUPS <= 0 or not os.path.exists(DB_FILE): return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    target = os.path.join(BACKUP_DIR, f"expenses-{today().isoformat()}.db")
    if os.path.exists(target): return
    src, dst = sqlite3.connect(DB_FILE), sqlite3.connect(target)
    with dst: src.backup(dst)                            # safe copy even while the app is running
    src.close(); dst.close()
    for old in sorted(glob.glob(os.path.join(BACKUP_DIR, "expenses-*.db")))[:-KEEP_BACKUPS]:
        os.remove(old)


# ---------- RECURRING BILLS ----------
def add_months(d, n):
    """Same day n months later (clamped to the end of shorter months)."""
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def due_dates(r, until):
    """All dates a recurring bill falls on, from its start up to 'until'."""
    start = datetime.date.fromisoformat(r["start_date"])
    end = datetime.date.fromisoformat(r["end_date"]) if r["end_date"] else None
    i, out = 0, []
    while True:
        d = add_months(start, i * max(1, r["every_months"]))
        if d > until or (end and d > end): return out
        out.append(d); i += 1

def post_recurring(conn=None):
    """Add any recurring bills that have come due and were not added yet.
    Returns how many were added. Deleting a posted bill does not bring it back."""
    conn = conn or db()
    added, t = 0, today()
    for r in conn.execute("SELECT * FROM recurring WHERE active=1").fetchall():
        for d in due_dates(r, t):
            period = d.strftime("%Y-%m-%d")
            if conn.execute("SELECT 1 FROM recurring_posted WHERE recurring_id=? AND period=?", (r["id"], period)).fetchone():
                continue
            conn.execute("INSERT INTO transactions (property_id,kind,date,description,category,amount,vendor_id,recurring_id) "
                         "VALUES (?,?,?,?,?,?,?,?)", (r["property_id"], "expense", period, r["description"],
                                                      r["category"], r["amount"], r["vendor_id"], r["id"]))
            conn.execute("INSERT INTO recurring_posted VALUES (?,?)", (r["id"], period))
            added += 1
    if added: conn.commit()
    return added
