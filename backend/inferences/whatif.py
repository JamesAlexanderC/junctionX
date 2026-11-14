"""What-ifs (context.md #24 to #27).

The frontend slider recomputes #24 and #26 locally with the same formulas.
"""

from __future__ import annotations

import math

import pandas as pd

from . import models
from . import thresholds as th
from .common import full_months, iso, prepare, r2, spend, to_date

# Copy this into the React slider card verbatim (P1.4 / P3.4).
SIMULATE_CUT_FORMULA = """\
// #24 cut a category by p (0..1); monthlySpend = mean of the last 3 full months
monthlySaving = p * monthlySpend
yearlySaving  = monthlySaving * 12
// #26 goal date; rate = median monthly Saver amount + monthlySaving
months = remaining <= 0 ? 0 : (rate <= 0 ? null : Math.ceil(remaining / rate))
// remaining = target - saved; months === null -> "Not reachable at the current pace"
goalDate = addMonths(today, months)
"""


def category_means(df: pd.DataFrame, today) -> dict:
    """Mean monthly spend per category over the last 3 full months (#24)."""
    df = prepare(df, today)
    months = full_months(today, th.WINDOW_FULL_MONTHS, df)
    if not months:
        return {}
    s = spend(df)
    s = s[s["month"].isin(months)]
    sums = s.groupby("category")["amount"].sum() / len(months)
    return {str(c): r2(v) for c, v in sums.sort_values(ascending=False).items()}


def simulate_cut(monthly_spend: float, p: float) -> dict:
    """#24: monthly saving = p x mean monthly spend; yearly = x 12."""
    monthly = p * (monthly_spend or 0.0)
    return {"monthly_saving": r2(monthly), "yearly_saving": r2(monthly * 12)}


def drop_subscription(amount: float, median_gap_days: float) -> float:
    """#25: yearly saving = amount x (365 / median gap in days)."""
    return r2(amount * 365 / (median_gap_days or 30))


def goal_date(target: float, saved: float, rate: float, today, extra=0.0) -> dict:
    """#26: months = ceil((target - saved) / r), r = Saver rate + extra (#24)."""
    r = (rate or 0.0) + (extra or 0.0)
    months = models.months_to_goal(target, saved, r)
    if months is None:
        return {
            "months": None,
            "date": None,
            "reachable": False,
            "text": "Not reachable at the current pace",
        }
    when = pd.Timestamp(to_date(today)) + pd.DateOffset(months=months)
    return {
        "months": months,
        "date": iso(when),
        "reachable": True,
        "text": f"{months} months",
    }


def habit_translation(category: str, total: float) -> dict | None:
    """#27: count = floor(total / reference price); first reference (most
    expensive first) whose count is between 1 and 10."""
    for name, price in th.HABIT_REFERENCES:
        count = math.floor(total / price) if price else 0
        if 1 <= count <= 10:
            return {"category": category, "count": count, "reference": name}
    return None


def compute_whatif(df: pd.DataFrame, today, income: dict, baskets: dict) -> dict:
    """profile["whatif"] (#24 to #27)."""
    subs = income.get("subscriptions", [])
    translations = [
        habit_translation(c["category"], c["monthly_total"])
        for c in baskets.get("leaky_categories", [])
    ]
    return {
        "category_means": category_means(df, today),
        "subscription_savings": [
            {
                "merchant_id": s["merchant_id"],
                "name": s["name"],
                "yearly_saving": drop_subscription(s["amount"], s["median_gap_days"]),
            }
            for s in subs
        ],
        "habit_translation": [t for t in translations if t],
        "formula": SIMULATE_CUT_FORMULA,
    }
