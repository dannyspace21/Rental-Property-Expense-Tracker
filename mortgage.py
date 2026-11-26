"""
mortgage.py - read Form 1098 PDFs
=================================
Pulls the numbers out of IRS Form 1098 (Mortgage Interest Statement): the official
IRS form (filled in electronically or printed) or a lender's own year-end statement.
Boxes read: 1 interest, 2 outstanding principal, 3 origination date, 4 refund,
5 mortgage insurance, 6 points, 10 other (often property taxes), 11 acquisition date,
plus property taxes / insurance paid from escrow, the tax year and the account number.

Nothing here is saved; it only reads. The results go to a review screen where you
can fix anything before it is recorded. Works only with PDFs that contain real text
or form fields (downloaded files), not photos or scans.
"""
import re, io, datetime

MONEY = r"\(?-?\$?\s?\d{1,3}(?:,\d{3})*\.\d{2}\)?|\(?-?\$?\s?\d+\.\d{2}\)?"


def pdf_text(data):
    """All text in a PDF (bytes). Returns '' for scans/photos with no text layer."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try: reader.decrypt("")
            except Exception: return ""
        parts = []
        for page in reader.pages[:12]:                   # statements are short; cap for safety
            try: parts.append(page.extract_text(extraction_mode="layout") or "")   # keeps table rows on one line
            except Exception:
                try: parts.append(page.extract_text() or "")
                except Exception: pass
        return normalize("\n".join(parts))
    except Exception:
        return ""

def normalize(text):
    for a, b in ((" ", " "), ("–", "-"), ("—", "-"), ("−", "-"), ("\t", " ")):
        text = text.replace(a, b)
    return text

def to_num(s):
    """'$1,234.56' -> 1234.56 ; '(12.00)' -> -12.0"""
    if s is None: return None
    neg = s.strip().startswith("(") or "-" in s
    v = float(re.sub(r"[^\d.]", "", s) or 0)
    return round(-v if neg else v, 2)

def parse_date(s):
    s = s.strip().replace(".", "")
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try: return datetime.datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

# ---------- FORM 1098 ----------
BOXES = [(1, r"mortgage interest received"), (2, r"outstanding mortgage\s*principal"), (3, r"mortgage origination date"),
         (4, r"refund of overpaid"), (5, r"mortgage insurance\s*premiums"), (6, r"points paid"),
         (7, r"(?:if )?(?:the )?address (?:or description )?of (?:the )?property (?:securing|is the same)"),
         (8, r"address or description of property"), (9, r"number of properties"), (10, r"\b10\s*other\b|\bother\b(?=\s*[\$\d(]|\s*\n)"),
         (11, r"mortgage acquisition date")]

def box_amount(text, n):
    """Dollar amount printed in a numbered 1098 box (looks between its label and the next label)."""
    label = dict(BOXES)[n]
    m = re.search(label, text, re.I)
    if not m: return None
    starts = [x.start() for _, pat in BOXES for x in re.finditer(pat, text, re.I) if x.start() > m.end()]
    end = min(starts + [m.end() + 200])
    window = text[m.end():end]
    window = re.sub(r"\(?\b(?:box|line)?\s*\d{1,2}\)?\s*$", "", window)
    v = re.search(MONEY, window)
    return to_num(v.group()) if v else None

def parse_1098(text):
    """Pull the boxes out of a Form 1098 (plus property tax / insurance paid from escrow if listed)."""
    out = {}
    for n, key in ((1, "interest"), (2, "principal"), (4, "refund"), (5, "mip"), (6, "points"), (10, "other")):
        out[key] = box_amount(text, n)
    # Property taxes / insurance paid from escrow: often in box 10 ("Other") or on a supplemental page
    tax = re.search(r"(?:real estate|property|county|city|town|school)\s+tax(?:es)?(?:\s+(?:paid|disbursed|disbursements?))?"
                    r"(?:\s+from\s+escrow)?[^\d$\n]{0,40}(" + MONEY + ")", text, re.I)
    ins = re.search(r"(?<!mortgage )(?:hazard|homeowners?'?|home|flood|property|dwelling)\s+insurance(?:\s+(?:paid|disbursed|disbursements?))?"
                    r"(?:\s+from\s+escrow)?[^\d$\n]{0,40}(" + MONEY + ")", text, re.I)
    out["taxes"] = to_num(tax.group(1)) if tax else None
    out["insurance"] = to_num(ins.group(1)) if ins else None
    if out["taxes"] is None and out["other"] and re.search(r"tax", text[text.lower().find("other"):][:200] if "other" in text.lower() else "", re.I):
        out["taxes"] = out["other"]
    years = re.findall(r"(?:calendar year|tax year|for year|year)\s*(20\d{2})|(20\d{2})\s*form\s*1098|form\s*1098\s*\(?(20\d{2})", text, re.I)
    years = [int(y) for t in years for y in t if y]
    out["year"] = years[0] if years else None
    out["found"] = out["interest"] is not None
    return out


# ---------- FORM 1098: read by position (works with filled-in IRS forms and lender statements) ----------
# Real 1098s differ a lot: the official IRS form filled in electronically keeps the numbers in form
# fields (not in the page text), boxes 2+3 and 4+5 sit side by side with the value *below* each label,
# and many lenders print their own "year-end statement" with wording like "Interest Paid".
# So instead of reading the text top to bottom, we note where every label and every value sits on the
# page and match each label with the closest value to its right or just below it.

AMOUNT = r"\(?-?\$?\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?\)?|\(?-?\$?\s?\d+\.\d{2}\)?"
DATE = r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}"
# (key, label pattern, kind of value). Order matters only for readability.
LABELS_1098 = [
    ("interest", r"mortgage interest received|(?:total |mortgage )?interest (?:paid|received)(?! to date)|\binterest\s+paid\b", "money"),
    ("principal", r"outstanding mortgage|outstanding principal|(?:unpaid |beginning |current )?principal balance|unpaid principal", "money"),
    ("origination", r"origination date|loan (?:open|origination) date|date of (?:the )?loan", "date"),
    ("refund", r"refund of overpaid", "money"),
    ("mip", r"mortgage insurance(?: premiums?)?|\bPMI\b|\bMIP\b", "money"),
    ("points", r"points paid", "money"),
    ("other", r"(?:^|\b10\s+)other\b", "money"),
    ("acquisition", r"acquisition date", "date"),
    ("taxes", r"(?:real estate|property|county|city|town|school)\s+tax(?:es)?(?:\s+(?:paid|disbursed|disbursements?))?", "money"),
    ("insurance", r"(?:hazard|homeowners?'?|home|flood|dwelling)\s+insurance(?:\s+(?:paid|disbursed|disbursements?))?", "money"),
    ("year", r"calendar year|tax year|for (?:the )?year", "year"),
    ("account", r"account (?:number|no\.?|#)|loan (?:number|no\.?|#)", "account"),
]
VALUE_RE = {"money": AMOUNT, "date": DATE, "year": r"\b20\d{2}\b", "account": r"[\dXx*#-]{4,}"}


def pdf_pieces(data, max_pages=6):
    """Every bit of text on the pages plus every filled-in form field, with where it sits.
    Returns a list of dicts: page, x, y (PDF points, y grows upward), size, text."""
    import logging
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)          # fonts warnings are harmless here
    pieces = []
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted: reader.decrypt("")
    except Exception:
        return pieces
    for pno, page in enumerate(reader.pages[:max_pages]):
        def visit(text, cm, tm, font, size, pno=pno):
            t = normalize(text or "").strip()
            if not t: return
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            scale = abs(tm[0] * cm[0]) or 1
            for line in t.split("\n"):
                if line.strip():
                    pieces.append({"page": pno, "x": x, "y": y, "size": (size or 9) * scale, "text": line.strip()})
                y -= (size or 9) * scale * 1.2
        try: page.extract_text(visitor_text=visit)
        except Exception: pass
        for annot in page.get("/Annots") or []:                  # values typed into the form's fields
            try:
                a = annot.get_object()
                if a.get("/Subtype") != "/Widget": continue
                value = a.get("/V") if "/V" in a else a.get("/Parent", {}).get_object().get("/V") if "/Parent" in a else None
                if value is None or str(value).startswith("/"): continue   # empty, or a checkbox state
                x0, y0, x1, y1 = (float(v) for v in a["/Rect"])
                for i, line in enumerate(str(value).splitlines()):
                    if line.strip():
                        pieces.append({"page": pno, "x": min(x0, x1) + 2, "y": max(y0, y1) - 9 - 11 * i,
                                       "size": 9, "text": normalize(line).strip()})
            except Exception:
                continue
    return pieces


def match_labels(pieces, labels=LABELS_1098):
    """Pair each label with the nearest value to its right or just below it. Each value is used once."""
    found_labels, options = [], []
    for p in pieces:
        for key, pat, kind in labels:
            m = re.search(pat, p["text"], re.I)
            if m: found_labels.append((key, kind, p, m.end()))
    for key, kind, lab, end in found_labels:
        rx = re.compile(VALUE_RE[kind], re.I)
        # a value printed in the same piece, right after the label ("Interest Paid  $13,512.66")
        same = rx.search(lab["text"][end:])
        if same:
            options.append((0.0, key, id(lab), same.group(), lab))
        for v in pieces:
            if v is lab or v["page"] != lab["page"]: continue
            hit = rx.search(v["text"])
            if not hit: continue
            dy, dx = lab["y"] - v["y"], v["x"] - lab["x"]
            line = max(3.0, lab["size"] * 0.6)
            if abs(dy) <= line and 0 < dx <= 560:                  # same line, to the right (any distance across the page)
                score = dx * 0.5
            elif line < dy <= 48 and -25 <= dx <= 160:            # just below, in the same column
                score = dy * 2 + abs(dx) * 0.8
            else:
                continue
            options.append((score, key, id(v), hit.group(), v))
    result, used_keys, used_vals = {}, set(), set()
    for score, key, vid, value, piece in sorted(options, key=lambda o: o[0]):
        if key in used_keys or (vid, value) in used_vals: continue
        result[key] = value
        used_keys.add(key); used_vals.add((vid, value))
    return result


def parse_1098_pdf(data):
    """Read a Form 1098 (official IRS form, filled in or printed, or a lender's year-end statement)."""
    raw = match_labels(pdf_pieces(data))
    out = {}
    for key in ("interest", "principal", "refund", "mip", "points", "other", "taxes", "insurance"):
        out[key] = to_num(raw[key]) if key in raw else None
    for key in ("origination", "acquisition"):
        d = parse_date(raw[key]) if key in raw else None
        out[key] = d.isoformat() if d else None
    out["year"] = int(raw["year"]) if "year" in raw else None
    digits = re.sub(r"\D", "", raw.get("account", ""))
    out["account_last4"] = digits[-4:] if len(digits) >= 4 else None
    # Fill gaps from the plain-text reader (handles some layouts the position reader can't see)
    text = pdf_text(data)
    if text.strip():
        backup = parse_1098(text)
        for key in ("interest", "principal", "refund", "mip", "points", "other", "taxes", "insurance", "year"):
            if out.get(key) is None and backup.get(key) is not None:
                out[key] = backup[key]
        if out["year"] is None:
            years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text) if 2000 < int(y) <= datetime.date.today().year]
            out["year"] = max(set(years), key=years.count) if years else None
    if out["taxes"] is None and out["other"] and re.search(r"tax", " ".join(p["text"] for p in pdf_pieces(data)
                                                                       if re.search(r"other", p["text"], re.I)), re.I):
        out["taxes"] = out["other"]
    out["found"] = out["interest"] is not None
    out["has_text"] = bool(text.strip()) or bool(raw)
    return out
