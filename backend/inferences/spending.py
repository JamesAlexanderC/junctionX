"""Spending per category, as the categories appear in the data.

profile["spending"]: the latest month with spending (this month, else the last
full month) split by the transaction ``category`` column. Spending is outflows
minus transfers to the customer's own accounts (common.spend, the same rule as
#24). Category names keep the data's own spelling: prepare() lowercases them
for vocabulary matching, so the original spelling is looked up again here.
"""

from __future__ import annotations

import pandas as pd

from . import models
from .common import add_months, month_key, prepare, r2, spend


def _display_names(df: pd.DataFrame) -> dict:
    """lowercased category -> its most common spelling in the raw data."""
    if "category" not in df.columns or not len(df):
        return {}
    raw = df["category"].dropna().astype(str)
    out = {}
    for name in raw.value_counts().index:
        out.setdefault(name.lower(), name)
    return out


def _month_split(s: pd.DataFrame, month: str, names: dict) -> dict:
    m = s[s["month"] == month]
    sums = m.groupby("category")["amount"].sum().sort_values(ascending=False)
    rows = [(str(c), r2(float(v))) for c, v in sums.items() if r2(float(v)) > 0]
    total = r2(sum(v for _, v in rows))
    return {
        "month": month,
        "total": total,
        "categories": [
            {
                "category": names.get(c, c),
                "total": v,
                "share": round(models.share(v, total) * 100, 1) if total else 0.0,
                "count": int((m["category"] == c).sum()),
            }
            for c, v in rows
        ],
    }


def compute_spending(df: pd.DataFrame, today) -> dict:
    """Category split of this month, else of last month if this one is empty.

    df: the raw transactions (before prepare), so category names keep their
    spelling. ``is_current`` says which month was used.
    """
    names = _display_names(df)
    s = spend(prepare(df, today))
    current = month_key(today)
    split = _month_split(s, current, names)
    if split["categories"]:
        return {**split, "is_current": True}
    last = _month_split(s, add_months(current, -1), names)
    if last["categories"]:
        return {**last, "is_current": False}
    return {**split, "is_current": True}
