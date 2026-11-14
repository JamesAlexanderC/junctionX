"""Demo customers for the landing page.

- income_levels: every customer's income fifth (1 = lowest), from mean
  monthly income with own-account transfers excluded (#2, #41).
- pick_level_demos: one demo per app level (#28 to #33), the customer most
  solidly at that level, spread over income levels and spender types (#16).
"""

from itertools import product

import pandas as pd

from . import thresholds as th

INCOME_LABELS = {
    1: "Lowest income",
    2: "Low income",
    3: "Middle income",
    4: "High income",
    5: "Highest income",
}
NO_INCOME_LABEL = "No income"
# Same label compute_levels uses for level 0.
NOT_STARTED = "Not started"


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


def level_clarity(progress):
    """How solidly a customer sits at their app level, higher = clearer:
    1 - progress towards the next level, so a customer about to move up is
    a weaker example of the level they are on."""
    if progress is None or pd.isna(progress):
        return None
    return 1.0 - min(1.0, max(0.0, float(progress)))


def pick_level_demos(index):
    """index: DataFrame with customer_id, income_level, spender_type, level,
    level_progress, months. Returns one demo dict per app level found, lowest
    level first, numbered from 1."""
    df = index[
        (index["months"] >= th.DEMO_MIN_HISTORY_MONTHS)
        & (index["income_level"] > 0)
        & index["level"].notna()
    ].copy()
    if df.empty:
        return []
    df["level"] = df["level"].astype(int)
    df["clarity"] = df["level_progress"].map(level_clarity)
    df = df.dropna(subset=["clarity"])

    # Clearest customer per (app level, income level); on a tie the longer
    # history, which gives the demo more to show.
    best = {}
    for (level, inc), group in df.groupby(["level", "income_level"]):
        row = group.sort_values(["clarity", "months"], kind="stable").iloc[-1]
        best[(int(level), int(inc))] = (
            float(row["clarity"]),
            row["customer_id"],
            row["spender_type"] if isinstance(row["spender_type"], str) else None,
        )
    levels = sorted({k[0] for k in best})
    incomes = sorted({k[1] for k in best})

    # Assign each app level an income level: cover as many income levels and
    # spender types as possible, then take the clearest examples. At most
    # 5 income levels ^ 7 app levels = 78,125 options; in practice 5 ^ 4.
    choice, choice_key = None, None
    for combo in product(incomes, repeat=len(levels)):
        cells = list(zip(levels, combo))
        if any(c not in best for c in cells):
            continue
        types = {best[c][2] for c in cells} - {None}
        key = (len(set(combo)), len(types), sum(best[c][0] for c in cells))
        if choice_key is None or key > choice_key:
            choice, choice_key = cells, key
    if choice is None:
        return []

    return [
        {
            "demo": n,
            "customer_id": str(best[c][1]),
            "level": c[0],
            "level_name": level_name(c[0]),
            "income_level": c[1],
            "income_label": INCOME_LABELS.get(c[1], f"Level {c[1]}"),
            "spender_type": best[c][2],
            "clarity": round(best[c][0], 2),
        }
        for n, c in enumerate(choice, 1)
    ]


def level_name(level):
    """#28 to #33 ladder name; level 0 is "Not started"."""
    return th.LEVEL_NAMES.get(int(level), NOT_STARTED)
