"""Pure analytics over one customer's transactions.

Every public function takes a list of :class:`Tx` (one customer, any order
is fine but chronological is assumed where noted; :func:`prepare` sorts) and
returns plain JSON-serialisable dicts/lists. Nothing here touches the
database, so the functions are cheap to unit test and safe for the LLM coach
to call as tools. Load data with :mod:`finance.services`.

Conventions
-----------
* Money is EUR, rounded to 2 dp on output. Outflows are negative in ``Tx``
  but reported as positive "spend" figures.
* "Today" is the last transaction date in the dataset (:data:`AS_OF`) unless
  a ``today`` argument is passed.
* Monthly averages use the 12 full calendar months ending with today's month
  (Oct 2025 .. Sep 2026 for the default ``AS_OF``).
* Money movements (investment deposits/withdrawals, salary sweeps) are never
  counted as spend or income.
"""

from __future__ import annotations

import calendar
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median, pstdev

AS_OF = date(2026, 9, 30)
WINDOW_MONTHS = 12
SAVINGS_INTEREST = 0.03  # p.a., used by what-if projections

# --- Category taxonomy ----------------------------------------------------

INCOME_CATEGORIES = {"Salary", "Other Income"}
MOVEMENT_CATEGORIES = {"Invest Deposit", "Invest Withdraw", "Salary Sweep"}
REGULAR_CATEGORIES = {"Housing", "Utilities", "Groceries"}
IRREGULAR_CATEGORIES = {"Health", "Home & Tech", "Travel"}
LEAKAGE_CATEGORIES = {"Restaurants", "Entertainment", "Lifestyle", "Transportation"}
SPEND_CATEGORIES = REGULAR_CATEGORIES | IRREGULAR_CATEGORIES | LEAKAGE_CATEGORIES
# Categories where a same-merchant monthly payment looks like a subscription
# (gym, streaming, software...). Groceries, taxis etc. repeat by habit.
SUBSCRIPTION_CATEGORIES = {"Entertainment", "Lifestyle", "Home & Tech", "Health"}
# Bills a customer is committed to (used for "upcoming bills").
BILL_CATEGORIES = {"Housing", "Utilities"}

BASKETS = {
    "mandatory_regular": "Must-pay bills",
    "mandatory_irregular": "Surprise essentials",
    "leakage": "Everyday leakage",
}

TAXI_MCC = "4121"
MCC_LABELS = {
    "4111": "Public transport",
    "4121": "Taxis & ride-hailing",
    "4511": "Airlines",
    "5200": "Home supplies",
    "5411": "Supermarkets",
    "5422": "Butchers & delis",
    "5499": "Food shops",
    "5541": "Fuel stations",
    "5542": "Fuel (automated)",
    "5651": "Clothing",
    "5691": "Clothing",
    "5734": "Software & computers",
    "5812": "Restaurants",
    "5813": "Bars",
    "5814": "Fast food & cafes",
    "5912": "Pharmacies",
    "5941": "Sporting goods",
    "5942": "Books",
    "5945": "Toys & hobbies",
    "5999": "Specialty retail",
    "7011": "Hotels",
    "7512": "Car rental",
    "7523": "Parking",
    "7832": "Cinemas",
    "7922": "Theatre & events",
    "7991": "Attractions",
    "7996": "Amusement parks",
    "7999": "Recreation",
    "8011": "Doctors",
    "8021": "Dentists",
    "8099": "Health services",
}


@dataclass(frozen=True, slots=True)
class Tx:
    """One transaction. ``amount`` < 0 is an outflow."""

    date: date
    timestamp: datetime | None
    category: str
    amount: float
    balance: float
    type: str = ""
    merchant_id: str | None = None
    mcc: str | None = None


# --- Small helpers ----------------------------------------------------------


def r2(x):
    """Round money to 2 dp (and turn -0.0 into 0.0)."""
    return round(float(x), 2) + 0.0


def month_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def shift_month(year, month, delta):
    """Return (year, month) shifted by ``delta`` months."""
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def last_months(today=None, n=WINDOW_MONTHS):
    """Keys of the ``n`` calendar months ending with today's month, oldest first."""
    today = today or AS_OF
    return [
        "%04d-%02d" % shift_month(today.year, today.month, -i)
        for i in range(n - 1, -1, -1)
    ]


def month_bounds(key):
    """First and last date of a ``YYYY-MM`` month."""
    year, month = int(key[:4]), int(key[5:7])
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def resolve_period(period="last_12_months", today=None):
    """Turn a period name into ``(start, end, label)`` (inclusive dates).

    Accepts ``last_month``, ``this_month``, ``last_3_months``,
    ``last_6_months``, ``last_12_months``, ``all`` or a ``YYYY-MM`` key.
    The "last N months" periods end with the latest complete month, which for
    the dataset's month-end ``AS_OF`` is today's month (September 2026).
    """
    today = today or AS_OF
    sizes = {
        None: 12,
        "": 12,
        "year": 12,
        "last_12_months": 12,
        "last_6_months": 6,
        "last_3_months": 3,
        "last_month": 1,
    }
    if period == "all":
        return date(1900, 1, 1), today, "all time"
    if period == "this_month":
        key = month_key(today)
        return month_bounds(key)[0], today, _month_label(key)
    if isinstance(period, str) and len(period) == 7 and period[4] == "-":
        start, end = month_bounds(period)
        return start, min(end, today), _month_label(period)
    if period not in sizes:
        raise ValueError(f"Unknown period {period!r}")
    n = sizes[period]
    anchor = today
    if today != month_bounds(month_key(today))[1]:
        anchor = today.replace(day=1) - timedelta(days=1)
    months = last_months(anchor, n)
    start = month_bounds(months[0])[0]
    end = month_bounds(months[-1])[1]
    label = _month_label(months[0]) if n == 1 else f"last {n} months"
    return start, end, label


def _month_label(key):
    start, _ = month_bounds(key)
    return start.strftime("%B %Y")


def prepare(txns):
    """Return transactions sorted chronologically."""
    return sorted(txns, key=lambda t: (t.date, t.timestamp or datetime.min))


def in_range(txns, start, end):
    return [t for t in txns if start <= t.date <= end]


def is_spend(t):
    return t.category in SPEND_CATEGORIES and t.amount < 0


def is_income(t):
    return t.category in INCOME_CATEGORIES and t.amount > 0


# --- Baskets ------------------------------------------------------------------


def detect_subscriptions(txns, today=None, min_months=6):
    """Find recurring subscriptions: same merchant, ~monthly, similar amount.

    A merchant in a subscription-like category counts when it was paid in at
    least ``min_months`` of the last 12 months, at most ~1.3 times per active
    month, around the same day (spread <= 7 days) and with amounts varying by
    less than 15% (coefficient of variation).

    Returns ``[{"merchant_id","category","monthly_amount","months",
    "typical_day"}]`` sorted by amount.
    """
    today = today or AS_OF
    months = set(last_months(today))
    by_merchant = defaultdict(list)
    for t in txns:
        if (
            t.merchant_id
            and t.category in SUBSCRIPTION_CATEGORIES
            and is_spend(t)
            and month_key(t.date) in months
        ):
            by_merchant[t.merchant_id].append(t)
    found = []
    for merchant, items in by_merchant.items():
        active = {month_key(t.date) for t in items}
        if len(active) < min_months or len(items) > 1.3 * len(active):
            continue
        amounts = [-t.amount for t in items]
        mean = sum(amounts) / len(amounts)
        if mean <= 0 or pstdev(amounts) / mean > 0.15:
            continue
        if pstdev([t.date.day for t in items]) > 7:
            continue
        found.append(
            {
                "merchant_id": merchant,
                "category": items[0].category,
                "monthly_amount": r2(median(amounts)),
                "months": len(active),
                "typical_day": int(median(t.date.day for t in items)),
            }
        )
    return sorted(found, key=lambda s: -s["monthly_amount"])


def classify_basket(t, subscription_merchants=frozenset()):
    """Basket key for one transaction, or ``None`` if it is not spend.

    Housing, Utilities, Groceries and recurring subscriptions are
    ``mandatory_regular``; Health, Home & Tech and Travel are
    ``mandatory_irregular``; Restaurants, Entertainment, Lifestyle and
    Transportation (incl. taxis, MCC 4121) are ``leakage``.
    """
    if not is_spend(t):
        return None
    if t.merchant_id and t.merchant_id in subscription_merchants:
        return "mandatory_regular"
    if t.category in REGULAR_CATEGORIES:
        return "mandatory_regular"
    if t.category in IRREGULAR_CATEGORIES:
        return "mandatory_irregular"
    return "leakage"


def _subs_set(txns, today=None):
    return frozenset(s["merchant_id"] for s in detect_subscriptions(txns, today))


def basket_breakdown(txns, today=None, top_n=3):
    """Monthly averages per basket over the last 12 months.

    Returns ``[{"key","label","monthly_avg","share",
    "top_categories":[{"category","monthly_avg"}]}]`` in basket order.
    """
    today = today or AS_OF
    start, end, _ = resolve_period("last_12_months", today)
    subs = _subs_set(txns, today)
    totals = defaultdict(float)
    cats = defaultdict(lambda: defaultdict(float))
    for t in in_range(txns, start, end):
        basket = classify_basket(t, subs)
        if basket:
            totals[basket] += -t.amount
            cats[basket][t.category] += -t.amount
    grand = sum(totals.values()) or 1.0
    out = []
    for key, label in BASKETS.items():
        top = sorted(cats[key].items(), key=lambda kv: -kv[1])[:top_n]
        out.append(
            {
                "key": key,
                "label": label,
                "monthly_avg": r2(totals[key] / WINDOW_MONTHS),
                "share": round(totals[key] / grand, 4),
                "top_categories": [
                    {"category": c, "monthly_avg": r2(v / WINDOW_MONTHS)}
                    for c, v in top
                ],
            }
        )
    return out


# --- Cashflow -----------------------------------------------------------------


def monthly_cashflow(txns, today=None, n=WINDOW_MONTHS):
    """Income, spend and net per month for the last ``n`` months.

    Returns ``[{"month":"2025-10","income","spend","net"}]`` oldest first.
    """
    keys = last_months(today, n)
    income = dict.fromkeys(keys, 0.0)
    spend = dict.fromkeys(keys, 0.0)
    for t in txns:
        k = month_key(t.date)
        if k not in income:
            continue
        if is_income(t):
            income[k] += t.amount
        elif is_spend(t):
            spend[k] += -t.amount
    return [
        {
            "month": k,
            "income": r2(income[k]),
            "spend": r2(spend[k]),
            "net": r2(income[k] - spend[k]),
        }
        for k in keys
    ]


def current_balance(txns):
    """Balance after the latest transaction (0 if there are none)."""
    if not txns:
        return 0.0
    latest = max(txns, key=lambda t: (t.date, t.timestamp or datetime.min))
    return r2(latest.balance)


def summary(txns, today=None):
    """Headline numbers: 12-month average income/spend, savings rate, balance.

    ``savings_rate`` = (income - spend) / income, clamped to [-1, 1]; 0 when
    there is no income.
    """
    flow = monthly_cashflow(txns, today)
    income = sum(m["income"] for m in flow) / len(flow)
    spend = sum(m["spend"] for m in flow) / len(flow)
    rate = (income - spend) / income if income > 0 else 0.0
    return {
        "income_monthly_avg": r2(income),
        "spend_monthly_avg": r2(spend),
        "savings_rate": round(max(-1.0, min(1.0, rate)), 4),
        "balance": current_balance(txns),
    }


def last_month_summary(txns, today=None):
    """Income, spend and basket totals for the most recent complete month."""
    today = today or AS_OF
    start, end, _ = resolve_period("last_month", today)
    subs = _subs_set(txns, today)
    income = spend = 0.0
    baskets = dict.fromkeys(BASKETS, 0.0)
    for t in in_range(txns, start, end):
        if is_income(t):
            income += t.amount
        basket = classify_basket(t, subs)
        if basket:
            spend += -t.amount
            baskets[basket] += -t.amount
    return {
        "month": month_key(start),
        "income": r2(income),
        "spend": r2(spend),
        "baskets": {k: r2(v) for k, v in baskets.items()},
    }


# --- Safe to spend --------------------------------------------------------------


def _clip_day(year, month, day):
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _next_day_of_month(after, day):
    """First date strictly after ``after`` falling on ``day`` (clipped)."""
    candidate = _clip_day(after.year, after.month, day)
    if candidate > after:
        return candidate
    y, m = shift_month(after.year, after.month, 1)
    return _clip_day(y, m, day)


def payday_pattern(txns, today=None):
    """Detect salary cadence from Salary transactions.

    Returns ``{"cadence": "monthly"|"irregular"|"none", "typical_day",
    "end_of_month": bool, "last_payday", "next_payday",
    "typical_amount"}`` (dates as ISO strings).
    """
    today = today or AS_OF
    salaries = [t for t in txns if t.category == "Salary" and t.amount > 0]
    salaries = [t for t in salaries if t.date <= today][-12:]
    if not salaries:
        return {
            "cadence": "none",
            "typical_day": None,
            "end_of_month": False,
            "last_payday": None,
            "next_payday": (today + timedelta(days=30)).isoformat(),
            "typical_amount": 0.0,
        }
    days = [t.date.day for t in salaries]
    # Salaries paid on the last days of the month drift with month length.
    end_of_month = sum(d >= 26 for d in days) >= 0.7 * len(days)
    mode_day, mode_count = Counter(days).most_common(1)[0]
    typical_day = 31 if end_of_month else mode_day
    gaps = [(b.date - a.date).days for a, b in zip(salaries, salaries[1:])]
    # Monthly if the pay day is stable (an occasional early payment, e.g.
    # before a holiday, is fine) or every gap is roughly a month.
    regular = len(salaries) >= 3 and (
        end_of_month
        or mode_count >= 0.6 * len(days)
        or all(20 <= g <= 40 for g in gaps)
    )
    if regular:
        nxt = _next_day_of_month(today, typical_day)
    elif gaps:
        nxt = salaries[-1].date + timedelta(days=int(median(gaps)))
        while nxt <= today:
            nxt += timedelta(days=int(median(gaps)) or 30)
    else:
        nxt = salaries[-1].date + timedelta(days=30)
        while nxt <= today:
            nxt += timedelta(days=30)
    return {
        "cadence": "monthly" if regular else "irregular",
        "typical_day": typical_day,
        "end_of_month": end_of_month,
        "last_payday": salaries[-1].date.isoformat(),
        "next_payday": nxt.isoformat(),
        "typical_amount": r2(median(t.amount for t in salaries)),
    }


def bill_schedule(txns, today=None, lookback_months=6):
    """Regular bills with their typical day of month and amount.

    A "bill stream" is a bill category (Housing, Utilities) or a detected
    subscription merchant. Streams seen in at least half of the last
    ``lookback_months`` months are kept. ``fixed_day`` is True when the
    payment day varies by at most ~5 days; otherwise the bill is spread
    through the month (e.g. several utility payments).

    Returns ``[{"label","category","typical_day","fixed_day",
    "monthly_amount","per_payment","payments_per_month"}]``.
    """
    today = today or AS_OF
    months = last_months(today, lookback_months)
    start = month_bounds(months[0])[0]
    subs = {s["merchant_id"]: s for s in detect_subscriptions(txns, today)}
    streams = defaultdict(list)
    for t in in_range(txns, start, today):
        if not is_spend(t):
            continue
        if t.merchant_id in subs:
            streams[("sub", t.merchant_id)].append(t)
        elif t.category in BILL_CATEGORIES:
            streams[("cat", t.category)].append(t)
    out = []
    for (kind, name), items in streams.items():
        active = {month_key(t.date) for t in items}
        if len(active) < lookback_months / 2:
            continue
        days = [t.date.day for t in items]
        per_month = len(items) / len(active)
        fixed = per_month <= 1.3 and pstdev(days) <= 5
        total = sum(-t.amount for t in items)
        label = name if kind == "cat" else f"{subs[name]['category']} subscription"
        out.append(
            {
                "label": label,
                "category": items[0].category,
                "typical_day": int(median(days)),
                "fixed_day": fixed,
                "monthly_amount": r2(total / lookback_months),
                "per_payment": r2(median(-t.amount for t in items)),
                "payments_per_month": round(per_month, 2),
            }
        )
    return sorted(out, key=lambda b: -b["monthly_amount"])


def _monthly_spend_avg(txns, today):
    flow = monthly_cashflow(txns, today)
    return sum(m["spend"] for m in flow) / len(flow)


def safe_to_spend(txns, today=None):
    """How much can be spent per day until the next payday.

    amount = balance - bills expected before payday - reserve (floored at 0);
    ``per_day`` spreads it over the days until payday. Fixed-day bills are
    included when their next due date falls before payday; spread-out bills
    are pro-rated by days. The reserve is 10% of average monthly spend,
    clamped to 50..300 EUR.

    Returns ``{"amount","per_day","days_until_payday","next_payday",
    "reserve","balance","upcoming_bills":[{"label","amount","due"}],
    "typical_spend_per_day"}``.
    """
    today = today or AS_OF
    balance = current_balance(txns)
    pay = payday_pattern(txns, today)
    next_payday = date.fromisoformat(pay["next_payday"])
    days = max(1, (next_payday - today).days)
    upcoming = []
    for bill in bill_schedule(txns, today):
        if bill["fixed_day"]:
            due = _next_day_of_month(today, bill["typical_day"])
            if due <= next_payday:
                upcoming.append(
                    {
                        "label": bill["label"],
                        "amount": bill["per_payment"],
                        "due": due.isoformat(),
                    }
                )
        else:
            amount = bill["monthly_amount"] * days / 30.4
            if amount >= 1:
                upcoming.append(
                    {
                        "label": f"{bill['label']} (spread over the month)",
                        "amount": r2(amount),
                        "due": next_payday.isoformat(),
                    }
                )
    upcoming.sort(key=lambda b: b["due"])
    # Typical day-to-day (non-bill) spend per day over the last 3 months, so
    # callers can put a large safe-to-spend figure in context.
    s3, e3, _ = resolve_period("last_3_months", today)
    everyday = sum(
        -t.amount
        for t in in_range(txns, s3, e3)
        if is_spend(t) and t.category not in BILL_CATEGORIES
    )
    typical_per_day = everyday / ((e3 - s3).days + 1)
    reserve = min(300.0, max(50.0, 0.10 * _monthly_spend_avg(txns, today)))
    bills = sum(b["amount"] for b in upcoming)
    amount = max(0.0, balance - bills - reserve)
    return {
        "amount": r2(amount),
        "per_day": r2(amount / days),
        "days_until_payday": days,
        "next_payday": next_payday.isoformat(),
        "reserve": r2(reserve),
        "balance": r2(balance),
        "upcoming_bills": upcoming,
        "typical_spend_per_day": r2(typical_per_day),
    }


# --- Features + persona -----------------------------------------------------


def features(txns, today=None):
    """Behavioural signals over the last 12 months (used for personas).

    Returns ``{"income","spend","savings_rate","leakage_share",
    "weekend_leakage_share","irregular_share","invest_monthly",
    "invest_rate","sweep_monthly","balance_now","balance_avg","balance_min",
    "balance_volatility","overdraft_days","cushion_months","tx_count"}``.
    """
    today = today or AS_OF
    start, end, _ = resolve_period("last_12_months", today)
    window = in_range(txns, start, end)
    head = summary(txns, today)
    income = head["income_monthly_avg"]
    spend = head["spend_monthly_avg"]
    leak = weekend_leak = irregular = invested = swept = 0.0
    balances = []
    overdraft = set()
    for t in window:
        balances.append(t.balance)
        if t.balance < 0:
            overdraft.add(t.date)
        if t.category == "Invest Deposit":
            invested += -t.amount
        elif t.category == "Invest Withdraw":
            invested -= t.amount
        elif t.category == "Salary Sweep":
            swept += -t.amount
        if not is_spend(t):
            continue
        if t.category in LEAKAGE_CATEGORIES:
            leak += -t.amount
            if t.date.isoweekday() >= 5:
                weekend_leak += -t.amount
        elif t.category in IRREGULAR_CATEGORIES:
            irregular += -t.amount
    total_spend = spend * WINDOW_MONTHS
    invest_monthly = invested / WINDOW_MONTHS
    bal_avg = sum(balances) / len(balances) if balances else head["balance"]
    return {
        "income": income,
        "spend": spend,
        "savings_rate": head["savings_rate"],
        "leakage_share": round(leak / total_spend, 4) if total_spend else 0.0,
        "weekend_leakage_share": round(weekend_leak / leak, 4) if leak else 0.0,
        "irregular_share": (round(irregular / total_spend, 4) if total_spend else 0.0),
        "invest_monthly": r2(invest_monthly),
        "invest_rate": round(invest_monthly / income, 4) if income else 0.0,
        "sweep_monthly": r2(swept / WINDOW_MONTHS),
        "balance_now": head["balance"],
        "balance_avg": r2(bal_avg),
        "balance_min": r2(min(balances)) if balances else head["balance"],
        "balance_volatility": (
            round(pstdev(balances) / income, 4) if income and balances else 0.0
        ),
        "overdraft_days": len(overdraft),
        "cushion_months": round(bal_avg / spend, 2) if spend else 0.0,
        "tx_count": len(window),
    }


PERSONAS = {
    "paycheck_to_paycheck": {
        "label": "Paycheck-to-Paycheck",
        "description": (
            "Money comes in and goes straight back out. Your balance runs low "
            "before payday, so a small buffer would make a big difference."
        ),
    },
    "investor": {
        "label": "Investor",
        "description": (
            "You regularly move money into investments, so your future self "
            "is already on the payroll."
        ),
    },
    "comfortable": {
        "label": "Comfortable",
        "description": (
            "You keep a healthy cushion in the bank and comfortably cover "
            "your costs. The question is making that idle money work."
        ),
    },
    "steady_saver": {
        "label": "Steady Saver",
        "description": (
            "You spend well below what you earn, month after month, and keep "
            "everyday leakage in check."
        ),
    },
    "weekend_spender": {
        "label": "Weekend Spender",
        "description": (
            "Eating out, going out and shopping take a big slice of your "
            "money, much of it from Friday to Sunday."
        ),
    },
    "balanced": {
        "label": "Balanced Budgeter",
        "description": (
            "Income and spending are roughly in balance with no extremes: "
            "a solid base to start building savings on."
        ),
    },
}

# Thresholds, tuned on the dataset so the six personas are reasonably even.
P2P_MAX_SAVINGS = 0.03
P2P_OVERDRAFT_DAYS = 15
INVESTOR_MIN_RATE = 0.07
COMFORT_MIN_CUSHION = 4.0
SAVER_MIN_RATE = 0.10
WEEKEND_MIN_LEAKAGE = 0.30


def assign_persona(f):
    """Rule-based persona from :func:`features` output.

    Returns ``(key, score)`` where score (0..1) says how clearly the customer
    fits, used to pick featured examples. Rules, first match wins:

    1. paycheck_to_paycheck: savings rate < 3% and overdrawn on 15+ days, or
       spending clearly more than earned.
    2. investor: >= 7% of income moved into investments.
    3. comfortable: average balance >= 4 months of spend, not losing money.
    4. steady_saver: savings rate >= 10%.
    5. weekend_spender: leakage >= 30% of spend.
    6. balanced: everyone else.
    """
    rate = f["savings_rate"]

    def clamp(x):
        return max(0.0, min(1.0, x))

    if (rate < P2P_MAX_SAVINGS and f["overdraft_days"] >= P2P_OVERDRAFT_DAYS) or (
        rate < -0.08
    ):
        return "paycheck_to_paycheck", clamp(
            0.5 * f["overdraft_days"] / 120 + 0.5 * clamp(-rate * 4)
        )
    if f["invest_rate"] >= INVESTOR_MIN_RATE:
        return "investor", clamp(f["invest_rate"] / 0.15)
    if f["cushion_months"] >= COMFORT_MIN_CUSHION and rate >= 0:
        return "comfortable", clamp(f["cushion_months"] / 8)
    if rate >= SAVER_MIN_RATE:
        return "steady_saver", clamp(rate / 0.35) * clamp(1.4 - f["leakage_share"])
    if f["leakage_share"] >= WEEKEND_MIN_LEAKAGE:
        return "weekend_spender", clamp(
            (f["leakage_share"] - 0.25) * 5 + f["weekend_leakage_share"] - 0.5
        )
    return "balanced", clamp(1 - abs(rate - 0.05) * 5)


def _pct(x):
    return f"{x * 100:.0f}%"


def _eur(x):
    """Format money for prose: €1,234 or -€56."""
    return f"-€{-x:,.0f}" if x < -0.5 else f"€{abs(x):,.0f}"


def persona(txns, today=None, feats=None):
    """Spender persona with description and number-backed traits.

    Returns ``{"key","label","description","traits":[str],"score"}``.
    """
    f = feats or features(txns, today)
    key, score = assign_persona(f)
    traits = [f"Saves {_pct(f['savings_rate'])} of income"]
    if f["savings_rate"] < 0:
        traits[0] = f"Spends {_pct(-f['savings_rate'])} more than earned"
    traits.append(f"{_pct(f['leakage_share'])} of spend is everyday leakage")
    if f["invest_monthly"] > 0:
        traits.append(f"Invests {_eur(f['invest_monthly'])} a month")
    if f["sweep_monthly"] > 0:
        traits.append(f"Sweeps {_eur(f['sweep_monthly'])} a month to another account")
    if f["overdraft_days"]:
        traits.append(f"Balance below zero on {f['overdraft_days']} days this year")
    else:
        traits.append(f"Average balance {_eur(f['balance_avg'])}")
    if key == "weekend_spender":
        traits.append(f"{_pct(f['weekend_leakage_share'])} of leakage is Fri-Sun")
    if key == "comfortable":
        traits.append(f"Cushion of {f['cushion_months']:.1f} months of spending")
    return {
        "key": key,
        "label": PERSONAS[key]["label"],
        "description": PERSONAS[key]["description"],
        "traits": traits[:4],
        "score": round(score, 3),
    }


# --- Tool-style helpers for the coach ---------------------------------------


def spend_by_category(txns, period="last_month", today=None):
    """Spend per category for a period, biggest first.

    Returns ``{"period","start","end","total",
    "categories":[{"category","basket","amount","count","share"}]}``.
    """
    start, end, label = resolve_period(period, today)
    subs = _subs_set(txns, today)
    amounts = defaultdict(float)
    counts = Counter()
    baskets = {}
    for t in in_range(txns, start, end):
        basket = classify_basket(t, subs)
        if basket:
            amounts[t.category] += -t.amount
            counts[t.category] += 1
            baskets.setdefault(t.category, basket)
    total = sum(amounts.values())
    rows = [
        {
            "category": c,
            "basket": baskets[c],
            "amount": r2(v),
            "count": counts[c],
            "share": round(v / total, 4) if total else 0.0,
        }
        for c, v in sorted(amounts.items(), key=lambda kv: -kv[1])
    ]
    return {
        "period": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": r2(total),
        "categories": rows,
    }


def spend_by_merchant_type(txns, period="last_month", category=None, today=None):
    """Spend grouped by merchant type (MCC), optionally within one category.

    Returns ``{"period","total","types":[{"mcc","label","category","amount",
    "count"}]}`` biggest first. Transactions without an MCC are grouped
    under ``mcc: null``.
    """
    start, end, label = resolve_period(period, today)
    groups = defaultdict(lambda: [0.0, 0, ""])
    for t in in_range(txns, start, end):
        if not is_spend(t) or (category and t.category != category):
            continue
        g = groups[t.mcc]
        g[0] += -t.amount
        g[1] += 1
        g[2] = g[2] or t.category
    rows = [
        {
            "mcc": mcc,
            "label": MCC_LABELS.get(mcc, "Other") if mcc else "Unspecified",
            "category": cat,
            "amount": r2(amount),
            "count": count,
        }
        for mcc, (amount, count, cat) in sorted(
            groups.items(), key=lambda kv: -kv[1][0]
        )
    ]
    return {
        "period": label,
        "total": r2(sum(g[0] for g in groups.values())),
        "types": rows,
    }


def taxi_stats(txns, period="last_month", today=None, months=6):
    """Taxi (MCC 4121) rides and spend for a period plus a monthly trend.

    Returns ``{"period","rides","total","avg_per_ride",
    "monthly":[{"month","rides","amount"}],"monthly_avg_last_12"}``.
    """
    start, end, label = resolve_period(period, today)
    taxis = [t for t in txns if t.mcc == TAXI_MCC and t.amount < 0]
    chosen = in_range(taxis, start, end)
    total = sum(-t.amount for t in chosen)
    keys = last_months(today, months)
    per_month = {k: [0, 0.0] for k in keys}
    for t in taxis:
        k = month_key(t.date)
        if k in per_month:
            per_month[k][0] += 1
            per_month[k][1] += -t.amount
    s12, e12, _ = resolve_period("last_12_months", today)
    year_total = sum(-t.amount for t in in_range(taxis, s12, e12))
    return {
        "period": label,
        "rides": len(chosen),
        "total": r2(total),
        "avg_per_ride": r2(total / len(chosen)) if chosen else 0.0,
        "monthly": [
            {"month": k, "rides": v[0], "amount": r2(v[1])}
            for k, v in per_month.items()
        ],
        "monthly_avg_last_12": r2(year_total / WINDOW_MONTHS),
    }


def category_trend(txns, category, months=12, today=None):
    """Monthly spend for a category (or a basket key) over ``months`` months.

    Returns ``{"category","months":[{"month","amount"}],"monthly_avg",
    "change_pct"}`` where change_pct compares the last 3 months with the 3
    before them (None if there is no earlier spend).
    """
    keys = last_months(today, months)
    subs = _subs_set(txns, today)
    amounts = dict.fromkeys(keys, 0.0)
    for t in txns:
        k = month_key(t.date)
        if k in amounts and _matches(t, category, subs):
            amounts[k] += -t.amount
    values = list(amounts.values())
    recent, before = sum(values[-3:]), sum(values[-6:-3])
    return {
        "category": category,
        "months": [{"month": k, "amount": r2(v)} for k, v in amounts.items()],
        "monthly_avg": r2(sum(values) / len(values)),
        "change_pct": round((recent - before) / before, 4) if before else None,
    }


def _matches(t, target, subs):
    """True if spend ``t`` belongs to a category name or basket key."""
    basket = classify_basket(t, subs)
    if not basket:
        return False
    if target in BASKETS:
        return basket == target
    if target == "Taxi":
        return t.mcc == TAXI_MCC
    return t.category == target


def project_savings(monthly_saving, years, rate=SAVINGS_INTEREST):
    """Value of saving ``monthly_saving`` each month, compounded monthly.

    Returns ``[{"year","saved","with_interest"}]`` for years 1..``years``.
    """
    i = rate / 12
    out = []
    for y in range(1, years + 1):
        n = 12 * y
        fv = monthly_saving * (((1 + i) ** n - 1) / i) if i else monthly_saving * n
        out.append(
            {"year": y, "saved": r2(monthly_saving * n), "with_interest": r2(fv)}
        )
    return out


def what_if(txns, target, pct, years=5, today=None):
    """Project the effect of cutting a category or basket by ``pct`` percent.

    ``target`` is a category ("Restaurants"), "Taxi", or a basket key
    ("leakage"). ``pct`` is 0..100. Savings compound at 3% p.a.

    Returns ``{"target","pct","current_monthly","monthly_saving",
    "yearly_saving","years","projection":[{"year","saved",
    "with_interest"}],"total_with_interest"}``.
    """
    years = max(1, min(int(years), 30))
    pct = max(0.0, min(float(pct), 100.0))
    trend = category_trend(txns, target, WINDOW_MONTHS, today)
    current = trend["monthly_avg"]
    saving = current * pct / 100
    projection = project_savings(saving, years)
    return {
        "target": target,
        "pct": pct,
        "current_monthly": r2(current),
        "monthly_saving": r2(saving),
        "yearly_saving": r2(saving * 12),
        "years": years,
        "projection": projection,
        "total_with_interest": projection[-1]["with_interest"],
    }


def compare_months(txns, month_a, month_b, today=None):
    """Compare spend per category between two ``YYYY-MM`` months.

    Returns ``{"month_a","month_b","total_a","total_b","diff",
    "categories":[{"category","a","b","diff"}]}`` sorted by absolute
    difference.
    """
    a = spend_by_category(txns, month_a, today)
    b = spend_by_category(txns, month_b, today)
    av = {c["category"]: c["amount"] for c in a["categories"]}
    bv = {c["category"]: c["amount"] for c in b["categories"]}
    rows = [
        {
            "category": c,
            "a": r2(av.get(c, 0)),
            "b": r2(bv.get(c, 0)),
            "diff": r2(bv.get(c, 0) - av.get(c, 0)),
        }
        for c in set(av) | set(bv)
    ]
    rows.sort(key=lambda r: -abs(r["diff"]))
    return {
        "month_a": month_a,
        "month_b": month_b,
        "total_a": a["total"],
        "total_b": b["total"],
        "diff": r2(b["total"] - a["total"]),
        "categories": rows,
    }


def biggest_expenses(txns, period="last_month", n=5, today=None):
    """The ``n`` largest single spend transactions in a period.

    Returns ``{"period","items":[{"date","category","amount","merchant_id",
    "merchant_type","basket"}]}``.
    """
    start, end, label = resolve_period(period, today)
    subs = _subs_set(txns, today)
    items = sorted(
        (t for t in in_range(txns, start, end) if is_spend(t)),
        key=lambda t: t.amount,
    )[:n]
    return {
        "period": label,
        "items": [
            {
                "date": t.date.isoformat(),
                "category": t.category,
                "amount": r2(-t.amount),
                "merchant_id": t.merchant_id,
                "merchant_type": MCC_LABELS.get(t.mcc) if t.mcc else None,
                "basket": classify_basket(t, subs),
            }
            for t in items
        ],
    }


# --- Insights ---------------------------------------------------------------------


def insights(txns, today=None, feats=None, limit=5):
    """3-5 concrete, number-backed observations, most important first.

    Returns ``[{"title","text","tone":"good"|"warn"|"info"}]``.
    """
    today = today or AS_OF
    f = feats or features(txns, today)
    cands = []  # (priority, insight)

    def add(priority, title, text, tone):
        cands.append((priority, {"title": title, "text": text, "tone": tone}))

    rate = f["savings_rate"]
    margin = f["income"] - f["spend"]
    if rate >= 0.15:
        add(
            5,
            "Strong saver",
            f"You keep {_pct(rate)} of your income: about {_eur(margin)} a "
            "month on average.",
            "good",
        )
    elif rate < 0:
        add(
            9,
            "Spending more than you earn",
            f"Over the last 12 months you spent {_eur(-margin)} a month more "
            "than came in.",
            "warn",
        )
    else:
        gap = max(0.0, 0.10 * f["income"] - margin)
        add(
            4,
            "Thin margin",
            f"You save {_pct(rate)} of income ({_eur(margin)} a month)."
            + (f" Reaching 10% means {_eur(gap)} more a month." if gap else ""),
            "info",
        )

    s12, e12, _ = resolve_period("last_12_months", today)
    subs = _subs_set(txns, today)
    leak_cats = defaultdict(float)
    for t in in_range(txns, s12, e12):
        if classify_basket(t, subs) == "leakage":
            leak_cats[t.category] += -t.amount
    if leak_cats:
        cat, total = max(leak_cats.items(), key=lambda kv: kv[1])
        monthly = total / WINDOW_MONTHS
        add(
            7,
            f"{cat} is your biggest leak",
            f"You spend about {_eur(monthly)} a month on {cat.lower()}. "
            f"Cutting it by 20% frees up {_eur(monthly * 0.2 * 12)} a year.",
            "info",
        )

    taxi = taxi_stats(txns, "last_3_months", today)
    if taxi["rides"] >= 3 and taxi["total"] >= 60:
        add(
            6,
            "Taxi habit",
            f"{taxi['rides']} taxi rides in the last 3 months cost "
            f"{_eur(taxi['total'])}, about {_eur(taxi['avg_per_ride'])} a ride.",
            "warn" if taxi["total"] > 200 else "info",
        )

    last = monthly_cashflow(txns, today)[-1]
    avg_spend = f["spend"]
    month_name = _month_label(last["month"]).split()[0]
    delta = (last["spend"] - avg_spend) / avg_spend if avg_spend > 0 else 0
    if delta >= 0.15:
        add(
            8,
            f"{month_name} ran hot",
            f"You spent {_eur(last['spend'])} in {month_name}, {_pct(delta)} "
            f"above your monthly average of {_eur(avg_spend)}.",
            "warn",
        )
    elif delta <= -0.10:
        add(
            8,
            f"Lighter {month_name}",
            f"{month_name} spend was {_eur(last['spend'])}, {_pct(-delta)} "
            f"below your average of {_eur(avg_spend)}.",
            "good",
        )

    if f["overdraft_days"] >= 5:
        add(
            8,
            "Dipping below zero",
            f"Your balance was negative on {f['overdraft_days']} days in the "
            f"last year (lowest {_eur(f['balance_min'])}). A buffer of "
            f"{_eur(0.5 * avg_spend)} would cover half a month.",
            "warn",
        )

    if f["invest_monthly"] > 0:
        add(
            5,
            "Investing habit",
            f"You put {_eur(f['invest_monthly'])} a month into investments "
            f"({_pct(f['invest_rate'])} of income).",
            "good",
        )
    elif f["cushion_months"] >= 3:
        idle = f["balance_avg"] - 2 * avg_spend
        add(
            6,
            "Idle cash",
            f"Your average balance covers {f['cushion_months']:.1f} months of "
            f"spending. Moving the {_eur(idle)} above a 2-month buffer into "
            f"savings at 3% would earn about {_eur(idle * 0.03)} a year.",
            "info",
        )

    big = biggest_expenses(txns, "last_month", 1, today)["items"]
    if big and big[0]["amount"] >= 0.2 * max(avg_spend, 1):
        b = big[0]
        add(
            3,
            "Biggest single cost",
            f"Your largest payment last month was {_eur(b['amount'])} on "
            f"{b['category'].lower()} ({b['date']}).",
            "info",
        )

    trends = []
    for cat in sorted(SPEND_CATEGORIES - {"Housing"}):
        tr = category_trend(txns, cat, 6, today)
        recent = sum(m["amount"] for m in tr["months"][-3:]) / 3
        before = sum(m["amount"] for m in tr["months"][-6:-3]) / 3
        # Ignore noise: need a meaningful level and a >= 30 EUR/month move.
        if tr["change_pct"] is not None and recent >= 60:
            if abs(recent - before) >= 30:
                trends.append((tr["change_pct"], cat, recent))
    if trends:
        change, cat, recent = max(trends)
        if change >= 0.4:
            add(
                5,
                f"{cat} is creeping up",
                f"{cat} averaged {_eur(recent)} a month over the last 3 "
                f"months, up {_pct(change)} on the 3 months before.",
                "warn",
            )
        change, cat, recent = min(trends)
        if change <= -0.3:
            add(
                4,
                f"Less on {cat.lower()}",
                f"{cat} is down {_pct(-change)} on the previous 3 months "
                f"(now {_eur(recent)} a month).",
                "good",
            )

    found_subs = detect_subscriptions(txns, today)
    if found_subs:
        total = sum(s["monthly_amount"] for s in found_subs)
        add(
            5,
            "Recurring subscriptions",
            f"{len(found_subs)} recurring payments add up to {_eur(total)} a "
            "month. Worth checking you still use them all.",
            "info",
        )

    add(
        0,
        "Know your baskets",
        "Sorting spend into bills, surprise essentials and everyday leakage "
        "shows where cuts are easiest.",
        "info",
    )
    add(
        0,
        "Safe to spend",
        "Check your daily safe-to-spend figure before bigger purchases: it "
        "already sets aside upcoming bills.",
        "info",
    )
    cands.sort(key=lambda c: -c[0])
    return [ins for _, ins in cands[:limit]]


# --- Home readiness ---------------------------------------------------------------

MORTGAGE_RATE = 0.06  # stress-test rate
MORTGAGE_YEARS = 25
MAX_LTV = 0.90  # first-home buyers in Finland
MAX_PAYMENT_SHARE = 0.35


def annuity_payment(principal, rate=MORTGAGE_RATE, years=MORTGAGE_YEARS):
    i = rate / 12
    n = years * 12
    return principal * i / (1 - (1 + i) ** -n)


def max_loan_for_payment(payment, rate=MORTGAGE_RATE, years=MORTGAGE_YEARS):
    i = rate / 12
    n = years * 12
    return payment * (1 - (1 + i) ** -n) / i


def affordability(income_monthly, savings_monthly, saved_now):
    """Finnish rule-of-thumb affordability estimate.

    Payment <= 35% of net income, stress-tested at 6% over 25 years; loan is
    at most 90% of the price, so a 10% deposit is needed.

    Returns ``{"max_payment","max_loan","max_property_price",
    "deposit_needed","deposit_saved_estimate","months_to_deposit"}``.
    """
    max_payment = max(0.0, income_monthly * MAX_PAYMENT_SHARE)
    max_loan = max_loan_for_payment(max_payment)
    price = max_loan / MAX_LTV
    deposit = price - max_loan
    saved = max(0.0, saved_now)
    gap = deposit - saved
    if gap <= 0:
        months = 0
    elif savings_monthly > 0:
        months = math.ceil(gap / savings_monthly)
    else:
        months = None
    return {
        "max_payment": r2(max_payment),
        "max_loan": r2(max_loan),
        "max_property_price": r2(price),
        "deposit_needed": r2(deposit),
        "deposit_saved_estimate": r2(saved),
        "months_to_deposit": months,
    }


REJECTION_TEXT = {
    "insufficient_collateral": "the collateral did not cover the loan",
    "insufficient_income": "income was too low for the loan size",
    "insufficient_equity": "the deposit (own equity) was too small",
    "existing_debt": "existing debts were too high",
}


def mortgage_timeline(application, events):
    """Summarise a real mortgage application and its negotiation events.

    ``application`` is a dict with the MortgageApplication fields (or None);
    ``events`` a chronological list of dicts with MortgageEvent fields
    (``timestamp`` as datetime or ISO string).

    Returns ``{"has_application","mortgage_customer_id","decision",
    "rejection_reason","rejection_text","started","decided","days_to_decision",
    "final":{...},"properties_considered","contacts","expenses":[...],
    "steps":[{"date","event_type","text"}]}`` or
    ``{"has_application": False}``.
    """
    if not application:
        return {"has_application": False}

    def ts(e):
        v = e.get("timestamp")
        return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

    events = sorted(events, key=ts)
    started = next(
        (ts(e) for e in events if e["event_type"] == "application_created"), None
    )
    decided = next((ts(e) for e in events if e["event_type"] == "loan_decision"), None)
    props = {e.get("property_id") for e in events if e.get("property_id")}
    expenses = [
        {
            "date": ts(e).date().isoformat(),
            "type": e.get("expense_type") or "",
            "amount": r2(e.get("expense_amount") or 0),
        }
        for e in events
        if e["event_type"] == "expense_recorded"
    ]
    reason = application.get("rejection_reason") or None
    steps = []
    for e in events:
        text = (e.get("note") or "").strip()
        if e.get("property_price_estimate") and e["event_type"].startswith("property"):
            text += f" (price estimate {_eur(e['property_price_estimate'])})"
        steps.append(
            {
                "date": ts(e).date().isoformat(),
                "event_type": e["event_type"],
                "text": text,
            }
        )
    return {
        "has_application": True,
        "mortgage_customer_id": application.get("mortgage_customer_id"),
        "decision": application.get("final_decision"),
        "rejection_reason": reason,
        "rejection_text": REJECTION_TEXT.get(reason, reason) if reason else None,
        "started": started.date().isoformat() if started else None,
        "decided": decided.date().isoformat() if decided else None,
        "days_to_decision": (decided - started).days if started and decided else None,
        "final": {
            "property_price": r2(application.get("final_property_price_eur") or 0),
            "loan": r2(application.get("final_requested_loan_eur") or 0),
            "equity": r2(application.get("final_equity_amount_eur") or 0),
            "collateral_value": r2(application.get("final_collateral_value_eur") or 0),
            "required_monthly_income": r2(
                application.get("required_monthly_income_eur") or 0
            ),
            "loan_to_value": round(application.get("final_loan_to_value") or 0, 4),
        },
        "properties_considered": len(props),
        "contacts": sum(e["event_type"] == "customer_contact" for e in events),
        "expenses": expenses,
        "steps": steps,
    }


def deposit_saved_estimate(txns, today=None):
    """Balance now plus net money moved into investments over the data."""
    today = today or AS_OF
    invested = 0.0
    for t in txns:
        if t.date > today:
            continue
        if t.category == "Invest Deposit":
            invested += -t.amount
        elif t.category == "Invest Withdraw":
            invested -= t.amount
    return max(0.0, current_balance(txns)) + max(0.0, invested)


def home_readiness(txns, application=None, events=(), today=None, feats=None):
    """Home-buying readiness: real application outcome + affordability.

    Returns ``{"has_application","decision","max_property_price",
    "deposit_needed","deposit_saved_estimate","months_to_deposit","verdict",
    "max_loan","max_payment","application": timeline-or-None}``.
    """
    f = feats or features(txns, today)
    est = affordability(
        f["income"],
        f["income"] - f["spend"],
        deposit_saved_estimate(txns, today),
    )
    timeline = mortgage_timeline(application, list(events)) if application else None
    decision = timeline["decision"] if timeline else None
    if timeline and decision == "approved":
        fin = timeline["final"]
        verdict = (
            f"Your mortgage was approved on {timeline['decided']}: "
            f"{_eur(fin['loan'])} towards a {_eur(fin['property_price'])} home "
            f"with {_eur(fin['equity'])} of your own money."
        )
    elif timeline:
        verdict = (
            f"Your application was declined"
            f"{' on ' + timeline['decided'] if timeline['decided'] else ''}"
            f" because {timeline['rejection_text'] or 'of the bank assessment'}."
            f" Based on your income you could aim for about "
            f"{_eur(est['max_property_price'])}."
        )
    elif est["months_to_deposit"] == 0:
        verdict = (
            f"You already have the ~{_eur(est['deposit_needed'])} deposit for a "
            f"home up to about {_eur(est['max_property_price'])}."
        )
    elif est["months_to_deposit"] is not None:
        years = est["months_to_deposit"] / 12
        when = (
            f"{est['months_to_deposit']} months"
            if years < 2
            else f"about {years:.0f} years"
        )
        verdict = (
            f"A home up to about {_eur(est['max_property_price'])} looks "
            f"affordable. At your current savings pace the "
            f"{_eur(est['deposit_needed'])} deposit takes {when}."
        )
    else:
        verdict = (
            "Right now spending outpaces income, so a deposit is out of reach. "
            "Freeing up even €100 a month gets the clock started."
        )
    return {
        "has_application": bool(timeline),
        "decision": decision,
        **{
            k: est[k]
            for k in (
                "max_property_price",
                "deposit_needed",
                "deposit_saved_estimate",
                "months_to_deposit",
            )
        },
        "verdict": verdict,
        "max_loan": est["max_loan"],
        "max_payment": est["max_payment"],
        "application": timeline,
    }


# --- Everything for the dashboard ---------------------------------------------


def profile_summary(txns, today=None):
    """Compact per-customer numbers stored in ``CustomerProfile``."""
    f = features(txns, today)
    key, score = assign_persona(f)
    return {
        "persona_key": key,
        "persona_label": PERSONAS[key]["label"],
        "persona_score": round(score, 4),
        "monthly_income": r2(f["income"]),
        "monthly_spend": r2(f["spend"]),
        "savings_rate": f["savings_rate"],
        "balance": f["balance_now"],
        "leakage_share": f["leakage_share"],
        "invest_monthly": f["invest_monthly"],
        "balance_volatility": f["balance_volatility"],
        "min_balance": f["balance_min"],
        "tx_count": f["tx_count"],
    }


def overview(txns, application=None, events=(), today=None):
    """The dashboard payload (everything except the ``customer`` summary)."""
    today = today or AS_OF
    txns = prepare(txns)
    f = features(txns, today)
    head = summary(txns, today)
    return {
        "as_of": today.isoformat(),
        "balance": head["balance"],
        "income_monthly_avg": head["income_monthly_avg"],
        "spend_monthly_avg": head["spend_monthly_avg"],
        "savings_rate": head["savings_rate"],
        "baskets": basket_breakdown(txns, today),
        "last_month": last_month_summary(txns, today),
        "monthly_cashflow": monthly_cashflow(txns, today),
        "safe_to_spend": safe_to_spend(txns, today),
        "persona": persona(txns, today, f),
        "insights": insights(txns, today, f),
        "home_readiness": home_readiness(txns, application, events, today, f),
    }
