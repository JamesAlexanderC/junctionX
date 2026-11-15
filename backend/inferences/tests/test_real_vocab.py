"""Real S-Bank vocabulary (docs/data_profile.md) and the P1.1 decisions."""

from datetime import date

import pytest

from inferences import alerts
from inferences.baskets import basket_split, classify
from inferences.common import essential_mask, prepare
from inferences.detected_goals import detect_travel_goal
from inferences.income import compute_income
from inferences.tests import alert_fixtures as af
from inferences.tests.fixtures import make_df

SEPT = date(2026, 9, 30)


def _salary_and_sweep(months, salary, sweep):
    rows = []
    for m in months:
        rows.append(
            dict(
                ts=f"2026-{m:02d}-15 08:00",
                amount=salary,
                ttype="salary",
                category="salary",
                merchant="M_EMPLOYER",
                mcc="",
            )
        )
        rows.append(
            dict(
                ts=f"2026-{m:02d}-16 08:00",
                amount=-sweep,
                ttype="salary_sweep",
                category="salary sweep",
                merchant="",
                mcc="",
            )
        )
    return rows


@pytest.mark.parametrize(
    "category,mcc,expected",
    [
        ("Transportation", "4111", True),  # public transport
        ("Transportation", "5542", True),  # fuel
        ("Transportation", "7523", True),  # parking
        ("Transportation", "", True),  # blank MCC
        ("Transportation", "4121", False),  # taxi / ride-hailing
        ("Groceries", "5411", True),
        ("Restaurants", "5812", False),
    ],
)
def test_essential_mask_splits_transportation_by_mcc(category, mcc, expected):
    df = prepare(
        make_df([dict(ts="2026-09-01 12:00", amount=-10, category=category, mcc=mcc)])
    )
    assert bool(essential_mask(df).iloc[0]) is expected


def test_taxi_under_25_is_leaky():
    df = make_df(
        [dict(ts="2026-09-01 12:00", amount=-18, category="Transportation", mcc="4121")]
    )
    assert classify(df, SEPT)["basket"].tolist() == ["leaky"]


def test_salary_sweep_is_in_no_basket():
    rows = _salary_and_sweep([9], 3000, 2700) + [
        dict(ts="2026-09-20 12:00", amount=-60, category="Groceries", mcc="5411")
    ]
    split = basket_split(classify(make_df(rows), SEPT), "2026-09")
    assert sum(split["totals"].values()) == pytest.approx(60)


def test_investment_withdrawal_is_negative_saver():
    rows = [
        dict(
            ts="2026-09-05 10:00",
            amount=-200,
            ttype="investment_deposit",
            category="invest deposit",
            mcc="",
        ),
        dict(
            ts="2026-09-20 10:00",
            amount=500,
            ttype="investment_withdrawal",
            category="invest withdraw",
            mcc="",
        ),
    ]
    split = basket_split(classify(make_df(rows), SEPT), "2026-09")
    assert split["totals"]["saver"] == pytest.approx(-300)


def test_retained_income_and_partial_view():
    inc = compute_income(make_df(_salary_and_sweep([6, 7, 8, 9], 3000, 2700)), SEPT)
    assert inc["monthly_income"] == pytest.approx(3000)
    assert inc["retained_income"] == pytest.approx(300)
    assert inc["coverage"] == pytest.approx(0.9)
    assert inc["partial_view"] is True


def test_low_sweep_is_full_view():
    inc = compute_income(make_df(_salary_and_sweep([6, 7, 8, 9], 3000, 600)), SEPT)
    assert inc["coverage"] == pytest.approx(0.2)
    assert inc["partial_view"] is False


def test_spending_pace_uses_retained_income_and_ignores_sweep():
    rows = [af.tx(f"2026-09-{d:02d} 12:00", -50) for d in range(1, 11)]
    rows.append(
        af.tx("2026-09-02 08:00", -2700, "", "salary sweep", "", "salary_sweep")
    )
    prof = af.profile(income__monthly_income=3000.0, income__retained_income=300.0)
    a = alerts.rule_88_spending_pace(af.make_df(rows), prof, date(2026, 9, 10))
    assert a is not None
    assert a["trigger_values"]["spent"] == pytest.approx(500)
    assert a["trigger_values"]["income"] == pytest.approx(300)


def test_sweep_alone_does_not_trigger_savings_withdrawn():
    rows = [af.tx("2026-10-02 08:00", -2700, "", "salary sweep", "", "salary_sweep")]
    assert (
        alerts.rule_94_savings_withdrawn(
            af.make_df(rows), af.profile(), date(2026, 10, 18)
        )
        is None
    )


def test_withdrawal_above_deposits_triggers_savings_withdrawn():
    rows = [
        af.tx("2026-10-02 08:00", -200, "", "invest deposit", "", "investment_deposit"),
        af.tx(
            "2026-10-09 08:00", 500, "", "invest withdraw", "", "investment_withdrawal"
        ),
    ]
    a = alerts.rule_94_savings_withdrawn(
        af.make_df(rows), af.profile(), date(2026, 10, 18)
    )
    assert a is not None and a["inference"] == 94


def test_travel_goal_from_last_years_travel_category():
    rows = [
        dict(ts="2025-12-10 12:00", amount=-250, category="Travel", mcc="4511"),
        dict(ts="2026-01-05 12:00", amount=-150, category="Travel", mcc="7011"),
    ]
    goal = detect_travel_goal(make_df(rows), SEPT)
    assert goal is not None
    assert goal["inference"] == 58
    assert goal["last_year_spend"] == pytest.approx(400)


def test_no_travel_goal_below_threshold():
    rows = [dict(ts="2026-01-05 12:00", amount=-200, category="Travel", mcc="7011")]
    assert detect_travel_goal(make_df(rows), SEPT) is None


def test_forecast_payday_inflow_is_retained_income():
    from inferences.forecast import scheduled_flows

    income = {
        "payday": {"found": True, "next_payday": "2026-10-15", "amount": 3000.0},
        "monthly_income": 3000.0,
        "retained_income": 300.0,
    }
    flows = scheduled_flows(income, [], date(2026, 10, 1), date(2026, 10, 31))
    assert flows == [("2026-10-15", 300.0)]
