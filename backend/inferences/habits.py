"""Habits and spender type (context.md #11 to #16).

Window: the last 3 full months of spend (outflows excluding own transfers).
"""

from __future__ import annotations

import pandas as pd

from . import models
from . import thresholds as th
from .common import essential_mask, full_months, prepare, r2, safe_div, spend


def _window(df: pd.DataFrame, today):
    months = full_months(today, th.WINDOW_FULL_MONTHS, df)
    s = spend(df)
    return s[s["month"].isin(months)], max(1, len(months))


def weekend(s: pd.DataFrame) -> dict:
    """#11: weekend share = Sat + Sun spend / total; flag above 43%."""
    total = s["amount"].sum()
    wk = s[s["tx_date"].dt.day_of_week >= 5]["amount"].sum()
    share = safe_div(wk, total)
    return {"share": r2(share), "flag": bool(share > th.WEEKEND_FLAG_SHARE)}


def night(s: pd.DataFrame) -> dict:
    """#12: night share = spend 22:00 to 05:00 / total; flag above 15%."""
    hours = s["tx_timestamp"].dt.hour
    is_night = (hours >= th.NIGHT_START_HOUR) | (hours < th.NIGHT_END_HOUR)
    share = safe_div(s[is_night]["amount"].sum(), s["amount"].sum())
    return {"share": r2(share), "flag": bool(share > th.NIGHT_FLAG_SHARE)}


def _leaky(s: pd.DataFrame) -> pd.DataFrame:
    """Leaky purchases (#9): non-essential and under EUR 25."""
    return s[~essential_mask(s) & (s["amount"] < th.LEAKY_MAX_EUR)]


def impulse(df: pd.DataFrame, today, months: int | None = None) -> dict:
    """#13: bursts of >= 3 leaky purchases within 60 minutes, per month."""
    if months is None:
        s, months = _window(df, today)
    else:
        s = spend(df)
    bursts = models.count_bursts(_leaky(s)["tx_timestamp"])
    per_month = bursts / months
    return {
        "bursts_per_month": r2(per_month),
        "flag": bool(per_month >= th.IMPULSE_FLAG_BURSTS),
    }


def payday_splurge(s: pd.DataFrame, payday_dates, start, end) -> dict:
    """#14: mean daily non-essential spend in days 0-3 after payday / mean
    daily non-essential spend in the rest of the cycle. Flag above 1.4."""
    paydays = sorted(pd.to_datetime(list(payday_dates or [])))
    if not paydays:
        return {"ratio": None, "flag": False}
    ne = s[~essential_mask(s)]
    daily = ne.groupby("tx_date")["amount"].sum()
    days = pd.date_range(max(pd.Timestamp(start), paydays[0]), pd.Timestamp(end))
    near, rest = [], []
    for d in days:
        last = max(p for p in paydays if p <= d)
        value = float(daily.get(d, 0.0))
        (near if (d - last).days <= th.PAYDAY_SPLURGE_DAYS else rest).append(value)
    if not near or not rest:
        return {"ratio": None, "flag": False}
    mean_rest = sum(rest) / len(rest)
    ratio = safe_div(sum(near) / len(near), mean_rest, default=None)
    if ratio is None:
        return {"ratio": None, "flag": False}
    return {"ratio": r2(ratio), "flag": bool(ratio > th.PAYDAY_SPLURGE_FLAG)}


def loyalty(s: pd.DataFrame, months: int) -> dict:
    """#15: HHI of merchant spend shares; Loyal > 0.15, Explorer when > 25
    unique merchants a month and HHI < 0.05. Also the top-3 merchants' share."""
    by_merchant = s.groupby("merchant_id")["amount"].sum().sort_values(ascending=False)
    h = models.hhi(by_merchant.values)
    unique_pm = safe_div(s.groupby("month")["merchant_id"].nunique().sum(), months)
    if h > th.LOYAL_HHI:
        label = "Loyal"
    elif unique_pm > th.EXPLORER_MERCHANTS_PER_MONTH and h < th.EXPLORER_HHI:
        label = "Explorer"
    else:
        label = "Mixed"
    top3 = safe_div(by_merchant.head(3).sum(), by_merchant.sum())
    return {
        "hhi": r2(h),
        "label": label,
        "top3_share": r2(top3),
        "unique_merchants_per_month": r2(unique_pm),
    }


TRAIT_LABELS = {
    "weekend": "Weekend Treater",
    "night": "Night Owl",
    "impulse": "Impulse Buyer",
    "payday": "Payday Splurger",
}


def spender_type(wk, nt, imp, pay, saver_share: float) -> dict:
    """#16: each trait scored value / flag threshold, capped at 1. Label = the
    highest trait; Steady Planner when all < 0.5 and Saver share > 10%."""
    scores = {
        "weekend": min(1.0, safe_div(wk["share"] or 0, th.WEEKEND_FLAG_SHARE)),
        "night": min(1.0, safe_div(nt["share"] or 0, th.NIGHT_FLAG_SHARE)),
        "impulse": min(
            1.0, safe_div(imp["bursts_per_month"] or 0, th.IMPULSE_FLAG_BURSTS)
        ),
        "payday": min(1.0, safe_div(pay["ratio"] or 0, th.PAYDAY_SPLURGE_FLAG)),
    }
    if (
        all(v < th.STEADY_PLANNER_MAX_SCORE for v in scores.values())
        and saver_share > th.STEADY_PLANNER_SAVER_SHARE
    ):
        label = "Steady Planner"
    else:
        label = TRAIT_LABELS[max(scores, key=scores.get)]
    return {"label": label, "scores": {k: r2(v) for k, v in scores.items()}}


def compute_habits(df: pd.DataFrame, today, income: dict, baskets: dict) -> dict:
    """profile["habits"] (#11 to #16)."""
    df = prepare(df, today)
    s, months = _window(df, today)
    window_months = full_months(today, th.WINDOW_FULL_MONTHS, df)
    wk, nt = weekend(s), night(s)
    imp = impulse(df, today)
    if window_months:
        start = pd.Period(window_months[0], freq="M").start_time
        end = pd.Period(window_months[-1], freq="M").end_time.normalize()
        pay = payday_splurge(
            s, income.get("payday", {}).get("payday_dates"), start, end
        )
    else:
        pay = {"ratio": None, "flag": False}
    # Saver share of total outflow over the window (#10, #75).
    hist = [h for h in baskets.get("history", []) if h["month"] in window_months]
    saver = sum(h["totals"].get("saver", 0) for h in hist)
    total = sum(sum(h["totals"].values()) for h in hist)
    return {
        "weekend": wk,
        "night": nt,
        "impulse": imp,
        "payday_splurge": pay,
        "loyalty": loyalty(s, months),
        "spender_type": spender_type(wk, nt, imp, pay, safe_div(saver, total)),
    }
