"""
reports.py - all the math
==========================
Totals, the rent roll, depreciation, the Schedule E tax summary, investment
metrics, charts and the PDF export. Nothing in here changes data.
pid = a property id, or None for "all properties".
"""
import io, datetime, calendar
from collections import defaultdict
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from store import (db, today, MONTHS, CATEGORY_LINE, SCHEDULE_E_LINES, NON_OPERATING, add_months)


def money(v):
    """Show a number as $1,234.56 (negative as -$1,234.56)."""
    v = v or 0
    return ("-" if v < 0 else "") + "${:,.2f}".format(abs(v))

def prop_filter(pid, col="property_id"):
    """SQL snippet + args that limit a query to one property (or none = all)."""
    return (f" AND {col}=?", [pid]) if pid else ("", [])

def years_with_data(pid):
    """Years to offer as tabs: every year with data, plus this year."""
    where, args = prop_filter(pid)
    rows = db().execute(f"SELECT DISTINCT substr(date,1,4) FROM transactions WHERE 1=1{where}", args).fetchall()
    return sorted({int(r[0]) for r in rows if r[0] and r[0].isdigit()} | {today().year})


# ---------- TRANSACTIONS ----------
def find_transactions(pid=None, year=None, kind=None, category=None, vendor_id=None, q=None,
                      date_from=None, date_to=None, min_amt=None, max_amt=None, lease_id=None, limit=None):
    """Search transactions. Every argument is optional."""
    sql = ["SELECT t.*, v.name AS vendor, p.name AS property, l.tenant AS tenant,"
           " (SELECT COUNT(*) FROM attachments a WHERE a.transaction_id=t.id) AS receipts"
           " FROM transactions t JOIN properties p ON p.id=t.property_id"
           " LEFT JOIN vendors v ON v.id=t.vendor_id LEFT JOIN leases l ON l.id=t.lease_id WHERE 1=1"]
    args = []
    def add(cond, *vals): sql.append(" AND " + cond); args.extend(vals)
    if pid: add("t.property_id=?", pid)
    if year: add("substr(t.date,1,4)=?", str(year))
    if kind: add("t.kind=?", kind)
    if category: add("t.category=?", category)
    if vendor_id: add("t.vendor_id=?", vendor_id)
    if lease_id: add("t.lease_id=?", lease_id)
    if date_from: add("t.date>=?", date_from)
    if date_to: add("t.date<=?", date_to)
    if min_amt not in (None, ""): add("t.amount>=?", float(min_amt))
    if max_amt not in (None, ""): add("t.amount<=?", float(max_amt))
    if q:
        like = f"%{q}%"
        add("(t.description LIKE ? OR t.notes LIKE ? OR v.name LIKE ? OR t.category LIKE ?)", like, like, like, like)
    sql.append(" ORDER BY t.date DESC, t.id DESC")
    if limit: sql.append(f" LIMIT {int(limit)}")
    return db().execute("".join(sql), args).fetchall()

def totals(rows):
    inc = sum(r["amount"] for r in rows if r["kind"] == "income")
    exp = sum(r["amount"] for r in rows if r["kind"] == "expense")
    return {"income": inc, "expense": exp, "net": inc - exp, "count": len(rows)}


# ---------- YEAR SUMMARY & CHARTS ----------
def year_summary(pid, year):
    """Income, expenses and cash flow for one year, by month and by category."""
    rows = find_transactions(pid=pid, year=year)
    by_month = [{"name": MONTHS[i][:3], "income": 0.0, "expense": 0.0} for i in range(12)]
    by_cat = defaultdict(float)
    for r in rows:
        m = int(r["date"][5:7]) - 1
        by_month[m][r["kind"]] += r["amount"]
        if r["kind"] == "expense": by_cat[r["category"]] += r["amount"]
    s = totals(rows)
    s["months"] = by_month
    s["categories"] = sorted(by_cat.items(), key=lambda kv: -kv[1])
    s["rows"] = rows
    return s

def month_chart(months, height=160):
    """Numbers for the side-by-side income/expense bar chart (drawn as SVG in the page)."""
    top = max([max(m["income"], m["expense"]) for m in months] + [1])
    out = []
    for i, m in enumerate(months):
        out.append({"x": i, "name": m["name"], "income": m["income"], "expense": m["expense"],
                    "hi": round(m["income"] / top * height, 1), "he": round(m["expense"] / top * height, 1)})
    return {"bars": out, "height": height, "top": top}


# ---------- RENT ROLL ----------
def lease_active_in(lease, year, month):
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, calendar.monthrange(year, month)[1])
    start = datetime.date.fromisoformat(lease["start_date"])
    end = datetime.date.fromisoformat(lease["end_date"]) if lease["end_date"] else None
    return start <= last and (end is None or end >= first)

def rent_cell(lease, year, month, paid):
    """Status of one lease for one month: paid / partial / late / due / upcoming / none."""
    if not lease_active_in(lease, year, month):
        return {"status": "none", "received": paid, "expected": 0, "balance": 0}
    t = today()
    due = datetime.date(year, month, min(lease["due_day"] or 1, calendar.monthrange(year, month)[1]))
    rent = lease["rent"] or 0
    if paid >= rent - 0.005: status = "paid"
    elif t > due + datetime.timedelta(days=lease["grace_days"] or 0): status = "partial" if paid else "late"
    elif t >= datetime.date(year, month, 1): status = "partial" if paid else "due"
    else: status = "upcoming"
    return {"status": status, "received": paid, "expected": rent, "balance": max(0.0, rent - paid),
            "due": due.isoformat()}

def rent_paid_by_month(lease_id, year):
    paid = defaultdict(float)
    for r in db().execute("SELECT date, amount FROM transactions WHERE lease_id=? AND category='Rent' AND kind='income'"
                          " AND substr(date,1,4)=?", (lease_id, str(year))):
        paid[int(r["date"][5:7])] += r["amount"]
    return paid

def leases(pid=None, current_only=False):
    where, args = prop_filter(pid, "l.property_id")
    rows = db().execute(f"SELECT l.*, p.name AS property FROM leases l JOIN properties p ON p.id=l.property_id"
                        f" WHERE 1=1{where} ORDER BY p.name, l.unit, l.start_date DESC", args).fetchall()
    if current_only:
        t = today()
        rows = [l for l in rows if lease_active_in(l, t.year, t.month)]
    return rows

def rent_roll(pid, year):
    """Every lease that touches 'year', with a status cell for each month."""
    out = []
    for l in leases(pid):
        if not any(lease_active_in(l, year, m) for m in range(1, 13)): continue
        paid = rent_paid_by_month(l["id"], year)
        cells = [rent_cell(l, year, m, paid.get(m, 0.0)) for m in range(1, 13)]
        out.append({"lease": l, "cells": cells,
                    "expected": sum(c["expected"] for c in cells), "received": sum(paid.values())})
    return out

def rent_this_month(pid):
    """Current month status for each active lease (used by Home and the Rent page)."""
    t = today()
    out = []
    for l in leases(pid, current_only=True):
        cell = rent_cell(l, t.year, t.month, rent_paid_by_month(l["id"], t.year).get(t.month, 0.0))
        out.append({"lease": l, **cell})
    return out


# ---------- DEPRECIATION ----------
def straight_line(basis, years, in_service, tax_year, mid_month):
    """One year's straight-line depreciation.
    27.5-year property uses the mid-month rule; shorter lives use the half-year rule."""
    if not basis or not in_service or tax_year < in_service.year: return 0.0, 0.0
    annual = basis / years
    def for_year(y):
        if y == in_service.year:
            return annual * ((12 - in_service.month + 0.5) / 12 if mid_month else 0.5)
        return annual
    taken = 0.0
    for y in range(in_service.year, tax_year):
        taken += min(for_year(y), basis - taken)
    this = max(0.0, min(for_year(tax_year), basis - taken))
    return round(this, 2), round(taken + this, 2)

def depreciation(pid, year):
    """Depreciation items for the year: each building plus each capital improvement."""
    items = []
    where, args = prop_filter(pid, "id")
    for p in db().execute(f"SELECT * FROM properties WHERE 1=1{where}", args):
        start = p["in_service_date"] or p["purchase_date"]
        basis = (p["purchase_price"] or 0) + (p["closing_costs"] or 0) - (p["land_value"] or 0)
        if start and basis > 0:
            d = datetime.date.fromisoformat(start)
            amt, total = straight_line(basis, 27.5, d, year, True)
            items.append({"property": p["name"], "what": "Building", "basis": basis, "years": 27.5,
                          "start": start, "amount": amt, "accumulated": total})
    for t in find_transactions(pid=pid, category="Capital improvement", kind="expense"):
        d = datetime.date.fromisoformat(t["date"])
        yrs = t["depr_years"] or 27.5
        amt, total = straight_line(t["amount"], yrs, d, year, yrs == 27.5)
        if total > 0:
            items.append({"property": t["property"], "what": t["description"], "basis": t["amount"], "years": yrs,
                          "start": t["date"], "amount": amt, "accumulated": total, "id": t["id"]})
    return items


# ---------- SCHEDULE E ----------
def schedule_e(pid, year):
    """Totals per Schedule E line for the year. Capital improvements and mortgage
    principal are left out (they are not deductible); depreciation is added instead."""
    lines = defaultdict(float)
    for r in find_transactions(pid=pid, year=year):
        line = CATEGORY_LINE.get(r["category"])
        if line: lines[line] += r["amount"]
    dep = depreciation(pid, year)
    lines[18] += sum(d["amount"] for d in dep)
    rows = [{"line": n, "label": label, "amount": round(lines.get(n, 0.0), 2)} for n, label in SCHEDULE_E_LINES]
    exp = sum(r["amount"] for r in rows if r["line"] != 3)
    return {"rows": rows, "income": lines.get(3, 0.0), "expenses": exp, "net": lines.get(3, 0.0) - exp,
            "depreciation": dep}


# ---------- INVESTMENT METRICS ----------
def metrics(prop, year):
    """Cap rate, cash-on-cash return and friends for one property and year."""
    s = year_summary(prop["id"], year)
    opex = sum(r["amount"] for r in s["rows"] if r["kind"] == "expense" and r["category"] not in NON_OPERATING)
    capex_to_date = sum(r["amount"] for r in find_transactions(pid=prop["id"], category="Capital improvement",
                                                               date_to=f"{year}-12-31"))
    noi = s["income"] - opex
    value = prop["current_value"] or prop["purchase_price"]
    invested = (prop["down_payment"] or 0) + (prop["closing_costs"] or 0) + capex_to_date
    t = today()
    months = 12 if year < t.year else (t.month if year == t.year else 0)
    return {"income": s["income"], "opex": opex, "noi": noi, "cash_flow": s["net"], "value": value,
            "invested": invested, "months": months,
            "cap_rate": (noi * 12 / months / value * 100) if value and months else None,
            "coc": (s["net"] * 12 / months / invested * 100) if invested and prop["down_payment"] and months else None,
            "expense_ratio": (opex / s["income"] * 100) if s["income"] else None,
            "monthly_cash_flow": (s["net"] / months) if months else None}


# ---------- ALERTS FOR THE HOME PAGE ----------
def alerts(pid):
    """Things that need attention: rent, maintenance and leases ending soon."""
    t = today()
    out = []
    for r in rent_this_month(pid):
        if r["status"] in ("late", "partial", "due"):
            out.append({"kind": "rent", "level": "bad" if r["status"] in ("late", "partial") else "warn", **r})
    where, args = prop_filter(pid, "t.property_id")
    soon = (t + datetime.timedelta(days=14)).isoformat()
    for task in db().execute(f"SELECT t.*, p.name AS property FROM tasks t JOIN properties p ON p.id=t.property_id"
                             f" WHERE t.done=0 AND t.next_due<=?{where} ORDER BY t.next_due", [soon] + args):
        out.append({"kind": "task", "level": "bad" if task["next_due"] < t.isoformat() else "warn", "task": task})
    for l in leases(pid, current_only=True):
        if l["end_date"]:
            days = (datetime.date.fromisoformat(l["end_date"]) - t).days
            if 0 <= days <= 60:
                out.append({"kind": "lease", "level": "warn", "lease": l, "days": days})
    return out


# ---------- PDF EXPORT ----------
def pdf_report(pid, year, title):
    """A printable year-end report: summary, Schedule E, income and expense lists."""
    st = getSampleStyleSheet()
    s, se = year_summary(pid, year), schedule_e(pid, year)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40,
                            title=f"{title} - {year}")
    def table(rows, widths, right_cols, bold_last=False):
        t = Table(rows, colWidths=widths, repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e6b")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f7")])]
        style += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right_cols]
        if bold_last: style += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]
        t.setStyle(TableStyle(style)); return t
    P = lambda text: Paragraph(str(text or "").replace("&", "&amp;").replace("<", "&lt;"), st["BodyText"])
    out = [Paragraph(f"{title} - {year} report", st["Title"]),
           table([["Income", "Expenses", "Net cash flow"], [money(s["income"]), money(s["expense"]), money(s["net"])]],
                 [173, 173, 173], [0, 1, 2]), Spacer(1, 14),
           Paragraph("Schedule E summary (estimate - confirm with your tax preparer)", st["Heading2"])]
    rows = [["Line", "Description", "Amount"]] + [[str(r["line"]), r["label"], money(r["amount"])] for r in se["rows"]]
    rows += [["20", "Total expenses", money(se["expenses"])], ["21", "Income or (loss)", money(se["net"])]]
    out += [table(rows, [40, 380, 100], [2], True), Spacer(1, 14)]
    has_multi = pid is None
    for kind, label in (("income", "Income"), ("expense", "Expenses")):
        items = [r for r in reversed(s["rows"]) if r["kind"] == kind]
        out.append(Paragraph(label, st["Heading2"]))
        head = ["Date", "Description", "Category"] + (["Property"] if has_multi else []) + ["Amount"]
        rows = [head] + [[r["date"], P(r["description"] + (f" ({r['vendor']})" if r["vendor"] else "")), P(r["category"])]
                         + ([P(r["property"])] if has_multi else []) + [money(r["amount"])] for r in items]
        rows.append(["", f"Total {label.lower()}", ""] + ([""] if has_multi else []) +
                    [money(sum(r["amount"] for r in items))])
        widths = [62, 220, 110, 70, 70] if has_multi else [62, 290, 100, 80]
        out += [table(rows, widths, [len(head) - 1], True), Spacer(1, 14)]
    doc.build(out); buf.seek(0)
    return buf
