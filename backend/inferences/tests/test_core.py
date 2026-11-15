"""Inference unit tests on Test Aino (context.md "Tests", table 1)."""

import json

import pytest

from inferences import (
    baskets,
    forecast,
    habits,
    income,
    levels,
    models,
    whatif,
)
from inferences.tests.fixtures import AINO_OCT_END, TODAY, aino_df


@pytest.fixture(scope="module")
def df_today():
    return aino_df(until=TODAY)


@pytest.fixture(scope="module")
def inc(df_today):
    return income.compute_income(df_today, TODAY)


@pytest.fixture(scope="module")
def bsk(df_today, inc):
    return baskets.compute_baskets(df_today, TODAY, bills=inc["bills"])


# --- Income and bills ------------------------------------------------------------


def test_payday_found(inc):
    # #1: day 25; next payday from 18 Oct = Fri 23 Oct (25 Oct is a Sunday).
    p = inc["payday"]
    assert p["found"] is True
    assert p["day_of_month"] == 25
    assert p["next_payday"] == "2026-10-23"
    assert p["days_to_payday"] == 5
    assert p["merchant_id"] == "M_EMPLOYER"
    assert p["amount"] == 2000.0


def test_monthly_income(inc):
    assert inc["monthly_income"] == 2000.0  # #2


def test_income_stability(inc):
    assert inc["stability"] == {"cv": 0.0, "label": "Steady"}  # #3


def test_rent_is_a_bill(inc):
    # #4: rent, 650, next 1 Nov.
    rent = next(b for b in inc["bills"] if b["merchant_id"] == "M_RENT")
    assert rent["amount"] == 650.0
    assert rent["next_date"] == "2026-11-01"
    assert rent["is_subscription"] is False
    assert rent["name"] == "Rent"


def test_netflix_is_subscription_rent_is_not(inc):
    # #5
    subs = {s["merchant_id"] for s in inc["subscriptions"]}
    assert "M_NETFLIX" in subs
    assert "M_RENT" not in subs


def test_savings_transfer_and_groceries_are_not_bills(inc):
    ids = {b["merchant_id"] for b in inc["bills"]}
    assert "OWN_SAVINGS" not in ids
    assert "M_SMARKET" not in ids


# --- Baskets ---------------------------------------------------------------------


def test_one_off_dentist_bill_is_surprise():
    # #8: classified Surprise, not Essentials.
    df = aino_df()
    cls = baskets.classify(df, AINO_OCT_END)
    repair = cls[cls["merchant_id"] == "M_DENTIST"].iloc[0]
    assert repair["basket"] == "surprise"
    groceries = cls[cls["merchant_id"] == "M_SMARKET"]
    assert set(groceries["basket"]) == {"essential"}


def test_basket_split_october():
    # #10, #75: Essentials 890 (73.4%), Surprise 0, Leaky 172.99 (14.3%),
    # Saver 150 (12.4%).
    df = aino_df()
    cls = baskets.classify(df, AINO_OCT_END)
    split = baskets.basket_split(cls, "2026-10")
    assert split["totals"]["essential"] == 890.0
    assert split["totals"]["surprise"] == 0.0
    assert split["totals"]["leaky"] == 172.99
    assert split["totals"]["saver"] == 150.0
    assert split["shares"]["essential"] == 73.4
    assert split["shares"]["leaky"] == 14.3
    assert split["shares"]["saver"] == 12.4


def test_compute_baskets_shape(bsk):
    assert bsk["month"] == "2026-10"
    assert bsk["monthly_essentials"] == 890.0
    assert bsk["monthly_saving"] == 150.0
    cats = [c["category"] for c in bsk["leaky_categories"]]
    assert cats[0] == "takeaway"
    assert set(bsk["totals"]) >= {"essential", "surprise", "leaky", "saver"}


# --- What-ifs --------------------------------------------------------------------


def test_cut_takeaway_20pct(df_today):
    # #24: 18 a month, 216 a year.
    means = whatif.category_means(df_today, TODAY)
    assert means["takeaway"] == 90.0
    assert whatif.simulate_cut(means["takeaway"], 0.20) == {
        "monthly_saving": 18.0,
        "yearly_saving": 216.0,
    }


def test_drop_netflix(inc):
    # #25: between 150 and 160 a year.
    netflix = next(s for s in inc["subscriptions"] if s["merchant_id"] == "M_NETFLIX")
    yearly = whatif.drop_subscription(netflix["amount"], netflix["median_gap_days"])
    assert 150 <= yearly <= 160


def test_goal_date():
    # #26: 1,500 target, 640 saved, 150 a month -> 6 months.
    res = whatif.goal_date(1500, 640, 150, TODAY)
    assert res["months"] == 6
    assert res["reachable"] is True
    assert res["date"] == "2027-04-18"


def test_goal_difficulty_stretch():
    # #49: 6 months -> Stretch.
    assert models.goal_difficulty(models.months_to_goal(1500, 640, 150)) == "Stretch"


def test_monthly_needed_rounded():
    # #65: 1,500 target, 640 saved, 10 months -> 86 rounded up to 90.
    assert models.monthly_needed(1500, 640, 10) == 90.0


# --- Levels ----------------------------------------------------------------------


def test_safety_net_progress(df_today, inc, bsk):
    # #30: 445 / 890 = 0.50 -> 50%, not reached.
    lv = levels.compute_levels(df_today, TODAY, inc, bsk)
    assert lv["buffer_months"] == 0.5
    ladder = {step["level"]: step for step in lv["ladder"]}
    assert ladder[3]["reached"] is False
    assert ladder[3]["progress"] == 0.5
    assert ladder[1]["reached"] and ladder[2]["reached"]
    assert lv["current"] == 2
    assert lv["next"] == 3
    assert lv["euros_to_go"] == 445.0
    assert lv["easiest_next_step"]["category"] == "takeaway"


def test_next_requirement_says_what_level_3_needs(df_today, inc, bsk):
    # #30 with Aino's numbers: lowest balance 445 of 890 (1 month essentials).
    req = levels.compute_levels(df_today, TODAY, inc, bsk)["next_requirement"]
    assert "1 month of essential spending" in req["text"]
    [check] = req["checks"]
    assert check == {
        "text": "Lowest balance in the last 30 days: EUR 445 of EUR 890 needed",
        "met": False,
    }


@pytest.mark.parametrize("lv", [1, 2, 3, 4, 5, 6])
def test_every_level_has_a_requirement(lv):
    facts = {
        "payday": True,
        "bills": False,
        "last_month": {"month": "2026-09", "spent": 1200.0, "earned": 1000.0},
        "essentials": 890.0,
        "low": 445.0,
        "l3": False,
        "goals_active": 1,
        "goals_counting": 0,
        "readiness": 0.5,
        "l5": False,
        "buffer_months": 0.5,
        "saver_months": (1, 3),
    }
    req = levels._requirement(lv, facts)
    assert req["text"] and req["checks"]
    assert not all(c["met"] for c in req["checks"])


def test_level_4_with_goal_on_track(df_today, inc, bsk):
    goals = [{"on_track": True, "paused": False, "progress_pct": 10.0}]
    lv = levels.compute_levels(df_today, TODAY, inc, bsk, goals=goals)
    ladder = {step["level"]: step for step in lv["ladder"]}
    assert ladder[4]["reached"] is True
    assert lv["current"] == 2  # still capped by level 3


# --- Habits and forecast ---------------------------------------------------------


def test_habits_shape(df_today, inc, bsk):
    h = habits.compute_habits(df_today, TODAY, inc, bsk)
    assert h["impulse"]["bursts_per_month"] == 0.0
    assert h["spender_type"]["label"] in {
        "Weekend Treater",
        "Night Owl",
        "Impulse Buyer",
        "Payday Splurger",
        "Steady Planner",
    }
    assert 0 <= h["loyalty"]["hhi"] <= 1


def test_forecast_shape(df_today, inc, bsk):
    f = forecast.compute_forecast(df_today, TODAY, inc, bsk)
    assert f["buffer"] == 89.0
    assert f["safe_to_spend_week"] >= 0
    assert f["safe_to_save_today"] >= 0
    up = f["upcoming_bills"]
    assert [b["date"] for b in up] == sorted(b["date"] for b in up)
    assert any(b["merchant_id"] == "M_RENT" and b["date"] == "2026-11-01" for b in up)
    assert f["end_of_month"]["low"] <= f["end_of_month"]["expected"]
    assert f["end_of_month"]["expected"] <= f["end_of_month"]["high"]


def test_everything_json_serialisable(df_today, inc, bsk):
    out = {
        "income": inc,
        "baskets": bsk,
        "habits": habits.compute_habits(df_today, TODAY, inc, bsk),
        "forecast": forecast.compute_forecast(df_today, TODAY, inc, bsk),
        "whatif": whatif.compute_whatif(df_today, TODAY, inc, bsk),
        "levels": levels.compute_levels(df_today, TODAY, inc, bsk),
    }
    json.dumps(out)


def _no_bills(inc, partial_view):
    return {**inc, "bills": [], "partial_view": partial_view}


def test_level_1_reached_without_bills_on_a_partial_view(df_today, inc, bsk):
    # #28: bills paid from another bank are not visible on a partial view.
    lv = levels.compute_levels(df_today, TODAY, _no_bills(inc, True), bsk)
    ladder = {step["level"]: step for step in lv["ladder"]}
    assert ladder[1]["reached"] is True
    assert lv["current"] == 2


def test_level_1_without_bills_says_the_bill_is_missing(df_today, inc, bsk):
    lv = levels.compute_levels(df_today, TODAY, _no_bills(inc, False), bsk)
    assert lv["current"] == 0
    checks = {c["text"]: c["met"] for c in lv["next_requirement"]["checks"]}
    assert checks == {"Payday found": True, "A regular bill found": False}


def test_a_new_goal_with_nothing_saved_does_not_reach_level_4(df_today, inc, bsk):
    # A goal is "on track" on its first day (0% saved of 0% expected); live, an
    # accepted plan jumped CUST00124 from level 3 to 5 at once.
    goals = [{"on_track": True, "paused": False, "progress_pct": 0.0}]
    lv = levels.compute_levels(df_today, TODAY, inc, bsk, goals=goals)
    ladder = {step["level"]: step for step in lv["ladder"]}
    assert ladder[4]["reached"] is False


def test_level_4_check_says_nothing_is_saved_yet():
    facts = {"goals_active": 1, "goals_counting": 0}
    req = levels._requirement(4, facts)
    assert req["checks"] == [
        {"text": "1 active goal, 0 on track with money saved", "met": False}
    ]
