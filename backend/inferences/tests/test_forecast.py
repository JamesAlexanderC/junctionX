"""Forecast #17 to #23 (handoff/forcasting.md FC-1 to FC-8).

Built on Test Aino (inferences/tests/fixtures.py): July to October 2026,
salary EUR 2,000 on the 25th, rent EUR 650 on the 1st.
"""

from datetime import date

import pytest

from coach.insights import end_of_month as end_of_month_insight
from inferences import baskets, forecast, income
from inferences.profile import build_profile
from inferences.tests.fixtures import aino_df

CUSTOMER = {"customer_id": "aino", "age": 24, "postal_code": "00510"}


def _forecast(today):
    df = aino_df(until=today)
    inc = income.compute_income(df, today)
    bsk = baskets.compute_baskets(df, today, bills=inc["bills"])
    return forecast.compute_forecast(df, today, inc, bsk)


# --- FC-1: the month-end target never has zero days left (#19) -------------------


@pytest.mark.parametrize(
    "today, target",
    [
        (date(2026, 9, 15), "2026-09-30"),  # mid-month: this month
        (date(2026, 9, 27), "2026-09-30"),  # 3 days left: still this month
        (date(2026, 9, 28), "2026-10-31"),  # 2 days left: roll over
        (date(2026, 9, 30), "2026-10-31"),  # last day (the data's as-of date)
    ],
)
def test_month_end_target_rolls_over_near_month_end(today, target):
    assert _forecast(today)["end_of_month"]["date"] == target


def test_month_end_on_the_last_day_has_a_real_range():
    eom = _forecast(date(2026, 9, 30))["end_of_month"]
    assert eom["low"] < eom["expected"] < eom["high"]


def test_daily_path_reaches_the_month_end_target():
    f = _forecast(date(2026, 9, 30))
    assert f["daily_path"][-1]["date"] >= f["end_of_month"]["date"]


def test_end_of_month_insight_names_the_date_on_the_last_day():
    profile = build_profile(aino_df(until=date(2026, 9, 30)), CUSTOMER, "2026-09-30")
    (row,) = end_of_month_insight(profile)
    assert "31 Oct" in row["text"]
    assert "likely between" in row["text"]
