"""LLM-callable tools over one customer's banking data.

Each tool wraps :mod:`finance.analytics` and returns::

    {
        "data": {...},          # compact JSON the model (or offline coach) reads
        "chart": {...} | None,  # chart event payload (see docs/design.md)
        "concept": {...} | None,  # {"title","text"} glossary explainer
        "label": "Checking your transactions…",  # tool status line
    }

The same registry backs Gemini function calling (:func:`declarations`) and
the offline coach (:func:`run_tool`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from finance import analytics as a

from . import vocab
from .glossary import concept

log = logging.getLogger(__name__)

PERIOD_HELP = (
    "Time window: last_month, this_month, last_3_months, last_6_months, "
    "last_12_months, all, or a month as YYYY-MM (e.g. 2026-08). 'Today' is "
    "2026-09-30, so last_month is September 2026."
)
TARGET_HELP = (
    "A spending category (Housing, Utilities, Groceries, Health, Home & Tech, "
    "Travel, Restaurants, Entertainment, Lifestyle, Transportation), 'Taxi', "
    "or a basket key (mandatory_regular, mandatory_irregular, leakage). "
    "Everyday words like 'dining out' are understood too."
)
PERIODS = {
    "last_month",
    "this_month",
    "last_3_months",
    "last_6_months",
    "last_12_months",
    "all",
}
MAX_CHART_POINTS = 8


class ToolError(ValueError):
    """Bad tool arguments; the message is shown to the model."""


class CoachContext:
    """One customer's data plus small caches shared by tool calls."""

    def __init__(self, data, today=None):
        self.data = data
        self.customer_id = data.customer.customer_id
        self.txns = a.prepare(data.txns)
        self.application = data.application
        self.events = list(data.events or [])
        self.today = today or a.AS_OF
        self._cache = {}

    def cached(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def features(self):
        return self.cached("features", lambda: a.features(self.txns, self.today))

    def summary(self):
        return self.cached("summary", lambda: a.summary(self.txns, self.today))

    def baskets(self):
        return self.cached("baskets", lambda: a.basket_breakdown(self.txns, self.today))


@dataclass
class Tool:
    name: str
    description: str
    label: str
    fn: Callable
    properties: dict = field(default_factory=dict)
    required: tuple = ()

    @property
    def schema(self):
        return {
            "type": "object",
            "properties": self.properties,
            "required": list(self.required),
        }


TOOLS: dict[str, Tool] = {}


def tool(name, description, label, properties=None, required=()):
    def register(fn):
        TOOLS[name] = Tool(name, description, label, fn, properties or {}, required)
        return fn

    return register


def declarations():
    """Tool specs as ``[{"name","description","parameters"}]`` (JSON schema)."""
    return [
        {"name": t.name, "description": t.description, "parameters": t.schema}
        for t in TOOLS.values()
    ]


def label_for(name):
    t = TOOLS.get(name)
    return t.label if t else "Checking your transactions…"


def run_tool(ctx, name, args=None):
    """Run a tool safely. Unknown tools or bad arguments return an error."""
    t = TOOLS.get(name)
    if t is None:
        return _result({"error": f"Unknown tool {name!r}"}, label="Thinking…")
    try:
        out = t.fn(ctx, **_clean_args(t, args or {}))
    except ToolError as exc:
        out = {"data": {"error": str(exc)}}
    except Exception:  # noqa: BLE001 - never let a tool kill the chat
        log.exception("Tool %s failed", name)
        out = {"data": {"error": "The calculation failed for this customer."}}
    out["label"] = out.get("label") or t.label
    out.setdefault("chart", None)
    out.setdefault("concept", None)
    return out


def _clean_args(t, args):
    return {k: v for k, v in dict(args).items() if k in t.properties}


def _result(data, chart=None, concept_key=None, label=None):
    return {
        "data": data,
        "chart": chart,
        "concept": concept(concept_key) if concept_key else None,
        "label": label,
    }


# --- Argument helpers ---------------------------------------------------------


def _period(value, default="last_month", today=None):
    if value in (None, ""):
        return default
    text = str(value).strip()
    key = text.lower().replace(" ", "_")
    if key in PERIODS:
        return key
    if len(text) == 7 and text[4] == "-" and text[:4].isdigit():
        return text
    parsed = vocab.find_period(text, today)
    if parsed:
        return parsed
    raise ToolError(f"Unknown period {value!r}. {PERIOD_HELP}")


def _target(value, default=None):
    if value in (None, ""):
        if default:
            return default
        raise ToolError(f"A category is required. {TARGET_HELP}")
    target = vocab.normalize_target(value)
    if target is None:
        raise ToolError(f"Unknown category {value!r}. {TARGET_HELP}")
    return target


def _month_key(value, today):
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 7 and text[4] == "-":
        return text
    months = vocab.find_months(f"in {text}", today)
    if not months:
        raise ToolError(f"Unknown month {value!r}; use YYYY-MM.")
    return months[0]


# --- Chart helpers --------------------------------------------------------------


def chart(kind, title, data, unit="€"):
    rows = [
        {"label": str(d["label"]), "value": round(float(d["value"]), 2)} for d in data
    ]
    if not rows or not any(r["value"] for r in rows):
        return None
    return {"kind": kind, "title": title, "unit": unit, "data": rows}


def _top_with_other(rows, n=MAX_CHART_POINTS - 1):
    rows = [r for r in rows if r["value"] > 0]
    if len(rows) <= n + 1:
        return rows
    other = sum(r["value"] for r in rows[n:])
    return rows[:n] + [{"label": "Other", "value": other}]


def basket_chart(baskets, title="Your money by basket (monthly avg)"):
    return chart(
        "pie",
        title,
        [{"label": b["label"], "value": b["monthly_avg"]} for b in baskets],
    )


def months_chart(kind, title, months, field="amount"):
    return chart(
        kind,
        title,
        [{"label": vocab.month_short(m["month"]), "value": m[field]} for m in months],
    )


# --- Tools ------------------------------------------------------------------------


@tool(
    "get_overview_summary",
    "Headline money picture: 12-month average income and spend, savings rate, "
    "balance, last month's totals, persona, safe-to-spend and the top "
    "insights. Use for 'how am I doing' or general questions.",
    "Looking at your overall picture…",
)
def get_overview_summary(ctx):
    head = ctx.summary()
    last = a.last_month_summary(ctx.txns, ctx.today)
    flow = a.monthly_cashflow(ctx.txns, ctx.today)
    sts = a.safe_to_spend(ctx.txns, ctx.today)
    feats = ctx.features()
    persona = a.persona(ctx.txns, ctx.today, feats)
    data = {
        "as_of": ctx.today.isoformat(),
        **head,
        "monthly_margin": a.r2(head["income_monthly_avg"] - head["spend_monthly_avg"]),
        "last_month": last,
        "last_6_months": flow[-6:],
        "safe_to_spend": {
            k: sts[k] for k in ("amount", "per_day", "next_payday", "days_until_payday")
        },
        "persona": {"label": persona["label"], "traits": persona["traits"]},
        "overdraft_days": feats["overdraft_days"],
        "insights": a.insights(ctx.txns, ctx.today, feats, limit=4),
    }
    return _result(
        data,
        months_chart("bar", "Spending by month", flow[-6:], "spend"),
        "savings_rate",
    )


@tool(
    "spend_by_category",
    "Spending per category for a period, biggest first, with counts and "
    "shares. Optionally pass a category to also get its breakdown by "
    "merchant type (supermarkets, bars, fuel...).",
    "Sorting your spending by category…",
    {
        "period": {"type": "string", "description": PERIOD_HELP},
        "category": {"type": "string", "description": TARGET_HELP},
    },
)
def spend_by_category(ctx, period=None, category=None):
    period = _period(period, today=ctx.today)
    target = _target(category) if category else None
    res = a.spend_by_category(ctx.txns, period, ctx.today)
    data = {k: res[k] for k in ("period", "start", "end", "total")}
    data["categories"] = res["categories"]
    rows = [{"label": c["category"], "value": c["amount"]} for c in res["categories"]]
    out_chart = chart(
        "bar", f"Spending by category, {res['period']}", _top_with_other(rows)
    )
    if target:
        data["focus"] = _focus(ctx, res, target, period)
    return _result(data, out_chart, "three_baskets" if not target else None)


def _focus(ctx, res, target, period):
    """Amount, count and merchant types for one target in a period."""
    if target == vocab.TAXI:
        taxi = a.taxi_stats(ctx.txns, period, ctx.today)
        return {
            "target": target,
            "amount": taxi["total"],
            "count": taxi["rides"],
            "share": round(taxi["total"] / res["total"], 4) if res["total"] else 0.0,
        }
    if target in a.BASKETS:
        rows = [c for c in res["categories"] if c["basket"] == target]
    else:
        rows = [c for c in res["categories"] if c["category"] == target]
    amount = sum(c["amount"] for c in rows)
    focus = {
        "target": target,
        "amount": a.r2(amount),
        "count": sum(c["count"] for c in rows),
        "share": round(amount / res["total"], 4) if res["total"] else 0.0,
    }
    if target in vocab.CATEGORIES:
        types = a.spend_by_merchant_type(ctx.txns, period, target, ctx.today)
        focus["merchant_types"] = [
            {k: t[k] for k in ("label", "amount", "count")} for t in types["types"][:4]
        ]
    return focus


@tool(
    "category_trend",
    "Monthly spend on one category, taxis or a basket over recent months, "
    "with the monthly average and change_pct (last 3 months vs the 3 "
    "before).",
    "Tracing the trend month by month…",
    {
        "category": {"type": "string", "description": TARGET_HELP},
        "months": {
            "type": "integer",
            "description": "How many months back (3-24, default 12).",
        },
    },
    ("category",),
)
def category_trend(ctx, category=None, months=12):
    target = _target(category)
    months = max(3, min(int(months or 12), 24))
    res = a.category_trend(ctx.txns, target, months, ctx.today)
    data = {**res, "display_name": vocab.display(target)}
    title = f"{vocab.display(target).capitalize()} by month"
    return _result(data, months_chart("bar", title, res["months"]))


@tool(
    "taxi_stats",
    "Taxi and ride-hailing (MCC 4121) rides and spend for a period, the "
    "average per ride, a 6-month monthly trend and the 12-month monthly "
    "average. Also the wider Transportation spend for the period.",
    "Counting your taxi rides…",
    {"period": {"type": "string", "description": PERIOD_HELP}},
)
def taxi_stats(ctx, period=None):
    period = _period(period, today=ctx.today)
    res = a.taxi_stats(ctx.txns, period, ctx.today)
    transport = a.spend_by_merchant_type(ctx.txns, period, "Transportation", ctx.today)
    data = {
        **res,
        "transport_total": transport["total"],
        "transport_types": [
            {k: t[k] for k in ("label", "amount", "count")}
            for t in transport["types"][:4]
        ],
    }
    return _result(data, months_chart("bar", "Taxi spend by month", res["monthly"]))


@tool(
    "what_if",
    "Project the saving from cutting a category, taxis or a basket by a "
    "percentage, compounded at 3% a year. Also returns the customer's "
    "current monthly margin (income minus spend).",
    "Running the numbers on your what-if…",
    {
        "target": {"type": "string", "description": TARGET_HELP},
        "pct": {"type": "number", "description": "Cut in percent, 1-100."},
        "years": {"type": "integer", "description": "Years to project (1-30)."},
    },
    ("target", "pct"),
)
def what_if(ctx, target=None, pct=20, years=5):
    target = _target(target)
    try:
        pct = float(pct if pct is not None else 20)
        years = int(years or 5)
    except (TypeError, ValueError):
        raise ToolError("pct must be a number and years an integer.")
    if not 0 < pct <= 100:
        raise ToolError("pct must be between 1 and 100.")
    res = a.what_if(ctx.txns, target, pct, years, ctx.today)
    head = ctx.summary()
    margin = a.r2(head["income_monthly_avg"] - head["spend_monthly_avg"])
    data = {
        **res,
        "display_name": vocab.display(target),
        "interest_rate": a.SAVINGS_INTEREST,
        "monthly_margin": margin,
    }
    points = [{"label": "Now", "value": 0}] + [
        {"label": f"Year {p['year']}", "value": p["with_interest"]}
        for p in res["projection"]
    ]
    title = f"Saved by cutting {vocab.display(target)} {pct:g}%"
    return _result(data, chart("line", title, points), "compound_interest")


@tool(
    "safe_to_spend",
    "How much the customer can safely spend until next payday: balance minus "
    "upcoming bills and a reserve, per day and for the next 7 days, plus "
    "their typical everyday spend per day.",
    "Checking upcoming bills and payday…",
)
def safe_to_spend(ctx):
    res = a.safe_to_spend(ctx.txns, ctx.today)
    week_days = min(7, res["days_until_payday"])
    bills = a.r2(sum(b["amount"] for b in res["upcoming_bills"]))
    data = {
        **res,
        "week_amount": a.r2(res["per_day"] * week_days),
        "week_days": week_days,
        "bills_total": bills,
        "shortfall": a.r2(max(0.0, bills + res["reserve"] - res["balance"])),
        "spend_monthly_avg": ctx.summary()["spend_monthly_avg"],
        "as_of": ctx.today.isoformat(),
    }
    if res["amount"] > 0:
        out_chart = chart(
            "pie",
            f"Your {vocab.eur(res['balance'])} balance until payday",
            [
                {"label": "Bills before payday", "value": bills},
                {"label": "Safety reserve", "value": res["reserve"]},
                {"label": "Safe to spend", "value": res["amount"]},
            ],
        )
    else:
        out_chart = chart(
            "bar",
            "Before payday",
            [
                {"label": "Balance", "value": max(0.0, res["balance"])},
                {"label": "Bills due", "value": bills},
                {"label": "Reserve", "value": res["reserve"]},
            ],
        )
    return _result(data, out_chart, "safe_to_spend")


@tool(
    "compare_months",
    "Compare spending per category between two months (YYYY-MM). Defaults "
    "to the two most recent months.",
    "Comparing the two months…",
    {
        "month_a": {"type": "string", "description": "Earlier month, YYYY-MM."},
        "month_b": {"type": "string", "description": "Later month, YYYY-MM."},
    },
)
def compare_months(ctx, month_a=None, month_b=None):
    keys = a.last_months(ctx.today, 2)
    a_key = _month_key(month_a, ctx.today) or keys[0]
    b_key = _month_key(month_b, ctx.today) or keys[1]
    if a_key > b_key:
        a_key, b_key = b_key, a_key
    res = a.compare_months(ctx.txns, a_key, b_key, ctx.today)
    rows = [c for c in res["categories"] if abs(c["diff"]) >= 1][:6]
    data = {**res, "categories": rows}
    title = (
        f"Change by category, {vocab.month_short(a_key)} → "
        f"{vocab.month_short(b_key)}"
    )
    out_chart = chart(
        "bar", title, [{"label": r["category"], "value": r["diff"]} for r in rows]
    )
    return _result(data, out_chart)


@tool(
    "biggest_expenses",
    "The largest single payments in a period with date, category, merchant "
    "type and basket.",
    "Finding your biggest payments…",
    {
        "period": {"type": "string", "description": PERIOD_HELP},
        "n": {"type": "integer", "description": "How many (1-10, default 5)."},
    },
)
def biggest_expenses(ctx, period=None, n=5):
    period = _period(period, today=ctx.today)
    n = max(1, min(int(n or 5), 10))
    res = a.biggest_expenses(ctx.txns, period, n, ctx.today)
    for item in res["items"]:
        item["basket_label"] = a.BASKETS.get(item["basket"])
        item.pop("merchant_id", None)
    out_chart = chart(
        "bar",
        f"Biggest payments, {res['period']}",
        [
            {
                "label": f"{vocab.day_label(i['date'])} {i['category']}",
                "value": i["amount"],
            }
            for i in res["items"]
        ],
    )
    return _result(res, out_chart)


@tool(
    "get_persona",
    "The customer's spender persona (Steady Saver, Weekend Spender, "
    "Paycheck-to-Paycheck, Investor, Comfortable, Balanced Budgeter) with "
    "the behavioural signals behind it.",
    "Working out your spending style…",
)
def get_persona(ctx):
    feats = ctx.features()
    persona = a.persona(ctx.txns, ctx.today, feats)
    signals = {
        k: feats[k]
        for k in (
            "income",
            "spend",
            "savings_rate",
            "leakage_share",
            "weekend_leakage_share",
            "invest_monthly",
            "balance_avg",
            "balance_min",
            "overdraft_days",
            "cushion_months",
        )
    }
    signals["income"] = a.r2(signals["income"])
    signals["spend"] = a.r2(signals["spend"])
    persona.pop("score", None)
    flow = a.monthly_cashflow(ctx.txns, ctx.today)[-6:]
    data = {**persona, "signals": signals, "last_6_months": flow}
    return _result(
        data,
        months_chart("bar", "Money left over each month", flow, "net"),
        "savings_rate",
    )


@tool(
    "home_readiness",
    "Home-buying readiness: an affordability estimate (Finnish rules: 10% "
    "deposit, payment <= 35% of income stress-tested at 6% over 25 years) "
    "and, if the customer applied for a mortgage, the real application "
    "outcome and timeline.",
    "Checking your home-buying readiness…",
)
def home_readiness(ctx):
    feats = ctx.features()
    res = a.home_readiness(ctx.txns, ctx.application, ctx.events, ctx.today, feats)
    app = res.pop("application")
    if app:
        steps = app.pop("steps", [])
        app["timeline"] = [
            {"date": s["date"], "event": s["event_type"]} for s in steps[:12]
        ]
        app["expenses"] = app.get("expenses", [])[:5]
        loan = app["final"]["loan"]
        app["stress_payment"] = a.r2(a.annuity_payment(loan)) if loan else 0.0
    data = {
        **res,
        "application": app,
        "monthly_margin": a.r2(feats["income"] - feats["spend"]),
        "income_monthly_avg": a.r2(feats["income"]),
        "spend_monthly_avg": a.r2(feats["spend"]),
    }
    if app:
        fin = app["final"]
        out_chart = chart(
            "bar",
            "Your mortgage deal",
            [
                {"label": "Home price", "value": fin["property_price"]},
                {"label": "Loan", "value": fin["loan"]},
                {"label": "Own money", "value": fin["equity"]},
            ],
        )
    else:
        out_chart = chart(
            "bar",
            "Deposit: needed vs saved",
            [
                {"label": "Deposit needed", "value": res["deposit_needed"]},
                {"label": "Saved so far", "value": res["deposit_saved_estimate"]},
            ],
        )
    return _result(data, out_chart, "ltv" if app else "stress_test")


@tool(
    "basket_breakdown",
    "Monthly average spend in the three baskets (must-pay bills, surprise "
    "essentials, everyday leakage) over the last 12 months with top "
    "categories, plus last month's basket totals.",
    "Sorting your spending into baskets…",
)
def basket_breakdown(ctx):
    baskets = ctx.baskets()
    last = a.last_month_summary(ctx.txns, ctx.today)
    head = ctx.summary()
    data = {
        "baskets": baskets,
        "last_month": last,
        "spend_monthly_avg": head["spend_monthly_avg"],
        "income_monthly_avg": head["income_monthly_avg"],
    }
    return _result(data, basket_chart(baskets), "three_baskets")
