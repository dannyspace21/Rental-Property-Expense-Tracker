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
    for a, b in ((" ", " "), ("–", "-"), ("—", "-"), ("−", "-"), ("\t", " "), ("\u2019", "'"), ("\u2018", "'")):
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
# Real 1098s differ a lot:
#  * the official IRS form filled in electronically keeps the numbers in form fields, not in the page text;
#  * lenders' print systems often draw text one word or even one letter at a time;
#  * boxes sit side by side, with the value below the label or in the bottom-right corner of the box;
#  * some pages are rotated; many add an instructions page that repeats the box wording.
# So we (1) collect every fragment of text and every form-field value with its position, (2) stitch the
# fragments back into lines, (3) find each box's label, and (4) give it the closest value to its right or
# below it, never across another box's label, using each value only once.

AMOUNT = r"\(?-?\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?|\(?-?\d{1,3}(?:,\d{3})+(?:\.\d{2})?\)?|\(?-?\d+\.\d{2}\)?"
DATE = r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}-\d{1,2}-\d{4}\b|\b[A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}\b"

def squash(text):
    """Lowercase letters and digits only, so 'M ortgage interestreceived' == 'Mortgage interest received'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())

# (key, label keywords compared with squash(), kind of value)
LABELS_1098 = [
    ("lender", ["lendersname", "recipientslendersname"], "name"),
    ("interest", ["mortgageinterestreceived", "mortgageinterestpaid", "interestpaid", "interestreceived", "totalinterest"], "money"),
    ("principal", ["outstandingmortgage", "outstandingprincipal", "principalbalance", "unpaidprincipal"], "money"),
    ("origination", ["originationdate", "loanopendate", "loanoriginationdate", "dateofloan"], "date"),
    ("refund", ["refundofoverpaid"], "money"),
    ("mip", ["mortgageinsurance"], "money"),
    ("points", ["pointspaid"], "money"),
    ("address_same", ["ifaddressofpropertysecuring", "ifaddressofthepropertysecuring", "ifthe addressofproperty"], "check"),
    ("property_address", ["addressordescriptionofproperty", "addressordescriptionofthe property", "propertyaddress"], "text"),
    ("properties", ["numberofproperties"], "count"),
    ("other", ["^10other", "^other$"], "money"),
    ("acquisition", ["acquisitiondate"], "date"),
    ("year", ["calendaryear", "taxyear"], "year"),
    ("account", ["accountnumber", "loannumber", "accountno", "loanno"], "account"),
]
EXTRA_LABELS = [   # escrow information: may share a value with box 10, so matched separately
    ("taxes", ["realestatetax", "propertytax", "countytax", "citytax", "towntax", "schooltax"], "money"),
    ("insurance", ["hazardinsurance", "homeownersinsurance", "homeinsurance", "floodinsurance", "dwellinginsurance"], "money"),
]
OTHER_WORDS = ["payer", "borrower", "recipient", "tin", "streetaddress", "cityortown", "omb", "form1098", "postalcode",
               "province", "telephone", "instructions", "mortgageinterest", "copyb", "department", "deductible",
               "caution", "amountshown", "limitsbased", "securedproperty"]
VALUE_RE = {"money": AMOUNT, "date": DATE, "year": r"(?<!\d)20\d{2}(?!\d)", "account": r"[\dXx*#-]*\d{4}\b",
            "count": r"^\s*\d{1,2}\s*$", "check": r"^\s*(?:X|x|✓|✔|Yes|On)\s*$",
            "name": r"^[A-Za-z][A-Za-z0-9&.,'\- ]{2,}$", "text": r"[A-Za-z0-9]"}
INSTRUCTIONS = re.compile(r"\bbox(?:es)?\s*\d{1,2}\s*[.:]\s*[A-Za-z]|\bsee (?:the )?instructions for\b|caution:", re.I)


def _has(keywords, text):
    sq = squash(text)
    for k in keywords:
        k = k.replace(" ", "")
        if k.startswith("^") and k.endswith("$"):
            if sq == k[1:-1]: return True
        elif k.startswith("^"):
            if sq.startswith(k[1:]): return True
        elif k in sq:
            return True
    return False

ALL_KEYWORDS = [k for _, ks, _ in LABELS_1098 + EXTRA_LABELS for k in ks] + OTHER_WORDS
def is_label(text):
    return _has(ALL_KEYWORDS, text)


_STANDARD = {"helvetica": "Helvetica", "arial": "Helvetica", "times": "Times-Roman", "courier": "Courier"}
def _text_width(text, font, size):
    """Width of a piece of text in points: the font's own widths if stored in the PDF, otherwise the
    standard metrics for Helvetica / Times / Courier (close enough for other fonts too)."""
    try:
        font = font.get_object() if hasattr(font, "get_object") else font
        widths, first = font.get("/Widths"), int(font.get("/FirstChar", 0))
        if widths:
            widths = [float(w) for w in widths]
            return sum(widths[ord(ch) - first] if 0 <= ord(ch) - first < len(widths) else 500 for ch in text) / 1000 * size
        base = str(font.get("/BaseFont", "/Helvetica")).lstrip("/").split("+")[-1]
    except Exception:
        base = "Helvetica"
    from reportlab.pdfbase.pdfmetrics import stringWidth
    family = next((v for k, v in _STANDARD.items() if k in base.lower()), "Helvetica")
    if family != "Courier" and "bold" in base.lower(): family = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold"}[family]
    try: return stringWidth(text, family, size)
    except Exception: return len(text) * size * 0.52


def pdf_pieces(data, max_pages=6):
    """Every fragment of text plus every filled-in form field, with its position, stitched into lines.
    Positions are turned so text always reads left to right (handles rotated pages)."""
    import logging, math
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)          # font warnings are harmless here
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted: reader.decrypt("")
    except Exception:
        return []
    lines = []
    for pno, page in enumerate(reader.pages[:max_pages]):
        frags = []
        def visit(text, cm, tm, font, size, frags=frags):
            t = normalize(text or "")
            if not t.strip(): return
            a, b = tm[0] * cm[0] + tm[1] * cm[2], tm[0] * cm[1] + tm[1] * cm[3]
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            scale = math.hypot(a, b) or 1
            fs = (size or 9) * scale
            angle = round(math.degrees(math.atan2(b, a)) / 90) % 4      # 0, 1 (90°), 2, 3
            for i, part in enumerate(t.split("\n")):
                if part.strip():
                    frags.append({"x": x, "y": y - i * fs * 1.15, "size": fs, "angle": angle,
                                  "w": _text_width(part, font, size or 9) * scale, "text": part})
        try: page.extract_text(visitor_text=visit)
        except Exception: pass
        for annot in page.get("/Annots") or []:                  # values typed into the form's fields
            try:
                w = annot.get_object()
                if w.get("/Subtype") != "/Widget": continue
                parent = w.get("/Parent").get_object() if "/Parent" in w else {}
                value = w.get("/V", parent.get("/V"))
                if value is None: continue
                value = str(value)
                if value.startswith("/"):                         # a checkbox: count it only when ticked
                    if value in ("/Off", "/0", "/No"): continue
                    value = "X"
                x0, y0, x1, y1 = (float(v) for v in w["/Rect"])
                for i, part in enumerate(value.splitlines()):
                    if part.strip():
                        frags.append({"x": min(x0, x1) + 2, "y": max(y0, y1) - 9 - 11 * i, "size": 9, "angle": 0,
                                      "w": len(part) * 9 * 0.55, "text": normalize(part)})
            except Exception:
                continue
        if not frags: continue
        # Turn rotated text so it reads left to right: rotate positions by the most common text angle
        angle = max(set(f["angle"] for f in frags), key=[f["angle"] for f in frags].count)
        for f in frags:
            x, y = f["x"], f["y"]
            f["x"], f["y"] = {0: (x, y), 1: (y, -x), 2: (-x, -y), 3: (-y, x)}[angle]
        # Stitch fragments on the same line that sit next to each other into one piece of text
        frags.sort(key=lambda f: (-round(f["y"], 0), f["x"]))
        rows = []
        for f in frags:
            if rows and abs(rows[-1][0]["y"] - f["y"]) <= max(1.5, 0.35 * min(rows[-1][0]["size"], f["size"])):
                rows[-1].append(f)
            else:
                rows.append([f])
        for row in rows:
            row.sort(key=lambda f: f["x"])
            cur = None
            for f in row:
                gap = f["x"] - (cur["x"] + cur["w"]) if cur else None
                if cur and -0.25 * f["size"] <= gap <= 1.1 * max(cur["size"], f["size"]):   # overlapping = separate boxes
                    joiner = " " if gap > 0.18 * f["size"] and not cur["text"].endswith(" ") and not f["text"].startswith(" ") else ""
                    cur["text"] += joiner + f["text"]
                    cur["w"] = f["x"] + f["w"] - cur["x"]
                else:
                    cur = dict(f, page=pno); lines.append(cur)
        for l in lines:
            if l.get("page") == pno: l["text"] = re.sub(r"\s+", " ", l["text"]).strip()
    return [l for l in lines if l["text"]]


def _between_label(lab, v, labels):
    """True if some other label sits between a label and a candidate value (then the value isn't ours)."""
    for o in labels:
        if o is lab or o is v or o["page"] != lab["page"]: continue
        if abs(o["x"] - lab["x"]) <= 3 and 0 < lab["y"] - o["y"] <= 2.2 * lab["size"]:
            continue                                              # the label's own second line
        if v["y"] + 1 < o["y"] < lab["y"] - 1 and min(lab["x"], v["x"]) - 15 <= o["x"] <= v["x"] + 5:
            return True                                           # a label between them, going down
        if abs(o["y"] - lab["y"]) <= 2 and abs(v["y"] - lab["y"]) <= 2 and lab["x"] < o["x"] < v["x"]:
            return True                                           # a label between them on the same line
    return False


def _box_number(p, pieces):
    """A lone number printed right before a label (like the '10' of '10 Other') is a box number, not a value."""
    if not re.fullmatch(r"\s*\d{1,2}\s*", p["text"]): return False
    return any(o is not p and o["page"] == p["page"] and abs(o["y"] - p["y"]) <= 2 and -2 <= o["x"] - p["x"] <= 30
               and is_label(o["text"]) for o in pieces)


def match_labels(pieces, labels, blockers=None):
    """Pair each label with the nearest suitable value to its right or below it. Each value is used once.
    'blockers' are the words of labels that a value may not be read across (default: every label)."""
    pieces = [p for p in pieces if not INSTRUCTIONS.search(p["text"])]      # skip "Box 1. Shows the..." text
    all_labels = [p for p in pieces if (_has(blockers, p["text"]) if blockers else is_label(p["text"]))]
    found, options = [], []
    for p in pieces:
        for key, words, kind in labels:
            if _has(words, p["text"]): found.append((key, kind, p))
    for key, kind, lab in found:
        rx = re.compile(VALUE_RE[kind], re.I)
        if kind in ("money", "date", "year", "account"):           # value printed in the same line as the label
            hits = list(rx.finditer(lab["text"]))
            if hits and not (kind == "account" and len(re.sub(r"\D", "", hits[-1].group())) < 4):
                options.append((0.0, key, (id(lab), hits[-1].group()), hits[-1].group()))
        for v in pieces:
            if v is lab or v["page"] != lab["page"]: continue
            if kind in ("name", "text", "count", "check") and is_label(v["text"]): continue
            if kind in ("count", "money") and _box_number(v, pieces): continue
            hit = rx.search(v["text"])
            if not hit: continue
            if kind == "text" and re.fullmatch(AMOUNT, v["text"].strip()): continue
            dy, dx = lab["y"] - v["y"], v["x"] - lab["x"]
            line = max(2.5, 0.45 * lab["size"])
            if abs(dy) <= line and 0 < dx <= 600 and kind not in ("count", "name", "text"):
                score = 5 + dx * 0.3                              # same line, to the right
            elif line < dy <= 60 and -8 <= dx <= (200 if kind == "name" else 320):   # below, in the same box/column
                score = dy * 3 + abs(dx) * 0.3
            else:
                continue
            if _between_label(lab, v, all_labels): continue
            value = v["text"] if kind in ("name", "text") else hit.group()
            options.append((score, key, (id(v), value), value))
    result, used_keys, used_vals = {}, set(), set()
    for score, key, vid, value in sorted(options, key=lambda o: o[0]):
        if key in used_keys or vid in used_vals: continue
        result[key] = value.strip()
        used_keys.add(key); used_vals.add(vid)
    return result


def parse_1098_pdf(data):
    """Read a Form 1098 (official IRS form, filled in or printed, or a lender's year-end statement).
    Returns every box 1-11, the tax year, lender, last 4 digits of the account, and escrow taxes/insurance."""
    pieces = pdf_pieces(data)
    box_words = [k for _, ks, _ in LABELS_1098 for k in ks] + OTHER_WORDS     # box 10's "REAL ESTATE TAXES" isn't a box label
    raw = match_labels(pieces, LABELS_1098, box_words)
    raw.update(match_labels(pieces, EXTRA_LABELS))
    out = {}
    for key in ("interest", "principal", "refund", "mip", "points", "other", "taxes", "insurance"):
        out[key] = to_num(raw[key]) if key in raw else None
    for key in ("origination", "acquisition"):
        d = parse_date(raw[key].replace("-", "/")) if key in raw and not re.match(r"\d{4}-", raw[key]) else None
        if key in raw and re.match(r"\d{4}-\d{2}-\d{2}", raw[key]): d = datetime.date.fromisoformat(raw[key])
        out[key] = d.isoformat() if d else None
    out["year"] = int(raw["year"]) if "year" in raw else None
    out["properties"] = int(raw["properties"]) if "properties" in raw else None
    out["address_same"] = True if "address_same" in raw else None
    out["property_address"] = raw.get("property_address")
    out["lender"] = raw.get("lender")
    digits = re.sub(r"\D", "", raw.get("account", ""))
    out["account_last4"] = digits[-4:] if len(digits) >= 4 else None
    # What box 10 says, e.g. "REAL ESTATE TAXES"
    other_label = next((p for p in pieces if _has(["^10other", "^other$"], p["text"])), None)
    out["other_text"] = None
    if other_label:
        below = [p for p in pieces if p["page"] == other_label["page"] and 0 < other_label["y"] - p["y"] <= 25
                 and -10 <= p["x"] - other_label["x"] <= 120 and re.search(r"[A-Za-z]{3}", p["text"])
                 and not _has(OTHER_WORDS, p["text"])]
        if below: out["other_text"] = re.sub(AMOUNT, "", min(below, key=lambda p: other_label["y"] - p["y"])["text"]).strip() or None
    if out["taxes"] is None and out["other"] and re.search(r"tax", (out["other_text"] or ""), re.I):
        out["taxes"] = out["other"]
    # Fill gaps from the plain-text reader (handles some layouts the position reader can't see)
    text = pdf_text(data)
    if text.strip():
        backup = parse_1098(text)
        for key in ("interest", "principal", "refund", "mip", "points", "taxes", "insurance", "year"):
            if out.get(key) is None and backup.get(key) is not None:
                out[key] = backup[key]
        if out["year"] is None:
            years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text) if 2000 < int(y) <= datetime.date.today().year]
            out["year"] = max(set(years), key=years.count) if years else None
    out["found"] = out["interest"] is not None
    out["has_text"] = bool(text.strip()) or bool(pieces)
    return out
