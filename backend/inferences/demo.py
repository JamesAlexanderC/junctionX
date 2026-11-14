"""Demo customers for the landing page.

- income_levels: every customer's income fifth (1 = lowest), from mean
  monthly income with own-account transfers excluded (#2, #41).
- pick_spender_demos: one demo per spender type (#16), the clearest example
  of that type, spread so every income level appears at least once.
"""

from itertools import product

import pandas as pd

from . import thresholds as th
from .habits import TRAIT_LABELS

INCOME_LABELS = {
    1: "Lowest income",
    2: "Low income",
    3: "Middle income",
    4: "High income",
    5: "Highest income",
}
NO_INCOME_LABEL = "No income"
# Display order; the trait types first, then the two calm ones.
SPENDER_TYPES = (*TRAIT_LABELS.values(), "Steady Planner", "Balanced")
_TRAIT_OF = {label: trait for trait, label in TRAIT_LABELS.items()}


def income_levels(monthly_income, levels=None):
    """Series of income levels 1..levels (equal-sized bands); 0 for customers
    with no income."""
    levels = levels or th.DEMO_LEVELS
    out = pd.Series(0, index=monthly_income.index, dtype=int)
    has = monthly_income > 0
    if has.sum() >= levels:
        ranks = monthly_income[has].rank(method="first")
        out[has] = pd.qcut(ranks, levels, labels=False).astype(int) + 1
    return out


def clarity(spender_type, scores):
    """How clearly a customer is their spender type, higher = clearer.
    Trait types: lead of the trait over the next highest trait. Steady
    Planner and Balanced: how far every trait stays below its flag."""
    if not scores:
        return None
    trait = _TRAIT_OF.get(spender_type)
    if trait is None:
        return 1.0 - max(scores.values())
    if trait not in scores:
        return None
    others = [v for k, v in scores.items() if k != trait]
    return scores[trait] - max(others, default=0.0)


def pick_spender_demos(index):
    """index: DataFrame with customer_id, income_level, spender_type,
    spender_scores (dict), months. Returns demo dicts, lowest income first,
    numbered from 1."""
    df = index[
        (index["months"] >= th.DEMO_MIN_HISTORY_MONTHS)
        & (index["income_level"] > 0)
        & index["spender_type"].isin(SPENDER_TYPES)
    ].copy()
    if df.empty:
        return []
    df["clarity"] = [
        clarity(t, s) for t, s in zip(df["spender_type"], df["spender_scores"])
    ]
    df = df.dropna(subset=["clarity"])

    # Clearest customer per (spender type, income level).
    best = {}
    for (stype, level), group in df.groupby(["spender_type", "income_level"]):
        row = group.loc[group["clarity"].idxmax()]
        best[(stype, int(level))] = (float(row["clarity"]), row["customer_id"])
    types = [t for t in SPENDER_TYPES if any(k[0] == t for k in best)]
    levels = sorted({k[1] for k in best})

    # Assign each type an income level: cover as many levels as possible,
    # then take the clearest examples. 5 levels ^ 6 types = 15,625 options.
    choice, choice_key = None, None
    for combo in product(levels, repeat=len(types)):
        cells = list(zip(types, combo))
        if any(c not in best for c in cells):
            continue
        key = (len(set(combo)), sum(best[c][0] for c in cells))
        if choice_key is None or key > choice_key:
            choice, choice_key = cells, key
    if choice is None:
        return []

    choice.sort(key=lambda c: (c[1], SPENDER_TYPES.index(c[0])))
    return [
        {
            "demo": n,
            "customer_id": str(best[c][1]),
            "income_level": c[1],
            "income_label": INCOME_LABELS.get(c[1], f"Level {c[1]}"),
            "spender_type": c[0],
            "clarity": round(best[c][0], 2),
        }
        for n, c in enumerate(choice, 1)
    ]
