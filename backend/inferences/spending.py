"""Spending per category, as the categories appear in the data.

profile["spending"]: the latest month with spending (this month, else the last
full month) split by the transaction ``category`` column. Spending is outflows
minus transfers to the customer's own accounts (common.spend, the same rule as
#24). Category names keep the data's own spelling: prepare() lowercases them
for vocabulary matching, so the original spelling is looked up again here.

Each category also carries ``usual``: its mean monthly spend over the 3 full
months before the month shown (whatif.category_means, #24), and
``usual_so_far``: the mean of what those months had spent by the same day of
the month. ``vs_usual = total - usual_so_far``, so a part month is compared
with the same part of a usual month (day 12 against days 1 to 12), not with a
whole month; for a complete month usual_so_far == usual. A rent paid on the
2nd counts in full from the 2nd, as it did in the usual months.
Money moved into savings or investments (Saver deposits, #75) is not spending:
it is listed apart under ``savings`` and left out of ``total``.
"""

from __future__ import annotations

import pandas as pd

from . import models
from .common import (
    add_months,
    days_in_month,
    full_months,
    month_key,
    outflows,
    prepare,
    r2,
    saver_mask,
    spend,
    to_date,
)
from . import thresholds as th
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


def usual_by_day(spent: pd.DataFrame, months: list[str], day: int) -> dict:
    """{category: mean spend on days 1..day} over ``months`` (each month's
    day capped at its length). A category missing from a month counts 0."""
    if not months:
        return {}
    parts = []
    for m in months:
        last = min(day, days_in_month(m))
        g = spent[(spent["month"] == m) & (spent["tx_date"].dt.day <= last)]
        parts.append(g.groupby("category")["amount"].sum())
    table = pd.concat(parts, axis=1).fillna(0.0)
    return {str(c): r2(v) for c, v in (table.sum(axis=1) / len(months)).items()}


def _month_split(
    spent: pd.DataFrame,
    saved: pd.DataFrame,
    month: str,
    names: dict,
    means: dict,
    so_far: dict | None = None,
) -> dict:
    """so_far: usual_by_day for a part month; None for a complete month."""
    rows = _by_category(spent[spent["month"] == month])
    total = r2(sum(v for _, v, _ in rows))
    categories = []
    for c, v, n in rows:
        usual = means.get(c)
        if usual is None:
            usual_so_far = None
        elif so_far is None:
            usual_so_far = usual
        else:
            usual_so_far = so_far.get(c, 0.0)
        categories.append(
            {
                "category": names.get(c, c),
                "total": v,
                "share": round(models.share(v, total) * 100, 1) if total else 0.0,
                "count": n,
                "usual": usual,
                "usual_so_far": usual_so_far,
                "vs_usual": (
                    r2(v - usual_so_far) if usual_so_far is not None else None
                ),
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
    spelling. means: whatif.category_means as of today (computed here when
    not given); it is only used for this month. ``is_current`` says which
    month was used.
    """
    names = _display_names(df)
    prepared = prepare(df, today)
    if means is None:
        means = category_means(df, today)
    spent = spend(prepared)
    saved = outflows(prepared)
    saved = saved[saver_mask(prepared).loc[saved.index]]
    current = month_key(today)
    day = to_date(today).day
    window = full_months(today, th.WINDOW_FULL_MONTHS, prepared)
    so_far = usual_by_day(spent, window, day)
    split = _month_split(spent, saved, current, names, means, so_far)
    if split["categories"] or split["savings"]:
        return {**split, "is_current": True}
    # Last month is complete; its usual is the 3 full months before it, so it
    # is never measured against an average that contains itself.
    last = add_months(current, -1)
    last_start = pd.Period(last, freq="M").start_time.date()
    split = _month_split(
        spent, saved, last, names, category_means(df, last_start), None
    )
    if split["categories"] or split["savings"]:
        return {**split, "is_current": False}
    return {
        **_month_split(spent, saved, current, names, means, so_far),
        "is_current": True,
    }
