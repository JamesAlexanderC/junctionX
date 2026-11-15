"""Plan summaries must use the dates and cash flows in the simulated path."""

from datetime import date, timedelta

from coach import planner


def profile():
    today = date(2026, 10, 10)
    return {
        "today": today.isoformat(),
        "balance": 1000,
        "income": {
            "payday": {"found": True, "next_payday": "2026-10-12", "days_to_payday": 2},
            "bills": [],
        },
        "baskets": {"monthly_saving": 0},
        "forecast": {
            "buffer": 50,
            "safe_to_spend_week": 100,
            "daily_discretionary": {"value": 10, "std": 0},
            "daily_path": [
                {
                    "date": (today + timedelta(days=i)).isoformat(),
                    "expected": 1000 - i * 10,
                    "low": 1000 - i * 10,
                    "high": 1000 - i * 10,
                }
                for i in range(1, 22)
            ],
            "end_of_month": {"expected": 790, "low": 790, "high": 790},
        },
    }


def test_cut_uses_month_end_and_payday_as_separate_horizons():
    p = profile()
    sim = planner.apply_action(
        p,
        {
            "type": "cut_category",
            "category": "coffee",
            "pct": 0.1,
            "monthly_impact": 30.44,
        },
    )
    fc = sim["forecast"]
    assert fc["end_of_month"]["expected"] == 811  # 21 days, not 2
    assert fc["end_of_month"] == {
        k: fc["daily_path"][-1][k] for k in ("expected", "low", "high")
    }
    assert fc["safe_to_save_today"] == 941  # lowest pre-payday point: 991
    assert fc["safe_to_spend_week"] == 101  # one pre-payday day, not seven


def test_cancelled_bill_is_removed_on_its_due_date_only():
    p = profile()
    bill = {
        "merchant_id": "sub",
        "name": "Subscription",
        "amount": 20,
        "next_date": "2026-10-15",
        "median_gap_days": 30,
    }
    p["income"]["bills"] = [bill]
    p["income"]["subscriptions"] = [bill]
    p["forecast"]["upcoming_bills"] = [{**bill, "date": "2026-10-15"}]
    for point in p["forecast"]["daily_path"]:
        if point["date"] >= "2026-10-15":
            for key in ("expected", "low", "high"):
                point[key] -= 20
    sim = planner.apply_action(
        p, {"type": "cancel_subscription", "merchant_id": "sub", "monthly_impact": 20}
    )
    fc = sim["forecast"]
    assert fc["daily_path"][0] == p["forecast"]["daily_path"][0]
    assert fc["daily_path"][4]["expected"] == 950
    assert fc["end_of_month"]["expected"] == 790
    assert fc["safe_to_spend_week"] == 100  # bill falls after payday
    assert fc["upcoming_bills"] == []


def test_danger_days_exclude_payday_and_later_dates():
    p = profile()
    p["forecast"]["daily_path"][-1]["low"] = -100
    sim = planner.apply_action(p, {"type": "move_saver_to_buffer", "amount": 10})
    assert sim["forecast"]["danger_days"] == []
    assert sim["forecast"]["balance"] == sim["balance"] == 1010
    assert sim["forecast"]["safe_to_save_today"] == 950
    assert sim["forecast"]["end_of_month"]["expected"] == 800


def test_plan_goal_date_uses_calendar_months():
    p = profile()
    p["goals"] = {"active": [{"target": 100, "saved": 0}]}
    p["baskets"]["monthly_saving"] = 100
    assert planner._goal_date(p, date(2026, 1, 31)) == "2026-02-28"


def test_combined_cuts_accumulate_on_one_unrounded_path():
    p = profile()
    actions = [
        {
            "type": "cut_category",
            "category": "coffee",
            "pct": 0.1,
            "monthly_impact": saving,
        }
        for saving in (30.44, 60.88)
    ]
    sim = planner.apply_actions(p, actions)
    assert sim["forecast"]["end_of_month"]["expected"] == 853
    assert sim["forecast"]["safe_to_spend_week"] == 103
    assert p["forecast"]["daily_path"][-1]["expected"] == 790
    assert "_projection" not in p


def test_one_off_transfer_is_prorated_over_long_pay_cycle():
    p = profile()
    p["income"]["payday"].update(next_payday="2026-10-24", days_to_payday=14)
    sim = planner.apply_action(p, {"type": "move_saver_to_buffer", "amount": 100})
    assert sim["forecast"]["safe_to_spend_week"] == 150
    assert sim["forecast"]["safe_to_save_today"] == 920


def test_no_payday_does_not_create_spendable_cash_from_spending_cuts():
    p = profile()
    p["income"]["payday"] = {"found": False}
    p["forecast"]["safe_to_spend_week"] = 950
    sim = planner.apply_action(
        p,
        {
            "type": "cut_category",
            "category": "coffee",
            "pct": 0.1,
            "monthly_impact": 30.44,
        },
    )
    assert sim["forecast"]["safe_to_spend_week"] == 950


def test_cut_cannot_make_daily_spending_negative():
    p = profile()
    p["goals"] = {"active": [{"target": 1000, "saved": 0}]}
    sim = planner.apply_action(
        p,
        {
            "type": "cut_category",
            "category": "coffee",
            "pct": 0.3,
            "monthly_impact": 1000,
        },
    )
    assert sim["forecast"]["daily_discretionary"]["value"] == 0
    assert sim["forecast"]["end_of_month"]["expected"] == 1000
    assert sim["goals"]["active"][0]["extra_monthly"] == 304.4
