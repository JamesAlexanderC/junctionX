"""Alert inferences #38 to #40 as plain functions (alerts.py wraps them)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import models
from . import thresholds as th
from .common import add_months, month_key, prepare, r2, spend


def unusual_charge(amount: float, merchant_history, category_history=None) -> dict:
    """#38 Unusual charge (model 2).

    z = 0.6745 (x - merchant median) / MAD; flag when z > 3.5 and the merchant
    has >= 3 past payments; otherwise flag when x > 3 x the category median.
    """
    # Lists, not Series: `category_history or hist` below needs a plain
    # truth value (a pandas Series raised "truth value is ambiguous").
    hist = [float(x) for x in merchant_history]
    category_history = (
        None if category_history is None else [float(x) for x in category_history]
    )
    med = float(np.median(hist)) if hist else None
    m = models.mad(hist) if hist else None
    z = models.robust_z(amount, hist) if hist else None
    if len(hist) >= th.UNUSUAL_MIN_HISTORY and z is not None:
        flagged = (
            z > th.ROBUST_Z_FLAG
            and amount > th.UNUSUAL_MIN_MULT * med
            and amount - med > th.UNUSUAL_MIN_EXCESS_EUR
        )
        rule = "robust_z"
    else:
        cat = [float(x) for x in (category_history or hist)]
        flagged = bool(cat) and amount > th.UNUSUAL_CATEGORY_MULT * float(
            np.median(cat)
        )
        rule = "category_median"
    return {
        "amount": r2(amount),
        "median": r2(med),
        "mad": r2(m),
        "z": r2(z),
        "rule": rule,
        "flagged": bool(flagged),
    }


def unusual_charges(df: pd.DataFrame, today, days: int = 30) -> list[dict]:
    """#38 over the last `days` days of spend."""
    s = spend(prepare(df, today))
    start = pd.Timestamp(today) - pd.Timedelta(days=days)
    out = []
    for idx, row in s[s["tx_date"] >= start].iterrows():
        before = s[s["tx_timestamp"] < row["tx_timestamp"]]
        known = row["merchant_id"] != ""
        merchant = before[known & (before["merchant_id"] == row["merchant_id"])][
            "amount"
        ]
        category = before[before["category"] == row["category"]]["amount"]
        res = unusual_charge(row["amount"], merchant, category)
        if res["flagged"]:
            res.update(
                {
                    "tx_id": str(row["tx_id"]),
                    "merchant_id": str(row["merchant_id"]),
                    "category": str(row["category"]),
                    "date": row["tx_date"].date().isoformat(),
                }
            )
            out.append(res)
    return out


def duplicate_charges(df: pd.DataFrame) -> list[dict]:
    """#39: same merchant and amount less than 10 minutes apart (model 5)."""
    s = prepare(df)
    s = s[s["tx_amount_eur"] < 0]
    out = []
    for a, b in models.duplicate_pairs(s):
        row = s[s["tx_id"] == a].iloc[0]
        out.append(
            {
                "tx_ids": [str(a), str(b)],
                "merchant_id": str(row["merchant_id"]),
                "amount": r2(-row["tx_amount_eur"]),
                "date": row["tx_date"].date().isoformat(),
            }
        )
    return out


def category_spikes(df: pd.DataFrame, today) -> list[dict]:
    """#40: this month > 1.5 x mean of the previous 3 months and +EUR 20."""
    s = spend(prepare(df, today))
    current = month_key(today)
    prev = [add_months(current, -k) for k in range(3, 0, -1)]
    out = []
    for cat, g in s.groupby("category"):
        by_month = g.groupby("month")["amount"].sum()
        now = float(by_month.get(current, 0.0))
        if th.SPIKE_REQUIRE_FULL_HISTORY and not all(
            by_month.get(m, 0.0) > 0 for m in prev
        ):
            continue
        mean_prev = float(np.mean([by_month.get(m, 0.0) for m in prev]))
        threshold = th.SPIKE_MULT * mean_prev
        diff = now - mean_prev
        if now > threshold and diff > th.SPIKE_MIN_DIFF_EUR:
            out.append(
                {
                    "category": str(cat),
                    "month": current,
                    "this_month": r2(now),
                    "previous_mean": r2(mean_prev),
                    "threshold": r2(threshold),
                    "difference": r2(diff),
                    "tx_ids": [str(t) for t in g[g["month"] == current]["tx_id"]],
                }
            )
    return out
