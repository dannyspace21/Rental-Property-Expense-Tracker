"""
Rental Property Tracker
=======================
A small, private web app for your rental properties: income, expenses,
recurring bills, rent, tenants, maintenance, vendors and tax reports.

  app.py      - the web pages (this file)
  store.py    - the database, categories, backups and recurring bills
  reports.py  - totals, rent roll, depreciation, Schedule E, metrics, PDF
  templates/  - the HTML for each page
  static/     - the stylesheet, a little JavaScript and the app icon

Data is saved in data/expenses.db and receipts in data/receipts/ (no login,
meant for your home network).
"""
import os, io, csv, uuid, zipfile, tempfile, sqlite3, datetime, re, shutil
from flask import (Flask, render_template, request, redirect, url_for, flash, send_file, abort,
                   send_from_directory, make_response)
from urllib.parse import urlsplit
from werkzeug.utils import secure_filename
from openpyxl import load_workbook

import store, reports
from store import db, today, MONTHS
from reports import money

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24).hex()   # only used for the little pop-up messages
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024                     # biggest upload: 40 MB
app.teardown_appcontext(store.close_db)
app.jinja_env.filters["money"] = money

@app.template_filter("nice")
def nice_date(text):
    """Show 2026-11-12 as 'Nov 12' (adds the year when it isn't this year)."""
    try: d = datetime.date.fromisoformat(str(text))
    except ValueError: return text or ""
    return f"{d:%b} {d.day}" + ("" if d.year == today().year else f", {d.year}")
RECEIPT_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".pdf"}


# ---------- SMALL HELPERS ----------
def num(text):
    """Turn typed text like '1,200.50' or '$40' into a number (blank = 0)."""
    try: return round(float(str(text or "").replace("$", "").replace(",", "").strip() or 0), 2)
    except ValueError: return 0.0

def num_or_none(text):
    return num(text) if str(text or "").strip() else None

def clean(name):
    return (request.form.get(name) or "").strip()

def valid_date(text, fallback=None):
    try: return datetime.date.fromisoformat(text).isoformat()
    except (TypeError, ValueError): return fallback

def all_properties():
    return db().execute("SELECT * FROM properties ORDER BY name").fetchall()

def current_pid():
    """The property picked in the header (None = all properties)."""
    props = all_properties()
    if len(props) == 1: return props[0]["id"]
    want = request.cookies.get("pid", "all")
    return int(want) if want.isdigit() and any(p["id"] == int(want) for p in props) else None

def default_pid():
    """Property to pre-select in forms: the current one, or the first."""
    return current_pid() or all_properties()[0]["id"]

def year_arg():
    y = request.args.get("year", type=int)
    return y if y and 1900 < y < 3000 else today().year

def local_path(url):
    """Keep only the path part of a link (e.g. the page you came from)."""
    parts = urlsplit(url or "")
    return parts.path + (f"?{parts.query}" if parts.query else "") if parts.path.startswith("/") else ""

def back(default):
    """Go back to where the user came from (only to pages on this site)."""
    nxt = request.values.get("next") or ""
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else default)

def vendor_id_for(name):
    """Find a vendor by name, or create them (so you can type a new name right in the form)."""
    name = (name or "").strip()
    if not name: return None
    row = db().execute("SELECT id FROM vendors WHERE lower(name)=lower(?)", (name,)).fetchone()
    if row: return row["id"]
    return db().execute("INSERT INTO vendors (name) VALUES (?)", (name,)).lastrowid

def save_receipts(tx_id):
    """Store uploaded receipt photos/PDFs for a transaction."""
    saved = 0
    for f in request.files.getlist("receipts"):
        if not f or not f.filename: continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in RECEIPT_TYPES:
            flash(f"Skipped {f.filename}: only photos and PDFs can be attached."); continue
        stored = f"{uuid.uuid4().hex}{ext}"
        f.save(os.path.join(store.RECEIPT_DIR, stored))
        db().execute("INSERT INTO attachments (transaction_id, filename, stored) VALUES (?,?,?)",
                     (tx_id, secure_filename(f.filename) or stored, stored))
        saved += 1
    return saved


# ---------- RUNS BEFORE EVERY PAGE ----------
_last_daily = {"day": None}

@app.before_request
def daily_jobs():
    """Once a day: make a backup and add recurring bills that came due."""
    if request.endpoint == "static": return
    if _last_daily["day"] != today():
        store.daily_backup()
        store.post_recurring()
        _last_daily["day"] = today()

@app.context_processor
def page_globals():
    """Values every page can use."""
    if request.endpoint == "static": return {}
    props = all_properties()
    pid = current_pid()
    return {"props": props, "pid": pid, "prop": next((p for p in props if p["id"] == pid), None),
            "today": today(), "MONTHS": MONTHS, "EXP_CATS": store.EXPENSE_CATEGORIES,
            "INC_CATS": store.INCOME_CATEGORIES, "LINE": store.CATEGORY_LINE}


# ---------- PROPERTY SWITCHER ----------
@app.route("/switch")
def switch_property():
    resp = back(url_for("home"))
    resp.set_cookie("pid", request.args.get("pid", "all"), max_age=10 * 365 * 24 * 3600, samesite="Lax")
    return resp


# ---------- HOME ----------
@app.route("/")
def home():
    pid, year = current_pid(), year_arg()
    s = reports.year_summary(pid, year)
    per_property = []
    if pid is None:
        for p in all_properties():
            ps = reports.year_summary(p["id"], year)
            per_property.append({"p": p, "income": ps["income"], "expense": ps["expense"], "net": ps["net"]})
    return render_template("home.html", year=year, years=reports.years_with_data(pid), s=s,
                           chart=reports.month_chart(s["months"]), alerts=reports.alerts(pid),
                           recent=reports.find_transactions(pid=pid, limit=6), per_property=per_property)


# ---------- MONEY (all income & expenses) ----------
def money_filters():
    a = request.args
    f = {k: (a.get(k) or "").strip() for k in ("q", "kind", "category", "vendor", "from", "to", "min", "max", "year")}
    if not any(f.values()): f["year"] = str(today().year)         # default view: this year
    return f

def filtered(f, pid):
    return reports.find_transactions(pid=pid, year=f["year"] if f["year"].isdigit() else None, kind=f["kind"] or None,
                                     category=f["category"] or None, vendor_id=int(f["vendor"]) if f["vendor"].isdigit() else None,
                                     q=f["q"] or None, date_from=valid_date(f["from"]), date_to=valid_date(f["to"]),
                                     min_amt=num(f["min"]) if f["min"] else None, max_amt=num(f["max"]) if f["max"] else None)

@app.route("/money")
def money_list():
    pid, f = current_pid(), money_filters()
    rows = filtered(f, pid)
    vendors = db().execute("SELECT id, name FROM vendors ORDER BY name").fetchall()
    return render_template("money.html", rows=rows, t=reports.totals(rows), f=f, vendors=vendors,
                           years=reports.years_with_data(pid),
                           advanced=any(f[k] for k in ("category", "vendor", "from", "to", "min", "max")))

@app.route("/money/export.csv")
def money_csv():
    rows = filtered(money_filters(), current_pid())
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["Date", "Type", "Property", "Description", "Category", "Schedule E line", "Amount", "Vendor", "Tenant", "Notes", "Receipts"])
    for r in rows:
        w.writerow([r["date"], r["kind"].title(), r["property"], r["description"], r["category"],
                    store.CATEGORY_LINE.get(r["category"]) or "", f"{r['amount']:.2f}", r["vendor"] or "",
                    r["tenant"] or "", r["notes"] or "", r["receipts"]])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=transactions-{today().isoformat()}.csv"
    return resp

@app.route("/money/new")
@app.route("/money/<int:tx_id>/edit")
def money_form(tx_id=None):
    tx = db().execute("SELECT t.*, v.name AS vendor FROM transactions t LEFT JOIN vendors v ON v.id=t.vendor_id"
                      " WHERE t.id=?", (tx_id,)).fetchone() if tx_id else None
    if tx_id and not tx: abort(404)
    a = request.args
    d = {"kind": a.get("kind", "expense"), "date": valid_date(a.get("date"), today().isoformat()),
         "category": a.get("category", ""), "amount": a.get("amount", ""), "description": a.get("description", ""),
         "property_id": a.get("property", type=int) or default_pid(), "lease_id": a.get("lease", type=int),
         "vendor": a.get("vendor", ""), "notes": "", "depr_years": 27.5}
    if tx: d.update({k: tx[k] for k in tx.keys() if k in d}); d["vendor"] = tx["vendor"] or ""
    files = db().execute("SELECT * FROM attachments WHERE transaction_id=?", (tx_id,)).fetchall() if tx else []
    vendors = [r["name"] for r in db().execute("SELECT name FROM vendors ORDER BY name")]
    return render_template("entry.html", tx=tx, d=d, files=files, vendors=vendors, leases=reports.leases(),
                           depr=store.DEPRECIATION_CHOICES, next=a.get("next") or local_path(request.referrer))

@app.route("/money/save", methods=["POST"])
def money_save():
    f = request.form
    kind = "income" if f.get("kind") == "income" else "expense"
    names = store.INCOME_NAMES if kind == "income" else store.EXPENSE_NAMES
    category = f.get(f"category_{kind}") or f.get("category")
    if category not in names: category = "Other income" if kind == "income" else "Other"
    amount = abs(num(f.get("amount")))
    if not amount:
        flash("Please enter an amount."); return redirect(request.referrer or url_for("money_form"))
    lease_id = f.get("lease_id", type=int) if kind == "income" else None
    pid = f.get("property_id", type=int) or default_pid()
    if lease_id:                                       # rent always belongs to the lease's property
        row = db().execute("SELECT property_id FROM leases WHERE id=?", (lease_id,)).fetchone()
        pid = row["property_id"] if row else pid
    vals = {"property_id": pid, "kind": kind, "date": valid_date(f.get("date"), today().isoformat()),
            "description": clean("description") or category, "category": category, "amount": amount,
            "notes": clean("notes"), "vendor_id": vendor_id_for(f.get("vendor")) if kind == "expense" else None,
            "lease_id": lease_id,
            "depr_years": num(f.get("depr_years")) or 27.5 if category == "Capital improvement" else None}
    tx_id = f.get("id", type=int)
    if tx_id:
        db().execute(f"UPDATE transactions SET {', '.join(k + '=?' for k in vals)} WHERE id=?", (*vals.values(), tx_id))
        msg = "Saved."
    else:
        tx_id = db().execute(f"INSERT INTO transactions ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})",
                             tuple(vals.values())).lastrowid
        msg = f"{'Income' if kind == 'income' else 'Expense'} added: {money(amount)} · {vals['description']}"
    n = save_receipts(tx_id)
    db().commit()
    flash(msg + (f" ({n} receipt{'s' if n > 1 else ''} attached)" if n else ""))
    if f.get("again"):
        return redirect(url_for("money_form", kind=kind, date=vals["date"], property=pid))
    return back(url_for("money_list"))

@app.route("/money/<int:tx_id>/delete", methods=["POST"])
def money_delete(tx_id):
    for a in db().execute("SELECT stored FROM attachments WHERE transaction_id=?", (tx_id,)).fetchall():
        try: os.remove(os.path.join(store.RECEIPT_DIR, a["stored"]))
        except OSError: pass
    db().execute("DELETE FROM transactions WHERE id=?", (tx_id,)); db().commit()
    flash("Deleted.")
    return back(url_for("money_list"))

@app.route("/receipt/<int:att_id>")
def receipt(att_id):
    a = db().execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone() or abort(404)
    return send_from_directory(os.path.abspath(store.RECEIPT_DIR), a["stored"], download_name=a["filename"])

@app.route("/receipt/<int:att_id>/delete", methods=["POST"])
def receipt_delete(att_id):
    a = db().execute("SELECT * FROM attachments WHERE id=?", (att_id,)).fetchone() or abort(404)
    try: os.remove(os.path.join(store.RECEIPT_DIR, a["stored"]))
    except OSError: pass
    db().execute("DELETE FROM attachments WHERE id=?", (att_id,)); db().commit()
    flash("Receipt removed.")
    return redirect(url_for("money_form", tx_id=a["transaction_id"]))


# ---------- RECURRING BILLS ----------
@app.route("/bills")
def bills():
    pid = current_pid()
    where, args = reports.prop_filter(pid, "r.property_id")
    rows = db().execute(f"SELECT r.*, p.name AS property, v.name AS vendor FROM recurring r JOIN properties p ON p.id=r.property_id"
                        f" LEFT JOIN vendors v ON v.id=r.vendor_id WHERE 1=1{where} ORDER BY r.active DESC, p.name, r.description", args).fetchall()
    edit = db().execute("SELECT r.*, v.name AS vendor FROM recurring r LEFT JOIN vendors v ON v.id=r.vendor_id WHERE r.id=?",
                        (request.args.get("edit", type=int),)).fetchone()
    monthly = sum(r["amount"] / max(1, r["every_months"]) for r in rows if r["active"])
    vendors = [r["name"] for r in db().execute("SELECT name FROM vendors ORDER BY name")]
    return render_template("bills.html", rows=rows, edit=edit, monthly=monthly, vendors=vendors, default_pid=default_pid())

@app.route("/bills/save", methods=["POST"])
def bills_save():
    f = request.form
    cat = f.get("category") if f.get("category") in store.EXPENSE_NAMES else "Other"
    vals = (f.get("property_id", type=int) or default_pid(), clean("description") or cat, cat, abs(num(f.get("amount"))),
            f.get("every_months", type=int) or 1, valid_date(f.get("start_date"), today().isoformat()),
            valid_date(f.get("end_date")), vendor_id_for(f.get("vendor")), 1 if f.get("active", "1") == "1" else 0)
    rid = f.get("id", type=int)
    if rid:
        db().execute("UPDATE recurring SET property_id=?,description=?,category=?,amount=?,every_months=?,start_date=?,"
                     "end_date=?,vendor_id=?,active=? WHERE id=?", vals + (rid,))
    else:
        db().execute("INSERT INTO recurring (property_id,description,category,amount,every_months,start_date,end_date,vendor_id,active)"
                     " VALUES (?,?,?,?,?,?,?,?,?)", vals)
    db().commit()
    added = store.post_recurring()
    flash(f"Bill saved. {added} payment{'s' if added != 1 else ''} up to today {'were' if added != 1 else 'was'} added to Money."
          if added else "Bill saved. It will be added to Money automatically each time it comes due.")
    return redirect(url_for("bills"))

@app.route("/bills/<int:rid>/delete", methods=["POST"])
def bills_delete(rid):
    db().execute("DELETE FROM recurring WHERE id=?", (rid,))
    db().execute("DELETE FROM recurring_posted WHERE recurring_id=?", (rid,)); db().commit()
    flash("Recurring bill removed. Payments already recorded were kept.")
    return redirect(url_for("bills"))


# ---------- RENT & LEASES ----------
@app.route("/rent")
def rent():
    pid, year = current_pid(), year_arg()
    all_leases = reports.leases(pid)
    t = today()
    return render_template("rent.html", year=year, now=reports.rent_this_month(pid), roll=reports.rent_roll(pid, year),
                           leases=all_leases, years=sorted(set(reports.years_with_data(pid)) | {t.year}),
                           current_ids={l["id"] for l in reports.leases(pid, current_only=True)})

@app.route("/rent/<int:lease_id>/paid", methods=["POST"])
def rent_paid(lease_id):
    """One tap: record the rest of a month's rent as received."""
    l = db().execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone() or abort(404)
    y, m = request.form.get("year", type=int), request.form.get("month", type=int)
    cell = reports.rent_cell(l, y, m, reports.rent_paid_by_month(lease_id, y).get(m, 0.0))
    amount = num(request.form.get("amount")) or cell["balance"]
    if amount <= 0:
        flash("That month is already paid."); return back(url_for("rent"))
    t = today()
    date = t.isoformat() if (y, m) == (t.year, t.month) else cell.get("due", f"{y}-{m:02d}-01")
    db().execute("INSERT INTO transactions (property_id,kind,date,description,category,amount,lease_id) VALUES (?,?,?,?,?,?,?)",
                 (l["property_id"], "income", date, f"Rent - {MONTHS[m-1]} ({l['tenant']})", "Rent", amount, lease_id))
    db().commit()
    flash(f"Recorded {money(amount)} rent from {l['tenant']} for {MONTHS[m-1]}.")
    return back(url_for("rent"))

@app.route("/leases/new")
@app.route("/leases/<int:lease_id>/edit")
def lease_form(lease_id=None):
    l = db().execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone() if lease_id else None
    if lease_id and not l: abort(404)
    payments = reports.find_transactions(lease_id=lease_id) if l else []
    return render_template("lease.html", l=l, payments=payments, default_pid=default_pid())

@app.route("/leases/save", methods=["POST"])
def lease_save():
    f = request.form
    if not clean("tenant"):
        flash("Please enter the tenant's name."); return redirect(request.referrer or url_for("lease_form"))
    vals = (f.get("property_id", type=int) or default_pid(), clean("unit"), clean("tenant"), clean("phone"), clean("email"),
            valid_date(f.get("start_date"), today().isoformat()), valid_date(f.get("end_date")), num(f.get("rent")),
            num(f.get("deposit")), min(28, max(1, f.get("due_day", type=int) or 1)), max(0, f.get("grace_days", type=int) or 0),
            clean("notes"))
    lid = f.get("id", type=int)
    if lid:
        db().execute("UPDATE leases SET property_id=?,unit=?,tenant=?,phone=?,email=?,start_date=?,end_date=?,rent=?,deposit=?,"
                     "due_day=?,grace_days=?,notes=? WHERE id=?", vals + (lid,))
    else:
        db().execute("INSERT INTO leases (property_id,unit,tenant,phone,email,start_date,end_date,rent,deposit,due_day,grace_days,notes)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", vals)
    db().commit()
    flash("Lease saved.")
    return redirect(url_for("rent"))

@app.route("/leases/<int:lease_id>/delete", methods=["POST"])
def lease_delete(lease_id):
    db().execute("DELETE FROM leases WHERE id=?", (lease_id,)); db().commit()
    flash("Lease deleted. Rent payments already recorded were kept.")
    return redirect(url_for("rent"))


# ---------- UPKEEP (maintenance reminders) ----------
@app.route("/upkeep")
def upkeep():
    pid = current_pid()
    where, args = reports.prop_filter(pid, "t.property_id")
    tasks = db().execute(f"SELECT t.*, p.name AS property FROM tasks t JOIN properties p ON p.id=t.property_id"
                         f" WHERE 1=1{where} ORDER BY t.done, t.next_due IS NULL, t.next_due", args).fetchall()
    log = db().execute(f"SELECT g.*, t.title, p.name AS property, x.amount FROM task_log g JOIN tasks t ON t.id=g.task_id"
                       f" JOIN properties p ON p.id=t.property_id LEFT JOIN transactions x ON x.id=g.transaction_id"
                       f" WHERE 1=1{where} ORDER BY g.done_date DESC, g.id DESC LIMIT 40", args).fetchall()
    have = {t["title"].lower() for t in tasks if not t["done"]}
    vendors = [r["name"] for r in db().execute("SELECT name FROM vendors ORDER BY name")]
    edit = db().execute("SELECT * FROM tasks WHERE id=?", (request.args.get("edit", type=int),)).fetchone()
    return render_template("upkeep.html", tasks=tasks, log=log, edit=edit, vendors=vendors, default_pid=default_pid(),
                           suggestions=[s for s in store.SUGGESTED_TASKS if s[0].lower() not in have],
                           soon=(today() + datetime.timedelta(days=14)).isoformat())

@app.route("/upkeep/save", methods=["POST"])
def upkeep_save():
    f = request.form
    vals = (f.get("property_id", type=int) or default_pid(), clean("title") or "Task", max(0, f.get("every_months", type=int) or 0),
            valid_date(f.get("next_due"), today().isoformat()), clean("notes"))
    tid = f.get("id", type=int)
    if tid: db().execute("UPDATE tasks SET property_id=?,title=?,every_months=?,next_due=?,notes=? WHERE id=?", vals + (tid,))
    else: db().execute("INSERT INTO tasks (property_id,title,every_months,next_due,notes) VALUES (?,?,?,?,?)", vals)
    db().commit()
    flash("Reminder saved.")
    return redirect(url_for("upkeep"))

@app.route("/upkeep/suggest", methods=["POST"])
def upkeep_suggest():
    title, every = request.form.get("title", ""), request.form.get("every", type=int) or 12
    pid = request.form.get("property_id", type=int) or default_pid()
    db().execute("INSERT INTO tasks (property_id,title,every_months,next_due) VALUES (?,?,?,?)",
                 (pid, title, every, today().isoformat()))
    db().commit()
    flash(f"Added reminder: {title} (every {every} months). Tap Done when you've done it.")
    return redirect(url_for("upkeep"))

@app.route("/upkeep/<int:tid>/done", methods=["POST"])
def upkeep_done(tid):
    t = db().execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone() or abort(404)
    f = request.form
    when = valid_date(f.get("done_date"), today().isoformat())
    tx_id, cost = None, num(f.get("cost"))
    if cost:
        cat = f.get("category") if f.get("category") in store.EXPENSE_NAMES else "Cleaning & maintenance"
        tx_id = db().execute("INSERT INTO transactions (property_id,kind,date,description,category,amount,vendor_id,notes)"
                             " VALUES (?,?,?,?,?,?,?,?)", (t["property_id"], "expense", when, t["title"], cat, cost,
                                                           vendor_id_for(f.get("vendor")), clean("note"))).lastrowid
        save_receipts(tx_id)
    db().execute("INSERT INTO task_log (task_id,done_date,note,transaction_id) VALUES (?,?,?,?)", (tid, when, clean("note"), tx_id))
    if t["every_months"]:
        nxt = store.add_months(datetime.date.fromisoformat(when), t["every_months"]).isoformat()
        db().execute("UPDATE tasks SET next_due=? WHERE id=?", (nxt, tid))
        msg = f"Nice! “{t['title']}” is next due {nxt}."
    else:
        db().execute("UPDATE tasks SET done=1 WHERE id=?", (tid,)); msg = f"“{t['title']}” marked done."
    db().commit()
    flash(msg + (f" Cost of {money(cost)} added to Money." if cost else ""))
    return back(url_for("upkeep"))

@app.route("/upkeep/<int:tid>/delete", methods=["POST"])
def upkeep_delete(tid):
    db().execute("DELETE FROM tasks WHERE id=?", (tid,)); db().commit()
    flash("Reminder deleted.")
    return redirect(url_for("upkeep"))


# ---------- VENDORS ----------
@app.route("/vendors")
def vendors():
    year = year_arg()
    no1099 = ",".join("'%s'" % c for c in store.NO_1099)
    rows = db().execute("SELECT v.*, COALESCE(SUM(CASE WHEN substr(t.date,1,4)=? THEN t.amount END),0) AS year_total,"
                        f" COALESCE(SUM(CASE WHEN substr(t.date,1,4)=? AND t.category NOT IN ({no1099}) THEN t.amount END),0) AS nec_total,"
                        " COALESCE(SUM(t.amount),0) AS all_total, COUNT(t.id) AS jobs FROM vendors v"
                        " LEFT JOIN transactions t ON t.vendor_id=v.id AND t.kind='expense'"
                        " GROUP BY v.id ORDER BY year_total DESC, v.name", (str(year), str(year))).fetchall()
    return render_template("vendors.html", rows=rows, year=year, years=reports.years_with_data(None))

@app.route("/vendors/new")
@app.route("/vendors/<int:vid>")
def vendor_page(vid=None):
    v = db().execute("SELECT * FROM vendors WHERE id=?", (vid,)).fetchone() if vid else None
    if vid and not v: abort(404)
    rows = reports.find_transactions(vendor_id=vid) if v else []
    return render_template("vendor.html", v=v, rows=rows, total=sum(r["amount"] for r in rows))

@app.route("/vendors/save", methods=["POST"])
def vendor_save():
    vals = (clean("name") or "Unnamed", clean("trade"), clean("phone"), clean("email"), clean("notes"))
    vid = request.form.get("id", type=int)
    if vid: db().execute("UPDATE vendors SET name=?,trade=?,phone=?,email=?,notes=? WHERE id=?", vals + (vid,))
    else: vid = db().execute("INSERT INTO vendors (name,trade,phone,email,notes) VALUES (?,?,?,?,?)", vals).lastrowid
    db().commit()
    flash("Vendor saved.")
    return redirect(url_for("vendor_page", vid=vid))

@app.route("/vendors/<int:vid>/delete", methods=["POST"])
def vendor_delete(vid):
    db().execute("DELETE FROM vendors WHERE id=?", (vid,)); db().commit()
    flash("Vendor deleted. Their past expenses were kept.")
    return redirect(url_for("vendors"))


# ---------- PROPERTIES ----------
@app.route("/properties")
def properties():
    year = today().year
    rows = []
    for p in all_properties():
        s = reports.year_summary(p["id"], year)
        rows.append({"p": p, "s": s, "tenants": len(reports.leases(p["id"], current_only=True))})
    return render_template("properties.html", rows=rows, year=year)

@app.route("/properties/new")
@app.route("/properties/<int:prop_id>/edit")
def property_form(prop_id=None):
    p = db().execute("SELECT * FROM properties WHERE id=?", (prop_id,)).fetchone() if prop_id else None
    if prop_id and not p: abort(404)
    used = db().execute("SELECT COUNT(*) FROM transactions WHERE property_id=?", (prop_id,)).fetchone()[0] if p else 0
    return render_template("property.html", p=p, used=used, count=len(all_properties()))

@app.route("/properties/save", methods=["POST"])
def property_save():
    f = request.form
    vals = (clean("name") or "Unnamed property", clean("address"), max(1, f.get("units", type=int) or 1),
            valid_date(f.get("purchase_date")), num_or_none(f.get("purchase_price")), num_or_none(f.get("land_value")),
            num_or_none(f.get("closing_costs")), num_or_none(f.get("down_payment")), num_or_none(f.get("current_value")),
            valid_date(f.get("in_service_date")), clean("notes"))
    pid = f.get("id", type=int)
    if pid:
        db().execute("UPDATE properties SET name=?,address=?,units=?,purchase_date=?,purchase_price=?,land_value=?,closing_costs=?,"
                     "down_payment=?,current_value=?,in_service_date=?,notes=? WHERE id=?", vals + (pid,))
        db().commit(); flash("Property saved.")
        return redirect(url_for("properties"))
    pid = db().execute("INSERT INTO properties (name,address,units,purchase_date,purchase_price,land_value,closing_costs,"
                       "down_payment,current_value,in_service_date,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals).lastrowid
    db().commit()
    flash(f"Added {vals[0]}. It's now selected at the top of the page.")
    resp = redirect(url_for("properties"))
    resp.set_cookie("pid", str(pid), max_age=10 * 365 * 24 * 3600, samesite="Lax")
    return resp

@app.route("/properties/<int:prop_id>/delete", methods=["POST"])
def property_delete(prop_id):
    if len(all_properties()) <= 1:
        flash("You need at least one property."); return redirect(url_for("properties"))
    if db().execute("SELECT 1 FROM transactions WHERE property_id=?", (prop_id,)).fetchone():
        flash("This property has income or expenses recorded, so it can't be deleted. Delete those first.")
        return redirect(url_for("property_form", prop_id=prop_id))
    db().execute("DELETE FROM properties WHERE id=?", (prop_id,)); db().commit()
    flash("Property deleted.")
    resp = redirect(url_for("properties")); resp.set_cookie("pid", "all"); return resp


# ---------- REPORTS ----------
@app.route("/reports")
def reports_page():
    pid, year = current_pid(), year_arg()
    props = [p for p in all_properties() if pid is None or p["id"] == pid]
    yoy = []
    for y in reports.years_with_data(pid)[-6:]:
        s = reports.year_summary(pid, y)
        yoy.append({"year": y, "income": s["income"], "expense": s["expense"], "net": s["net"]})
    vendors_1099 = db().execute(
        "SELECT v.id, v.name, SUM(t.amount) AS total FROM transactions t JOIN vendors v ON v.id=t.vendor_id"
        " WHERE t.kind='expense' AND substr(t.date,1,4)=? AND t.category NOT IN (%s)" % ",".join("?" * len(store.NO_1099)) +
        (" AND t.property_id=?" if pid else "") +
        " GROUP BY v.id HAVING total >= 600 ORDER BY total DESC", [str(year), *store.NO_1099] + ([pid] if pid else [])).fetchall()
    return render_template("reports.html", year=year, years=reports.years_with_data(pid), se=reports.schedule_e(pid, year),
                           metrics=[(p, reports.metrics(p, year)) for p in props], yoy=yoy, vendors_1099=vendors_1099,
                           s=reports.year_summary(pid, year))

def report_title(pid):
    p = db().execute("SELECT name FROM properties WHERE id=?", (pid,)).fetchone() if pid else None
    return p["name"] if p else "All properties"

@app.route("/reports/<int:year>.pdf")
def report_pdf(year):
    pid = current_pid()
    return send_file(reports.pdf_report(pid, year, report_title(pid)), mimetype="application/pdf", as_attachment=True,
                     download_name=f"{secure_filename(report_title(pid))}-{year}-report.pdf")

@app.route("/reports/<int:year>/schedule-e.csv")
def schedule_e_csv(year):
    pid = current_pid()
    se = reports.schedule_e(pid, year)
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([f"Schedule E summary - {report_title(pid)} - {year}"]); w.writerow(["Line", "Description", "Amount"])
    for r in se["rows"]: w.writerow([r["line"], r["label"], f"{r['amount']:.2f}"])
    w.writerow([20, "Total expenses", f"{se['expenses']:.2f}"]); w.writerow([21, "Income or (loss)", f"{se['net']:.2f}"])
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=schedule-e-{year}.csv"
    return resp


# ---------- MORE: import & backup ----------
@app.route("/more")
def more():
    backups = sorted(os.listdir(store.BACKUP_DIR), reverse=True) if os.path.isdir(store.BACKUP_DIR) else []
    return render_template("more.html", backups=backups[:5])

def guess_category(text):
    """Pick a category from words in the description (you can change it afterwards)."""
    t = text.lower()
    for cat, words in [("Auto & travel", ["flight", "airline", "travel", "gas", "meal", "food", "mileage"]),
                       ("Repairs", ["repair", "plumb", "spring", "heater", "latch", "smoke", "faucet", "paint", "labor", "fix"]),
                       ("Cleaning & maintenance", ["filter", "maintenance", "weed", "pressure", "clean", "soap", "grass", "lawn", "pest"]),
                       ("HOA dues", ["hoa"]), ("Insurance", ["insurance"]), ("Property taxes", ["tax"]),
                       ("Utilities", ["water", "electric", "trash", "sewer"]), ("Supplies", ["office", "supplies"])]:
        if any(w in t for w in words): return cat
    return "Other"

def parse_text_date(text, year):
    """Turn text like '9/1 to 9/6/26' into a real date (uses the first date found)."""
    parts = re.findall(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text)
    if not parts: return None
    yr = next((int(p[2]) for p in parts if p[2]), year)
    yr = yr + 2000 if yr < 100 else yr
    try: return datetime.date(yr, int(parts[0][0]), int(parts[0][1])).isoformat()
    except ValueError: return None

@app.route("/import", methods=["POST"])
def import_excel():
    """Read an .xlsx where each sheet is named after a year (2024, 2025...) into the chosen property."""
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith(".xlsx"):
        flash("Please choose an .xlsx Excel file."); return redirect(url_for("more"))
    pid = request.form.get("property_id", type=int) or default_pid()
    shutil.copy(store.DB_FILE, os.path.join(store.DATA_DIR, "backup-before-import.db"))   # safety copy first
    wb = load_workbook(file, data_only=True)
    done = []
    ins = "INSERT INTO transactions (property_id,kind,date,description,category,amount,notes) VALUES (?,?,?,?,?,?,?)"
    for ws in wb:
        if not ws.title.strip().isdigit(): continue
        year = int(ws.title)
        # Replace this property's typed-in expenses for that year (income, rent and recurring bills are kept)
        db().execute("DELETE FROM transactions WHERE property_id=? AND kind='expense' AND substr(date,1,4)=?"
                     " AND recurring_id IS NULL", (pid, str(year)))
        for r in range(3, ws.max_row + 1):               # expense list: columns A (name), B (date), C (cost)
            name, when, cost = (ws.cell(r, c).value for c in (1, 2, 3))
            if str(name or "").strip().lower() == "total": break
            if not isinstance(cost, (int, float)): continue
            note, date = "", None
            if isinstance(when, (datetime.datetime, datetime.date)): date = when.date().isoformat() if hasattr(when, "date") else when.isoformat()
            elif when: date, note = parse_text_date(str(when), year), f"Original date: {when}"
            if not date: date, note = f"{year}-01-01", (note + "; " if note else "") + "No date in spreadsheet"
            desc = str(name or "").strip() or "(No description - please fix)"
            db().execute(ins, (pid, "expense", date, desc, guess_category(desc), cost, note))
        for m in range(1, 13):                           # monthly table: columns F, G, H and note in I
            row, note = m + 2, str(ws.cell(m + 2, 9).value or "")
            for col, desc, cat in ((6, "Management fee", "Management fees"), (7, "Due to agent", "Commissions"), (8, "HOA", "HOA dues")):
                v = ws.cell(row, col).value
                if isinstance(v, (int, float)) and v:
                    db().execute(ins, (pid, "expense", f"{year}-{m:02d}-01", desc, cat, v, note)); note = ""
        done.append(str(year))
    db().commit()
    flash("Imported years: " + ", ".join(done) if done else "No sheets named like a year (e.g. 2025) were found.")
    return redirect(url_for("money_list"))

@app.route("/backup")
def backup():
    """Download everything (database + receipts) as one .zip file."""
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "expenses.db")
        src, dst = sqlite3.connect(store.DB_FILE), sqlite3.connect(copy)
        with dst: src.backup(dst)
        src.close(); dst.close()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copy, "expenses.db")
            for name in os.listdir(store.RECEIPT_DIR):
                z.write(os.path.join(store.RECEIPT_DIR, name), f"receipts/{name}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"rental-tracker-backup-{today().isoformat()}.zip")


store.init_db()                                          # create / upgrade tables on startup
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=bool(os.environ.get("DEBUG")))
