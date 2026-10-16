"""
Rental Property Expense Tracker
================================
A small web app that replaces your Excel sheet. Everything lives in this one
file: the database, the web pages, the Excel import and the PDF export.
Data is saved in a single file: data/expenses.db  (copy it = backup).
"""
import os, re, shutil, sqlite3, io, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, g
from openpyxl import load_workbook                       # reads your .xlsx file
from reportlab.lib.pagesizes import letter               # PDF page size (US Letter)
from reportlab.lib import colors                         # colors for the PDF
from reportlab.lib.styles import getSampleStyleSheet     # ready-made text styles
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer

# ---------- SETTINGS (safe to edit) ----------
PROPERTY_NAME = os.environ.get("PROPERTY_NAME", "My Rental Property")  # shown in page title and PDFs; set in docker-compose.yml
DATA_DIR = os.environ.get("DATA_DIR", "data")            # folder where the database lives
DB_FILE = os.path.join(DATA_DIR, "expenses.db")          # the database file itself
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

app = Flask(__name__)                                    # creates the web app
app.secret_key = "local-only"                            # needed for the little pop-up messages

# ---------- DATABASE HELPERS ----------
def db():
    """Open (once per request) a connection to the database."""
    if "db" not in g:
        os.makedirs(DATA_DIR, exist_ok=True)             # make the data folder if missing
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row                   # lets us read columns by name
    return g.db

@app.teardown_appcontext
def close_db(_):
    """Close the connection when the request is finished."""
    conn = g.pop("db", None)
    if conn: conn.close()

def init_db():
    """Create the two tables the first time the app starts."""
    with app.app_context():
        db().executescript("""
        CREATE TABLE IF NOT EXISTS expenses (            -- one row per repair/purchase
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL, date TEXT, description TEXT NOT NULL,
            category TEXT, amount REAL NOT NULL, notes TEXT);
        CREATE TABLE IF NOT EXISTS monthly (             -- one row per month: recurring bills
            year INTEGER, month INTEGER, mgmt_fee REAL DEFAULT 0,
            agent REAL DEFAULT 0, hoa REAL DEFAULT 0, note TEXT,
            PRIMARY KEY (year, month));
        """)
        db().commit()

def num(text):
    """Turn typed text like '1,200.50' or '$40' into a number (blank = 0)."""
    try: return round(float(str(text).replace("$", "").replace(",", "").strip() or 0), 2)
    except ValueError: return 0.0

@app.template_filter("money")
def money(v):
    """Show a number as $1,234.56 (used inside the HTML pages)."""
    return "${:,.2f}".format(v or 0)

def all_years():
    """List of years to show as tabs: every year with data, plus this year."""
    rows = db().execute("SELECT year FROM expenses UNION SELECT year FROM monthly").fetchall()
    return sorted({r[0] for r in rows} | {datetime.date.today().year})

def summary(year):
    """Add up everything for one year. Returns a dict used by the page and the PDF."""
    exp = db().execute("SELECT * FROM expenses WHERE year=? ORDER BY date IS NULL, date, id", (year,)).fetchall()
    stored = {r["month"]: r for r in db().execute("SELECT * FROM monthly WHERE year=?", (year,))}
    months = []                                          # always 12 rows, even if nothing saved yet
    for i, name in enumerate(MONTHS, 1):
        r = stored.get(i)
        months.append({"n": i, "name": name, "mgmt": r["mgmt_fee"] if r else 0,
                       "agent": r["agent"] if r else 0, "hoa": r["hoa"] if r else 0,
                       "note": (r["note"] or "") if r else ""})
    s = {"expenses": exp, "months": months,
         "exp_total": sum(e["amount"] for e in exp),
         "mgmt_total": sum(m["mgmt"] for m in months),
         "agent_total": sum(m["agent"] for m in months),
         "hoa_total": sum(m["hoa"] for m in months)}
    s["grand"] = s["exp_total"] + s["mgmt_total"] + s["agent_total"] + s["hoa_total"]
    return s

# ---------- WEB PAGES ----------
@app.route("/")
def home():
    """Going to the main address jumps to the newest year."""
    return redirect(url_for("year_page", year=all_years()[-1]))

@app.route("/year/<int:year>")
def year_page(year):
    """The main screen for one year. ?edit=5 loads expense #5 into the form."""
    edit_id = request.args.get("edit", type=int)
    editing = db().execute("SELECT * FROM expenses WHERE id=?", (edit_id,)).fetchone() if edit_id else None
    cats = [r[0] for r in db().execute("SELECT DISTINCT category FROM expenses WHERE category<>'' ORDER BY 1")]
    return render_template("index.html", year=year, years=all_years(), s=summary(year),
                           editing=editing, cats=cats, prop=PROPERTY_NAME)

@app.route("/year/<int:year>/expense", methods=["POST"])
def save_expense(year):
    """Add a new expense, or update one if the form has an id."""
    f = request.form
    date = f.get("date") or None                         # blank date is allowed
    if date: year = int(date[:4])                        # the date decides which year it belongs to
    vals = (year, date, f["description"].strip(), f.get("category", "").strip(), num(f["amount"]), f.get("notes", "").strip())
    if f.get("id"):                                      # editing an existing row
        db().execute("UPDATE expenses SET year=?,date=?,description=?,category=?,amount=?,notes=? WHERE id=?", vals + (f["id"],))
        flash("Expense updated.")
    else:                                                # adding a brand new row
        db().execute("INSERT INTO expenses (year,date,description,category,amount,notes) VALUES (?,?,?,?,?,?)", vals)
        flash("Expense added.")
    db().commit()
    return redirect(url_for("year_page", year=year))

@app.route("/expense/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    """Delete one expense."""
    row = db().execute("SELECT year FROM expenses WHERE id=?", (id,)).fetchone()
    db().execute("DELETE FROM expenses WHERE id=?", (id,)); db().commit()
    flash("Expense deleted.")
    return redirect(url_for("year_page", year=row["year"] if row else all_years()[-1]))

@app.route("/year/<int:year>/monthly", methods=["POST"])
def save_monthly(year):
    """Save the whole 12-month table (fees, agent, HOA, notes) in one go."""
    for i in range(1, 13):
        db().execute("INSERT OR REPLACE INTO monthly (year,month,mgmt_fee,agent,hoa,note) VALUES (?,?,?,?,?,?)",
                     (year, i, num(request.form.get(f"mgmt{i}")), num(request.form.get(f"agent{i}")),
                      num(request.form.get(f"hoa{i}")), request.form.get(f"note{i}", "").strip()))
    db().commit()
    flash("Monthly charges saved.")
    return redirect(url_for("year_page", year=year) + "#monthly")

# ---------- EXCEL IMPORT ----------
def guess_category(text):
    """Pick a category from words in the description (you can change it afterwards)."""
    t = text.lower()
    for cat, words in [("Travel", ["flight", "airline", "travel", "gas", "meal", "food"]),
                       ("Repairs", ["repair", "plumb", "spring", "heater", "latch", "smoke", "faucet", "paint", "labor"]),
                       ("Maintenance", ["filter", "maintenance", "weed", "pressure", "clean", "soap", "grass"]),
                       ("Fees", ["lease", "hoa", "late", "fee", "estimate"]),
                       ("Office", ["office"])]:
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
    """Read an uploaded .xlsx where each sheet is named after a year (2024, 2025...)."""
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith(".xlsx"):
        flash("Please choose an .xlsx Excel file."); return redirect(url_for("home"))
    if os.path.exists(DB_FILE):                          # safety: copy the database before changing it
        shutil.copy(DB_FILE, os.path.join(DATA_DIR, "backup-before-import.db"))
    wb = load_workbook(file, data_only=True)             # data_only = read values, not formulas
    done = []
    for ws in wb:
        if not ws.title.strip().isdigit(): continue      # skip sheets not named like a year
        year = int(ws.title)
        db().execute("DELETE FROM expenses WHERE year=?", (year,))   # replace that year's data
        db().execute("DELETE FROM monthly WHERE year=?", (year,))
        for r in range(3, ws.max_row + 1):               # expense list: columns A (name), B (date), C (cost)
            name, when, cost = (ws.cell(r, c).value for c in (1, 2, 3))
            if str(name or "").strip().lower() == "total": break   # stop at the Total row
            if not isinstance(cost, (int, float)): continue        # skip empty rows
            note, date = "", None
            if isinstance(when, (datetime.datetime, datetime.date)): date = when.date().isoformat() if hasattr(when, "date") else when.isoformat()
            elif when: date, note = parse_text_date(str(when), year), f"Original date: {when}"
            desc = str(name or "").strip() or "(No description - please fix)"
            db().execute("INSERT INTO expenses (year,date,description,category,amount,notes) VALUES (?,?,?,?,?,?)",
                         (year, date, desc, guess_category(str(name or "")) if name else "Other", cost, note))
        for m in range(1, 13):                           # monthly table: columns F, G, H and note in I
            row = m + 2
            vals = [ws.cell(row, c).value for c in (6, 7, 8)]
            db().execute("INSERT INTO monthly (year,month,mgmt_fee,agent,hoa,note) VALUES (?,?,?,?,?,?)",
                         (year, m, *[v if isinstance(v, (int, float)) else 0 for v in vals], ws.cell(row, 9).value or ""))
        done.append(str(year))
    db().commit()
    flash("Imported years: " + ", ".join(done) if done else "No sheets named like a year (e.g. 2025) were found.")
    return redirect(url_for("home"))

# ---------- PDF EXPORT ----------
@app.route("/year/<int:year>/pdf")
def export_pdf(year):
    """Build a printable PDF of one year and send it to the browser."""
    s, st = summary(year), getSampleStyleSheet()
    buf = io.BytesIO()                                   # build the PDF in memory
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    def table(rows, widths, right_cols, bold_last=False):
        """Make a styled table: header row shaded, money columns right-aligned."""
        t = Table(rows, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e6b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f7")])]
        style += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right_cols]
        if bold_last: style += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]
        t.setStyle(TableStyle(style)); return t
    out = [Paragraph(f"{PROPERTY_NAME} - {year} Expenses", st["Title"]),
           Paragraph(f"<b>Total for the year: {money(s['grand'])}</b>", st["Heading3"]), Spacer(1, 6),
           Paragraph("Expenses", st["Heading2"])]
    rows = [["Date", "Description", "Category", "Cost"]] + [[e["date"] or "", Paragraph(e["description"], st["BodyText"]), e["category"] or "", money(e["amount"])] for e in s["expenses"]]
    rows.append(["", "Total expenses", "", money(s["exp_total"])])
    out += [table(rows, [70, 270, 100, 80], [3], True), Spacer(1, 14), Paragraph("Monthly charges", st["Heading2"])]
    rows = [["Month", "Mgmt fee", "Due to agent", "HOA", "Note"]] + [[m["name"], money(m["mgmt"]), money(m["agent"]), money(m["hoa"]), m["note"]] for m in s["months"]]
    rows.append(["Total", money(s["mgmt_total"]), money(s["agent_total"]), money(s["hoa_total"]), ""])
    out.append(table(rows, [80, 80, 90, 80, 190], [1, 2, 3], True))
    doc.build(out); buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=f"Expenses-{year}.pdf")

@app.route("/backup")
def backup():
    """Download a copy of the whole database file."""
    return send_file(DB_FILE, as_attachment=True, download_name="expenses-backup.db")

init_db()                                                # make sure tables exist on startup
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)                   # serve the app on port 8080
