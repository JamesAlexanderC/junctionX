"""Words and numbers: category synonyms, periods, months and money formatting.

Shared by the tools (to normalise arguments the LLM sends) and the offline
coach (to parse questions).
"""

from __future__ import annotations

import re
from datetime import date

from finance import analytics

CATEGORIES = (
    "Housing",
    "Utilities",
    "Groceries",
    "Health",
    "Home & Tech",
    "Travel",
    "Restaurants",
    "Entertainment",
    "Lifestyle",
    "Transportation",
)
TAXI = "Taxi"

# Canonical target -> phrases a customer might use. Targets are category
# names, "Taxi" or basket keys.
SYNONYMS = {
    "Restaurants": (
        "restaurants",
        "restaurant",
        "dining out",
        "dine out",
        "dining",
        "eating out",
        "eat out",
        "takeaway",
        "takeaways",
        "take-away",
        "takeout",
        "take-out",
        "food delivery",
        "delivery food",
        "cafes",
        "cafe",
        "café",
        "cafés",
        "coffee",
        "coffees",
        "bars",
        "bar",
        "pubs",
        "pub",
        "lunches",
        "lunch",
        "fast food",
        "wolt",
        "foodora",
    ),
    "Groceries": (
        "groceries",
        "grocery",
        "food shopping",
        "food",
        "supermarkets",
        "supermarket",
        "k-market",
        "s-market",
        "prisma",
        "lidl",
    ),
    "Entertainment": (
        "entertainment",
        "fun",
        "going out",
        "nights out",
        "night out",
        "cinema",
        "movies",
        "concerts",
        "concert",
        "events",
        "streaming",
        "netflix",
        "spotify",
        "games",
        "gaming",
        "hobbies",
        "leisure",
    ),
    "Lifestyle": (
        "lifestyle",
        "shopping",
        "clothes",
        "clothing",
        "fashion",
        "beauty",
        "gym",
        "sports",
    ),
    "Transportation": (
        "transportation",
        "transport",
        "public transport",
        "commuting",
        "commute",
        "buses",
        "bus",
        "trams",
        "tram",
        "metro",
        "trains",
        "train",
        "fuel",
        "petrol",
        "parking",
        "car",
    ),
    TAXI: (
        "taxis",
        "taxies",
        "taxi",
        "cabs",
        "cab",
        "uber",
        "bolt",
        "ride-hailing",
        "ride hailing",
    ),
    "Housing": ("housing", "rent", "maintenance charge", "vastike"),
    "Utilities": (
        "utilities",
        "utility",
        "electricity",
        "water bill",
        "internet",
        "phone bill",
    ),
    "Health": (
        "health",
        "healthcare",
        "doctors",
        "doctor",
        "dentist",
        "pharmacy",
        "medicine",
    ),
    "Home & Tech": (
        "home & tech",
        "home and tech",
        "tech",
        "electronics",
        "gadgets",
        "furniture",
        "appliances",
        "laptop",
    ),
    "Travel": (
        "travel",
        "travelling",
        "traveling",
        "trips",
        "trip",
        "holidays",
        "holiday",
        "vacation",
        "flights",
        "hotels",
    ),
    "leakage": ("everyday leakage", "leakage", "leaks", "leak", "optional spending"),
    "mandatory_regular": (
        "must-pay bills",
        "must pay bills",
        "fixed costs",
        "bills",
        "regular bills",
    ),
    "mandatory_irregular": ("surprise essentials", "irregular essentials"),
}

# How a target reads in a sentence ("you spent X on ...").
DISPLAY = {
    "Restaurants": "dining out",
    "Groceries": "groceries",
    "Entertainment": "entertainment",
    "Lifestyle": "shopping & lifestyle",
    "Transportation": "transport",
    TAXI: "taxis",
    "Housing": "housing",
    "Utilities": "utilities",
    "Health": "health",
    "Home & Tech": "home & tech",
    "Travel": "travel",
    "leakage": "everyday leakage",
    "mandatory_regular": "must-pay bills",
    "mandatory_irregular": "surprise essentials",
}

_PHRASES = sorted(
    ((p, target) for target, ps in SYNONYMS.items() for p in ps),
    key=lambda pt: -len(pt[0]),
)
_PHRASE_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(p) for p, _ in _PHRASES) + r")(?![\w-])",
    re.IGNORECASE,
)
_PHRASE_TARGET = {p: t for p, t in _PHRASES}


def display(target):
    return DISPLAY.get(target, str(target).lower())


def find_targets(text):
    """All categories/baskets mentioned in ``text``, in order, deduplicated."""
    out = []
    for m in _PHRASE_RE.finditer(text or ""):
        target = _PHRASE_TARGET[m.group(1).lower()]
        if target not in out:
            out.append(target)
    return out


def normalize_target(value):
    """Map free text ("dining out", "restaurants", "leakage") to a target.

    Returns a category name, ``"Taxi"``, a basket key, or None.
    """
    if not value:
        return None
    text = str(value).strip()
    for c in CATEGORIES:
        if text.lower() == c.lower():
            return c
    if text in analytics.BASKETS:
        return text
    for key, label in analytics.BASKETS.items():
        if text.lower() == label.lower():
            return key
    found = find_targets(text)
    return found[0] if found else None


# --- Periods and months -------------------------------------------------------

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_RE = re.compile(
    r"(?<![\w-])(?P<prefix>(?:in|of|for|during|and|vs|versus|to|from|since|with|"
    r"between)\s+)?(?P<name>"
    + "|".join(sorted(MONTHS, key=len, reverse=True))
    + r")\.?(?:\s+(?P<year>20\d\d))?(?![\w-])",
    re.IGNORECASE,
)
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}
_N = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"


def _num(token):
    token = token.lower()
    return NUMBER_WORDS.get(token) or int(token)


def find_months(text, today=None):
    """``YYYY-MM`` keys for month names in ``text`` (latest one <= today).

    "may" only counts with a preposition before it or a year after it, so
    "may I" is not read as a month.
    """
    today = today or analytics.AS_OF
    out = []
    for m in _MONTH_RE.finditer(text or ""):
        name = m.group("name").lower()
        if name == "may" and not (m.group("prefix") or m.group("year")):
            continue
        month = MONTHS[name]
        if m.group("year"):
            year = int(m.group("year"))
        else:
            year = today.year if month <= today.month else today.year - 1
        key = f"{year:04d}-{month:02d}"
        if key not in out:
            out.append(key)
    return out


def find_period(text, today=None):
    """Period name for analytics (``last_month``, ``YYYY-MM``...) or None."""
    t = (text or "").lower()
    months = find_months(t, today)
    if months:
        return months[0]
    m = re.search(rf"(?:last|past|previous)\s+{_N}\s+months?", t)
    if m:
        n = _num(m.group(1))
        if n <= 1:
            return "last_month"
        if n <= 3:
            return "last_3_months"
        if n <= 6:
            return "last_6_months"
        return "last_12_months"
    rules = (
        (r"\b(all time|ever|since the start|in total)\b", "all"),
        (r"\b(quarter|three months)\b", "last_3_months"),
        (r"\b(half (a )?year|six months)\b", "last_6_months"),
        (
            r"\b(this year|last year|past year|the year|a year|annual|"
            r"annually|yearly|12 months|twelve months|per year)\b",
            "last_12_months",
        ),
        (r"\b(last|previous|past) month\b", "last_month"),
        (r"\bthis month\b", "this_month"),
    )
    for pattern, period in rules:
        if re.search(pattern, t):
            return period
    return None


def find_percent(text):
    """A percentage in the text (0..100) or None."""
    t = (text or "").lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(%|percent|per cent|pct)", t)
    if m:
        return min(100.0, float(m.group(1).replace(",", ".")))
    for word, value in (
        ("in half", 50.0),
        ("by half", 50.0),
        ("half", 50.0),
        ("a third", 33.0),
        ("a quarter", 25.0),
        ("a tenth", 10.0),
        ("completely", 100.0),
        ("entirely", 100.0),
        ("altogether", 100.0),
        ("stop", 100.0),
        ("stopped", 100.0),
        ("stopping", 100.0),
        ("quit", 100.0),
        ("give up", 100.0),
        ("gave up", 100.0),
        ("cut out", 100.0),
        ("no more", 100.0),
    ):
        if re.search(rf"\b{word}\b", t):
            return value
    m = re.search(r"\bby\s+(\d{1,2})\b(?!\s*(?:€|eur|euro|years?|months?))", t)
    if m:
        return float(m.group(1))
    return None


def find_years(text):
    """A number of years (1..30) mentioned in the text, or None."""
    t = (text or "").lower()
    if re.search(r"\ba decade\b|\bten years\b", t):
        return 10
    m = re.search(rf"{_N}\s+years?", t)
    if m:
        return max(1, min(30, _num(m.group(1))))
    return None


# --- Formatting -----------------------------------------------------------------


def eur(x):
    """Money for prose: €1,234 for large amounts, €41.24 for small ones."""
    x = float(x or 0)
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 100 or float(x).is_integer():
        return f"{sign}€{x:,.0f}"
    return f"{sign}€{x:,.2f}"


def pct(x, digits=0):
    """0.4672 -> '47%'."""
    return f"{float(x) * 100:.{digits}f}%"


def month_label(key, year=True):
    """'2026-09' -> 'September 2026' (or 'September')."""
    d = date(int(key[:4]), int(key[5:7]), 1)
    return d.strftime("%B %Y" if year else "%B")


def month_short(key):
    """'2026-09' -> 'Sep'."""
    return date(int(key[:4]), int(key[5:7]), 1).strftime("%b")


def day_label(iso):
    """'2026-10-02' -> '2 Oct'."""
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def full_date(iso):
    """'2026-07-01' -> '1 July 2026'."""
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"
