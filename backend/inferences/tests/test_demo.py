"""Demo customers: income levels and one clearest demo per spender type."""

import pandas as pd

from inferences import thresholds as th
from inferences.demo import clarity, income_levels, pick_spender_demos

TRAITS = ("weekend", "night", "impulse", "payday")
TRAIT_TYPE = {
    "weekend": "Weekend Treater",
    "night": "Night Owl",
    "impulse": "Impulse Buyer",
    "payday": "Payday Splurger",
}


def scores(top=None, value=0.9, rest=0.1):
    return {t: (value if t == top else rest) for t in TRAITS}


def index():
    """60 customers: every spender type at every income level."""
    rows = []
    kinds = [(TRAIT_TYPE[t], scores(t)) for t in TRAITS] + [
        ("Steady Planner", scores(rest=0.05)),
        ("Balanced", scores(rest=0.3)),
    ]
    n = 0
    for level in range(1, 6):
        for stype, sc in kinds:
            for strength in (0.7, 0.9):
                sc2 = {k: (strength if v == 0.9 else v) for k, v in sc.items()}
                rows.append(
                    {
                        "customer_id": f"C{n:03d}",
                        "income_level": level,
                        "spender_type": stype,
                        "spender_scores": sc2,
                        "months": 12,
                    }
                )
                n += 1
    return pd.DataFrame(rows)


def test_income_levels_are_equal_fifths_and_zero_without_income():
    income = pd.Series([0.0] + [100.0 * i for i in range(1, 11)])
    levels = income_levels(income)
    assert levels[0] == 0
    assert list(levels[1:]) == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_clarity_is_the_lead_over_the_next_trait():
    assert clarity("Night Owl", scores("night", 0.9, 0.2)) == 0.7
    assert clarity("Steady Planner", scores(rest=0.1)) == 0.9
    assert clarity("Night Owl", {}) is None


def test_one_demo_per_spender_type_covering_every_income_level():
    demos = pick_spender_demos(index())
    assert len(demos) == 6
    assert {d["spender_type"] for d in demos} == {
        "Weekend Treater",
        "Night Owl",
        "Impulse Buyer",
        "Payday Splurger",
        "Steady Planner",
        "Balanced",
    }
    assert {d["income_level"] for d in demos} == {1, 2, 3, 4, 5}
    assert [d["demo"] for d in demos] == [1, 2, 3, 4, 5, 6]
    levels = [d["income_level"] for d in demos]
    assert levels == sorted(levels)


def test_picks_the_clearest_example():
    df = index()
    demos = pick_spender_demos(df)
    by_id = df.set_index("customer_id")
    for d in demos:
        if d["spender_type"] in TRAIT_TYPE.values():
            sc = by_id.loc[d["customer_id"], "spender_scores"]
            assert max(sc.values()) == 0.9  # the stronger of the two


def test_short_histories_are_skipped():
    df = index()
    df["months"] = th.DEMO_MIN_HISTORY_MONTHS - 1
    assert pick_spender_demos(df) == []
