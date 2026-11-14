"""build_profile: every inference in the shape of profile_demo.json."""

import json
import math
from pathlib import Path

import pytest

from inferences.profile import age_band, build_profile
from inferences.tests.fixtures import TODAY, aino_df

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "coach"
    / "tests"
    / "fixtures"
    / "profile_demo.json"
)
CUSTOMER = {"customer_id": "C-AINO", "age": 24, "postal_code": "00510"}


@pytest.fixture(scope="module")
def profile():
    return build_profile(aino_df(), CUSTOMER, TODAY)


def test_has_every_top_level_key_of_the_demo_fixture(profile):
    expected = set(json.loads(FIXTURE.read_text()))
    assert expected <= set(profile)


@pytest.mark.parametrize(
    "section", ["income", "baskets", "habits", "forecast", "levels", "goals"]
)
def test_sections_have_the_demo_fixture_keys(profile, section):
    expected = set(json.loads(FIXTURE.read_text())[section])
    assert expected <= set(profile[section])


def test_is_json_serialisable(profile):
    json.dumps(profile)


def test_dates_and_customer(profile):
    assert profile["today"] == "2026-10-18"
    assert profile["customer"] == {
        "age": 24,
        "postal_code": "00510",
        "age_band": "18-24",
        "area": "00",
    }


def test_carries_retained_income_and_alerts(profile):
    assert "retained_income" in profile["income"]
    assert isinstance(profile["alerts"], list)
    assert all("inference" in a for a in profile["alerts"])


def test_balance_is_latest_balance(profile):
    df = aino_df(until=TODAY)
    assert profile["balance"] == pytest.approx(df["balance_after_eur"].iloc[-1])


@pytest.mark.parametrize(
    "age,band",
    [
        (None, None),
        (17, None),
        (24, "18-24"),
        (25, "25-29"),
        (39, "30-39"),
        (54, "40-54"),
        (55, "55+"),
    ],
)
def test_age_bands(age, band):
    # #36: 18-24, 25-29, 30-39, 40-54, 55+.
    assert age_band(age) == band


def test_empty_frame_does_not_crash():
    empty = aino_df().iloc[0:0]
    out = build_profile(empty, CUSTOMER, TODAY)
    assert out["balance"] is None
    json.dumps(out)


def test_moderate_loan_payments_are_reported_below_alert_threshold():
    # Review: loan_payments_found and dsti must not depend on alert #76 firing.
    from inferences.tests.fixtures import make_df

    rows = []
    for m in (7, 8, 9, 10):
        rows.append(
            dict(
                ts=f"2026-{m:02d}-01 08:00",
                amount=3000,
                ttype="salary",
                category="Salary",
                mcc="",
            )
        )
        rows.append(
            dict(
                ts=f"2026-{m:02d}-05 08:00",
                amount=-300,
                category="loan",
                mcc="6141",
                merchant="M_BANK_LOAN",
            )
        )
    out = build_profile(make_df(rows), CUSTOMER, TODAY)
    assert out["mortgage"]["loan_payments_found"] is True
    assert out["mortgage"]["dsti"] == pytest.approx(0.1, abs=0.01)


def test_recommended_goal_uses_shared_difficulty_maths(profile):
    from inferences import models

    rec = profile["goals"]["recommended"]
    rate = profile["baskets"]["monthly_saving"]
    months = math.ceil(rec["target"] / rate) if rate > 0 else None
    assert rec["difficulty"] == models.goal_difficulty(months)
