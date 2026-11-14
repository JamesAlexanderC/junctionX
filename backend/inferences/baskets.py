"""Baskets (context.md #7 to #10, plus #75 Saver).

Every outflow lands in one basket: essential, surprise, leaky, saver, or
other (non-essential and EUR 25 or more, which the doc's four baskets leave
out). Shares are basket total / total outflow x 100.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import models
from . import thresholds as th
from .common import (
    add_months,
    essential_mask,
    full_months,
    internal_mask,
    month_key,
    neutral_mask,
    outflows,
    prepare,
    r2,
    saver_mask,
)

BASKETS = ("essential", "surprise", "leaky", "saver", "other")


def _is_surprise(amount: float, history: list[float]) -> bool:
    """#8: amount > Q3 + 1.5 IQR of the category history, or > 3 x the
    category median with fewer than 8 past payments. With no history at all,
    above SURPRISE_NO_HISTORY_MIN_EUR (our rule, the doc has none)."""
    if len(history) >= th.SURPRISE_MIN_HISTORY:
        return amount > models.iqr_upper_fence(history)
    if history:
        return amount > th.SURPRISE_MEDIAN_MULT * float(np.median(history))
    return amount > th.SURPRISE_NO_HISTORY_MIN_EUR


def _basket_flows(df: pd.DataFrame) -> pd.DataFrame:
    """Outflows minus neutral sweeps, plus Saver withdrawals as negative amounts.

    salary_sweep is neutral (P1.1 decision). An investment withdrawal is a
    negative Saver flow, so the Saver total is net of withdrawals (#94).
    """
    neutral = neutral_mask(df)
    outs = outflows(df[~neutral])
    back = df[(df["tx_amount_eur"] > 0) & saver_mask(df)].copy()
    back["amount"] = -back["tx_amount_eur"]
    return pd.concat([outs, back]).sort_values("tx_timestamp", kind="stable")


def classify(df: pd.DataFrame, today, bills: list[dict] | None = None):
    """Outflows up to today with a `basket` column (#7, #8, #9, #75).

    bills: output of income.regular_bills; recurring bills are never Surprises.
    """
    df = prepare(df, today)
    outs = _basket_flows(df)
    if not len(outs):
        outs["basket"] = pd.Series(dtype=str)
        return outs
    saver = (saver_mask(df) | internal_mask(df)).loc[outs.index]
    if bills is None:
        from .income import regular_bills

        bills = regular_bills(df, today)
    bill_merchants = {b["merchant_id"] for b in bills}
    essential_cat = essential_mask(outs)
    history: dict[str, list[float]] = {}
    labels = []
    for idx, row in outs.iterrows():
        if saver.loc[idx]:
            labels.append("saver")  # #75
        elif essential_cat.loc[idx]:
            past = history.setdefault(row["category"], [])
            recurring = row["merchant_id"] in bill_merchants
            if not recurring and _is_surprise(row["amount"], past):
                labels.append("surprise")  # #8
            else:
                labels.append("essential")  # #7
            past.append(row["amount"])
        elif row["amount"] < th.LEAKY_MAX_EUR:
            labels.append("leaky")  # #9
        else:
            labels.append("other")
    outs["basket"] = labels
    return outs


def basket_split(classified: pd.DataFrame, month: str) -> dict:
    """#10 for one month: totals and shares (% of total outflow, 1 dp)."""
    m = classified[classified["month"] == month] if len(classified) else classified
    sums = m.groupby("basket")["amount"].sum() if len(m) else {}
    totals = {b: r2(float(sums.get(b, 0.0)) if len(m) else 0.0) for b in BASKETS}
    total = sum(totals.values())
    shares = {
        b: round(models.share(v, total) * 100, 1) if total else 0.0
        for b, v in totals.items()
    }
    return {"month": month, "totals": totals, "shares": shares}


def compute_baskets(df: pd.DataFrame, today, bills: list[dict] | None = None):
    """profile["baskets"] (#7 to #10, #75) for today's month."""
    cls = classify(df, today, bills)
    prepared = prepare(df, today)
    current = month_key(today)
    split = basket_split(cls, current)
    prev = [add_months(current, -k) for k in range(th.BASKET_TREND_MONTHS, 0, -1)]
    prev_splits = [basket_split(cls, m) for m in prev]
    trend = {
        b: round(
            split["shares"][b] - float(np.mean([p["shares"][b] for p in prev_splits])),
            1,
        )
        for b in BASKETS
    }
    window = full_months(today, th.WINDOW_FULL_MONTHS, prepared)
    hist_months = full_months(today, 6, prepared)
    history = [
        {"month": m, "totals": basket_split(cls, m)["totals"]} for m in hist_months
    ]
    win_splits = [basket_split(cls, m)["totals"] for m in window]

    def win_mean(b):
        return float(np.mean([s[b] for s in win_splits])) if win_splits else 0.0

    def win_median(b):
        return float(np.median([s[b] for s in win_splits])) if win_splits else 0.0

    leaky = cls[(cls["basket"] == "leaky") & cls["month"].isin(window)]
    n = max(1, len(window))
    leaky_cats = (
        (leaky.groupby("category")["amount"].sum() / n).sort_values(ascending=False)
        if len(leaky)
        else pd.Series(dtype=float)
    )
    return {
        "month": current,
        "totals": split["totals"],
        "shares": split["shares"],
        "trend": trend,
        "history": history,
        "leaky_categories": [
            {"category": str(c), "monthly_total": r2(v)} for c, v in leaky_cats.items()
        ],
        "monthly_essentials": r2(win_mean("essential")),
        # #26 uses the median monthly Saver amount of the last 3 months.
        "monthly_saving": r2(win_median("saver")),
    }
