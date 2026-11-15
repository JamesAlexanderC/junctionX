"""Read-only tools: numbers from the profile and the transactions."""

import math
import re

from inferences.common import last_complete_month
from inferences.thresholds import OWN_TRANSFER_TYPES

from ...models import Transaction
from ... import services
from .context import ToolError, _missing, _norm, unavailable

# --- tool implementations --------------------------------------------------


def get_category_spend(ctx, category, month=None):
    """Spend in one category: outflows minus own-account and Saver transfers
    (common.spend), so "salary" or "invest" never count the salary_sweep or
    investment deposits as spending."""
    month = month or last_complete_month(ctx.today)  # F8
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ToolError("month must be YYYY-MM")
    year, mon = (int(x) for x in month.split("-"))
    qs = Transaction.objects.filter(
        customer_id=ctx.customer_id,
        tx_amount_eur__lt=0,
        tx_date__year=year,
        tx_date__month=mon,
    )
    rows = [
        t
        for t in qs
        if _norm(category) in _norm(t.category)
        and (t.transaction_type or "").lower() not in OWN_TRANSFER_TYPES
    ]
    if not rows:
        return {
            **unavailable(f"No spending in '{category}' in {month}."),
            "found": False,
            "category": category,
            "month": month,
        }
    total = round(sum(-t.tx_amount_eur for t in rows), 2)
    return {
        "available": True,
        "found": True,
        "category": category,
        "month": month,
        "total": total,
        "count": len(rows),
    }


def get_safe_to_spend(ctx):
    p = ctx.profile
    fc, payday = p.get("forecast", {}), p.get("income", {}).get("payday", {})
    next_payday = payday.get("next_payday")
    if fc.get("safe_to_spend_week") is None:
        return unavailable("Safe to spend could not be computed from the data.")
    bills = [
        b
        for b in fc.get("upcoming_bills", [])
        if not next_payday or b["date"] <= next_payday
    ]
    return {
        "safe_to_spend_week": fc.get("safe_to_spend_week"),
        "balance": p.get("balance"),
        "buffer": fc.get("buffer"),
        "payday_found": payday.get("found", False),
        "next_payday": next_payday,
        "days_to_payday": payday.get("days_to_payday"),
        "bills_before_payday": bills,
        "monthly_saving_planned": p.get("baskets", {}).get("monthly_saving"),
    }


def get_safe_to_save(ctx):
    fc = ctx.profile.get("forecast", {})
    if fc.get("safe_to_save_today") is None:
        return unavailable("Safe to save could not be computed from the data.")
    return {
        "safe_to_save_today": fc.get("safe_to_save_today"),
        "danger_days": fc.get("danger_days", []),
        "buffer": fc.get("buffer"),
    }


def get_baskets(ctx):
    baskets = ctx.profile.get("baskets") or {}
    if not any((baskets.get("totals") or {}).values()):
        return unavailable("No spending found for the latest month.")
    return baskets


def level_card(levels):
    """level_progress card for the level the user is working towards (#28-#33).

    At the top level it shows the level reached, at 100 %. Levels are climbed
    in order, so the ladder marks only levels up to the current one as
    reached: a later level whose own test passes (e.g. mortgage readiness)
    stays open until the levels below it are reached.
    """
    current = levels["current"]
    nxt = levels.get("next")
    step = levels.get("easiest_next_step") or {}
    # FC-7: show where the user is, and clamp progress (it can come out < 0).
    progress = min(1.0, max(0.0, float(levels.get("progress", 1.0) or 0.0)))
    card = {
        "type": "level_progress",
        "level": nxt or current,
        "name": levels.get("next_name") or levels.get("current_name"),
        "current_level": current,
        "current_name": levels.get("current_name"),
        "progress": progress,
        "euros_to_go": levels.get("euros_to_go"),
        "next_step": step.get("text"),
        # What the next level needs, with the customer's own numbers.
        "requirement": levels.get("next_requirement") if nxt else None,
        "ladder": [
            {"level": r["level"], "name": r["name"], "reached": r["level"] <= current}
            for r in levels.get("ladder") or []
        ],
    }
    return {k: v for k, v in card.items() if v not in (None, [])}


def get_level(ctx):
    levels = ctx.profile.get("levels") or {}
    if levels.get("current") is None:
        return unavailable("Levels could not be computed from the data.")
    return {**levels, "card": level_card(levels)}


def simulate_cut(ctx, category, pct, goal_id=None):
    """#24 cut a category by pct; #26 goal date before/after."""
    if pct > 1:
        pct = pct / 100
    if not 0 <= pct <= 1:
        raise ToolError("pct must be between 0 and 1")
    means = ctx.profile.get("whatif", {}).get("category_means", {})
    match = next(
        (
            c
            for c in means
            if _norm(category) in _norm(c) or _norm(c) in _norm(category)
        ),
        None,
    )
    if match is None:
        return {
            **unavailable(f"No recent spending in '{category}' to cut."),
            "found": False,
            "category": category,
        }
    monthly_spend = means[match]
    monthly = round(pct * monthly_spend, 2)
    out = {
        "found": True,
        "category": match,
        "pct": pct,
        "monthly_spend": monthly_spend,
        "monthly_saving": monthly,
        "yearly_saving": round(monthly * 12, 2),
    }
    goals = ctx.profile.get("goals", {}).get("active", [])
    goal = next((g for g in goals if g["id"] == goal_id), None)
    if goal_id is not None and goal is None:
        out["goal"] = {"found": False}
    elif goal is not None:
        rate = float(ctx.profile.get("baskets", {}).get("monthly_saving") or 0)
        remaining = float(goal["target"]) - float(goal["saved"])
        before = math.ceil(remaining / rate) if rate > 0 else None
        after = math.ceil(remaining / (rate + monthly)) if rate + monthly > 0 else None
        out["goal"] = {
            "id": goal["id"],
            "name": goal["name"],
            "target": goal["target"],
            "saved": goal["saved"],
            "monthly_rate": rate,
            "months_before": before,
            "months_after": after,
            "months_sooner": (before - after) if before and after else None,
        }
    return out


def forecast_balance(ctx):
    fc = ctx.profile.get("forecast", {})
    if _missing(fc.get("end_of_month")):
        return unavailable("The balance forecast could not be computed.")
    return {
        "balance": ctx.profile.get("balance"),
        "end_of_month": fc.get("end_of_month"),
        "danger_days": fc.get("danger_days", []),
        "upcoming_bills": fc.get("upcoming_bills", []),
        "seasonal": fc.get("seasonal"),
    }


def get_spender_type(ctx):
    habits = ctx.profile.get("habits") or {}
    if not (habits.get("spender_type") or {}).get("label"):
        return unavailable("Not enough spending to tell a spender type.")
    return habits


def get_mortgage_readiness(ctx):
    m = dict(ctx.profile.get("mortgage", {}))
    if (m.get("readiness") or {}).get("score") is None:
        return unavailable(
            "The mortgage readiness model has not been fitted on the mortgage "
            "files (run manage.py build_artifacts)."
        )
    m["loan_details_entered"] = services.latest_loan(ctx.customer_id) is not None
    m["note"] = "Guidance only, not a loan decision."
    return m


TIGHT_DAYS_TEXT = (
    "Days when your balance could drop below EUR 50: before your next payday, or "
    "in the next 30 days when no payday is found."
)

SURPRISES_TEXT = (
    "Surprises are must-pay costs that come irregularly, like a car repair or "
    "the dentist. They are not the same as an unusual charge, which is one "
    "payment much bigger than usual at a shop."
)

EXPLAINERS = {
    # FC-7: tight days are below EUR 50, not below the buffer.
    "danger days": (
        TIGHT_DAYS_TEXT,
        lambda p: {"value": len(p.get("forecast", {}).get("danger_days") or [])},
    ),
    "tight days": (
        TIGHT_DAYS_TEXT,
        lambda p: {"value": len(p.get("forecast", {}).get("danger_days") or [])},
    ),
    "safe to spend": (
        "What you can spend this week without touching bills, savings or your "
        "buffer.",
        lambda p: {"value": p.get("forecast", {}).get("safe_to_spend_week")},
    ),
    "buffer": (
        "A small cushion kept aside for surprises: the larger of EUR 50 or 10% of "
        "your monthly essentials.",
        lambda p: {"value": p.get("forecast", {}).get("buffer")},
    ),
    "leaky": (
        "Small everyday spending that slips away, like coffee, snacks, takeaway "
        "and taxis.",
        lambda p: {"value": p.get("baskets", {}).get("totals", {}).get("leaky")},
    ),
    "essentials": (
        "Must-pay regular costs: rent, utilities, insurance, loans, groceries.",
        lambda p: {"value": p.get("baskets", {}).get("monthly_essentials")},
    ),
    # #8 (live test): "unexpected costs" got the unusual-charge alert instead.
    "unexpected costs": (
        SURPRISES_TEXT,
        lambda p: {"value": p.get("forecast", {}).get("surprise_fund_monthly")},
    ),
    "surprises": (
        SURPRISES_TEXT,
        lambda p: {"value": p.get("forecast", {}).get("surprise_fund_monthly")},
    ),
    "saver": (
        "Money you move aside for later: savings, investments and goal pots.",
        lambda p: {"value": p.get("baskets", {}).get("monthly_saving")},
    ),
    "dsti": (
        "Debt service to income: the share of your net income going to loan "
        "payments. Finland's limit is 60% at a 6% stress rate.",
        lambda p: {"value": p.get("mortgage", {}).get("dsti")},
    ),
    "safety net": (
        "Your lowest balance measured in months of essentials. One month or more "
        "means you have a safety net.",
        lambda p: {"value": p.get("levels", {}).get("buffer_months")},
    ),
}


def get_explainer(ctx, term):
    key = next((k for k in EXPLAINERS if k in _norm(term)), None)
    if key is None:
        return {"found": False, "term": term}
    text, numbers = EXPLAINERS[key]
    values = {k: v for k, v in numbers(ctx.profile).items() if v is not None}
    return {"found": True, "term": key, "text": text, **values}


def get_benchmark(ctx, kind, category=None):
    rows = ctx.profile.get("benchmarks", {}).get(kind, [])
    if category:
        rows = [r for r in rows if _norm(category) in _norm(r["category"])]
    if not rows:
        return unavailable(
            "No peer group of at least 20 customers to compare with.", kind=kind
        )
    return {
        "kind": kind,
        "rows": rows,
        "source": ctx.profile.get("benchmarks", {}).get("source"),
    }
