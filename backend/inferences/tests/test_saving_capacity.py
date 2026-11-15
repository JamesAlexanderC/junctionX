"""One-off cash must not fund a recurring monthly commitment."""

from datetime import date

from inferences import goals


def test_one_off_surplus_does_not_raise_monthly_capacity():
    assert (
        goals.safe_to_save_monthly(
            {"monthly_saving": 100}, {"safe_to_save_today": 1000}
        )
        == 100
    )


def test_surplus_does_not_make_an_unaffordable_goal_realistic():
    goal = {
        "target": 1200,
        "saved": 0,
        "start_date": "2026-01-01",
        "target_date": "2027-01-01",
    }
    out = goals.evaluate_goal(
        goal,
        date(2026, 7, 1),
        {"monthly_saving": 100},
        {"safe_to_save_today": 1000},
    )
    assert out["realistic"] is False
    assert out["suggested_monthly"] == 100
    assert out["projected_date"] == "2027-07-01"


def test_one_off_projection_applies_cash_once_without_marking_it_saved():
    goal = {
        "target": 1500,
        "saved": 100,
        "start_date": "2026-01-01",
        "target_date": "2027-01-01",
    }
    out = goals.evaluate_goal(
        goal,
        date(2026, 7, 1),
        {"monthly_saving": 100},
        {"safe_to_save_today": 1000},
    )
    assert out["saved"] == 100
    assert out["one_off_scenario"] == {
        "contribution": 1000,
        "monthly_rate": 100,
        "months_needed": 4,
        "projected_date": "2026-11-01",
    }


def test_one_off_surplus_cannot_clear_recurring_goal_clash():
    monthly = goals.safe_to_save_monthly(
        {"monthly_saving": 100}, {"safe_to_save_today": 1000}
    )
    assert goals.clash([{"monthly_needed": 200}], monthly)["clash"] is True


def test_one_off_scenario_can_fully_fund_goal_with_no_monthly_rate():
    out = goals.evaluate_goal(
        {"target": 500, "saved": 100},
        date(2026, 7, 1),
        {},
        {"safe_to_save_today": 1000},
    )
    assert out["projected_date"] is None
    assert out["one_off_scenario"]["contribution"] == 400
    assert out["one_off_scenario"]["months_needed"] == 0
    assert out["one_off_scenario"]["projected_date"] == "2026-07-01"
