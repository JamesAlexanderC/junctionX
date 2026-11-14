"""Demo customers: income levels and one clearest demo per app level."""

import pandas as pd

from inferences import thresholds as th
from inferences.demo import income_levels, level_clarity, pick_level_demos

TYPES = (
    "Weekend Treater",
    "Night Owl",
    "Impulse Buyer",
    "Payday Splurger",
    "Steady Planner",
    "Balanced",
)


def index(app_levels=(0, 1, 2, 3)):
    """Every app level at every income level, two progress values each, with
    the spender type rotating so the picks can cover several."""
    rows = []
    n = 0
    for level in app_levels:
        for inc in range(1, 6):
            for progress in (0.2, 0.8):
                rows.append(
                    {
                        "customer_id": f"C{n:03d}",
                        "income_level": inc,
                        "spender_type": TYPES[n % len(TYPES)],
                        "level": level,
                        "level_progress": progress,
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


def test_level_clarity_is_distance_from_the_next_level():
    assert level_clarity(0.25) == 0.75
    assert level_clarity(1.0) == 0.0
    assert level_clarity(None) is None


def test_one_demo_per_app_level_lowest_first():
    demos = pick_level_demos(index())
    assert [d["level"] for d in demos] == [0, 1, 2, 3]
    assert [d["level_name"] for d in demos] == [
        "Not started",
        "Getting started",
        "In control",
        "Safety net",
    ]
    assert [d["demo"] for d in demos] == [1, 2, 3, 4]
    # Spread over income levels: four demos, four different fifths.
    assert len({d["income_level"] for d in demos}) == 4
    assert all(d["spender_type"] in TYPES for d in demos)


def test_picks_the_most_solid_example():
    df = index()
    by_id = df.set_index("customer_id")
    for d in pick_level_demos(df):
        assert by_id.loc[d["customer_id"], "level_progress"] == 0.2
        assert d["clarity"] == 0.8


def test_only_levels_present_get_a_demo():
    demos = pick_level_demos(index(app_levels=(1, 3)))
    assert [d["level"] for d in demos] == [1, 3]


def test_short_histories_and_no_income_are_skipped():
    df = index()
    df["months"] = th.DEMO_MIN_HISTORY_MONTHS - 1
    assert pick_level_demos(df) == []
    df = index()
    df["income_level"] = 0
    assert pick_level_demos(df) == []


def test_ties_go_to_the_longer_history():
    df = index(app_levels=(1,))
    df["level_progress"] = 0.0
    df["income_level"] = 1
    df.loc[df["customer_id"] == "C003", "months"] = 24
    demos = pick_level_demos(df)
    assert demos[0]["customer_id"] == "C003"
