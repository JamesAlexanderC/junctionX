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


# --- FC-4: tight days alert wording without a payday (#20) -----------------------


def _tight_days_alert(payday_found):
    from inferences.alerts import rule_20_danger_days

    profile = {
        "forecast": {"danger_days": ["2026-10-05", "2026-10-06"]},
        "income": {"payday": {"found": payday_found}},
    }
    return rule_20_danger_days(None, profile, date(2026, 9, 30))


def test_tight_days_without_payday_says_next_30_days():
    text = _tight_days_alert(payday_found=False)["text"]
    assert "in the next 30 days" in text
    assert "payday" not in text


def test_tight_days_with_payday_still_says_before_payday():
    assert "before payday" in _tight_days_alert(payday_found=True)["text"]


# --- FC-5: #17 safe to spend, the app's formula (context.md, chosen by Will) ------
# Available = B - bills before payday - monthly saving x share of cycle left
#             - buffer; safe this week = Available x min(7, D) / D, floor 0.
# Hand-checked live values from handoff/forcasting.md (D = 15 of a 30-day cycle).


@pytest.mark.parametrize(
    "balance, bills, saving, buffer, expected",
    [
        (1085.77, 730.54, 445.37, 92.48, 18.70),  # CUST03369
        (1103.89, 622.19, 116.11, 107.15, 147.70),  # CUST00025
    ],
)
def test_safe_to_spend_matches_the_hand_checked_customers(
    balance, bills, saving, buffer, expected
):
    out = forecast.safe_to_spend_week(
        balance, bills, saving, buffer, days_to_payday=15, cycle_days=30
    )
    assert out == pytest.approx(expected, abs=0.01)


def test_safe_to_spend_is_never_negative():
    assert forecast.safe_to_spend_week(100, 500, 0, 50, 10, 30) == 0


def test_safe_to_spend_uses_a_full_week_only_when_payday_is_far():
    # D <= 7: everything available may be spent before payday.
    assert forecast.safe_to_spend_week(500, 0, 0, 100, 3, 30) == pytest.approx(400)


# --- FC-8: the rest of the forecast rules -----------------------------------------


def test_no_payday_makes_the_forecast_items_unavailable():
    from inferences.availability import availability

    profile = build_profile(aino_df(until=date(2026, 9, 30)), CUSTOMER, "2026-09-30")
    profile["income"]["payday"] = {**profile["income"]["payday"], "found": False}
    flags = availability(profile)
    for item in (
        "forecast.safe_to_spend_week",
        "forecast.safe_to_save_today",
        "forecast.end_of_month",
        "forecast.danger_days",
    ):
        assert flags[item]["available"] is False, item
        assert "payday" in flags[item]["reason"], item


def test_danger_days_are_exactly_the_days_below_50_before_payday():
    from inferences import thresholds as th

    today = date(2026, 10, 18)
    f = _forecast(today)
    df = aino_df(until=today)
    payday = income.compute_income(df, today)["payday"]["next_payday"]
    expected = [
        p["date"]
        for p in f["daily_path"]
        if p["date"] < payday and p["low"] < th.DANGER_BALANCE_EUR
    ]
    assert f["danger_days"] == expected


def test_surprise_fund_divides_by_months_of_data_up_to_12():
    from unittest.mock import patch

    today = date(2026, 10, 31)
    df = aino_df(until=today)
    with patch.object(forecast, "months_spanned", return_value=4):
        four = forecast.surprise_fund(df, today, {})
    with patch.object(forecast, "months_spanned", return_value=30):
        capped = forecast.surprise_fund(df, today, {})
    assert four > 0
    assert capped == pytest.approx(four * 4 / 12)


def test_seasonal_needs_a_full_year():
    # Aino has 4 months of data: no ratio, no warning (#23 unavailable).
    out = forecast.seasonal(aino_df(until=date(2026, 10, 18)), date(2026, 10, 18))
    assert out["ratio"] is None and out["warn"] is False
