"""Spending per category, as the categories appear in the data.

profile["spending"]: the latest month with spending (this month, else the last
full month) split by the transaction ``category`` column. Spending is outflows
minus transfers to the customer's own accounts (common.spend, the same rule as
#24). Category names keep the data's own spelling: prepare() lowercases them
for vocabulary matching, so the original spelling is looked up again here.

Each category also carries ``usual``: its mean monthly spend over the last 3
full months (whatif.category_means, #24), and ``vs_usual`` = total - usual.
Money moved into savings or investments (Saver deposits, #75) is not spending:
it is listed apart under ``savings`` and left out of ``total``.
"""

from __future__ import annotations

import pandas as pd

from . import models
from .common import add_months, month_key, outflows, prepare, r2, saver_mask, spend
from .whatif import category_means


def _display_names(df: pd.DataFrame) -> dict:
    """lowercased category -> its most common spelling in the raw data."""
    if "category" not in df.columns or not len(df):
        return {}
    raw = df["category"].dropna().astype(str)
    out = {}
    for name in raw.value_counts().index:
        out.setdefault(name.lower(), name)
    return out


def _by_category(m: pd.DataFrame):
    """[(lowercased category, total, count)] of positive totals, largest first."""
    if not len(m):
        return []
    g = m.groupby("category")["amount"]
    sums, counts = g.sum().sort_values(ascending=False), g.size()
    return [
        (str(c), r2(float(v)), int(counts[c]))
        for c, v in sums.items()
        if r2(float(v)) > 0
    ]


def _month_split(
    spent: pd.DataFrame, saved: pd.DataFrame, month: str, names: dict, means: dict
) -> dict:
    rows = _by_category(spent[spent["month"] == month])
    total = r2(sum(v for _, v, _ in rows))
    categories = []
    for c, v, n in rows:
        usual = means.get(c)
        categories.append(
            {
                "category": names.get(c, c),
                "total": v,
                "share": round(models.share(v, total) * 100, 1) if total else 0.0,
                "count": n,
                "usual": usual,
                "vs_usual": r2(v - usual) if usual is not None else None,
            }
        )
    savings = [
        {"category": names.get(c, c), "total": v, "count": n}
        for c, v, n in _by_category(saved[saved["month"] == month])
    ]
    return {
        "month": month,
        "total": total,
        "categories": categories,
        "savings": savings,
        "savings_total": r2(sum(r["total"] for r in savings)),
    }


def compute_spending(df: pd.DataFrame, today, means: dict | None = None) -> dict:
    """Category split of this month, else of last month if this one is empty.

    df: the raw transactions (before prepare), so category names keep their
    spelling. means: whatif.category_means (computed here when not given).
    ``is_current`` says which month was used.
    """
    names = _display_names(df)
    prepared = prepare(df, today)
    if means is None:
        means = category_means(df, today)
    spent = spend(prepared)
    saved = outflows(prepared)
    saved = saved[saver_mask(prepared).loc[saved.index]]
    current = month_key(today)
    for month, is_current in ((current, True), (add_months(current, -1), False)):
        split = _month_split(spent, saved, month, names, means)
        if split["categories"] or split["savings"]:
            return {**split, "is_current": is_current}
    return {**_month_split(spent, saved, current, names, means), "is_current": True}
