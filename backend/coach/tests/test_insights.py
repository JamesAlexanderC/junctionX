"""GET /api/insights/: only insights the customer's data supports."""

import copy
import json

import pytest

from coach import insights

from .conftest import AINO, FIXTURES

FIELDS = {"key", "inference", "title", "value", "unit", "text", "section"}


def sample():
    return json.loads((FIXTURES / "profile_demo.json").read_text())


@pytest.mark.django_db
def test_endpoint_returns_supported_insights(client, aino):
    res = client.get(f"/api/insights/{AINO}/")
    assert res.status_code == 200
    body = res.json()
    assert body["customer_id"] == AINO and body["as_of"] == "2026-10-18"
    keys = {i["key"] for i in body["insights"]}
    assert {"safe_to_spend", "payday", "monthly_income", "level"} <= keys
    for item in body["insights"]:
        assert FIELDS <= set(item)
        assert item["value"] is not None and item["text"]


def test_unsupported_sections_are_omitted():
    p = sample()
    p["mortgage"]["readiness"]["score"] = None
    p["benchmarks"]["age"] = []
    p["benchmarks"]["area"] = []
    p["income"]["payday"]["found"] = False
    p["forecast"]["safe_to_spend_week"] = None
    p["alerts"] = []
    p["goals"]["detected"] = []
    keys = {i["key"] for i in insights.insights(p)}
    for gone in (
        "mortgage_readiness",
        "benchmark_age",
        "benchmark_area",
        "payday",
        "safe_to_spend",
    ):
        assert gone not in keys
    assert not [k for k in keys if k.startswith("a-") or k.startswith("goal_det")]


def test_availability_map_is_respected():
    p = sample()
    p["availability"] = {
        "habits.spender_type": {"available": False, "reason": "too little data"},
        "income.monthly_income": {"available": True},
    }
    keys = {i["key"] for i in insights.insights(p)}
    assert "spender_type" not in keys
    assert "monthly_income" in keys


def test_baskets_left_to_basket_panel():
    assert "baskets" not in {i["key"] for i in insights.insights(sample())}


def test_basket_summary_picks_computed_fields():
    p = copy.deepcopy(sample())
    out = insights.basket_summary(p)
    assert out["month"] == "2026-10"
    assert out["total"] == 1212.99
    assert [b["key"] for b in out["buckets"]] == ["essential", "leaky", "saver"]
    leaky = out["buckets"][1]
    assert leaky["name"] == "Leaky"
    assert leaky["total"] == 172.99
    assert leaky["share"] == 14.3
    assert leaky["trend"] == 1.3
    assert leaky["categories"][0] == {"category": "takeaway", "total": 90.0}
    assert out["monthly_saving"] == 150.0


def test_basket_summary_falls_back_to_last_full_month():
    p = copy.deepcopy(sample())
    p["baskets"]["totals"] = {k: 0.0 for k in p["baskets"]["totals"]}
    out = insights.basket_summary(p)
    assert out["month"] == "2026-09"
    surprise = next(b for b in out["buckets"] if b["key"] == "surprise")
    assert surprise["total"] == 400.0
    assert surprise["trend"] is None  # trend is for the current month only


def test_basket_summary_empty_profile():
    assert insights.basket_summary({}) == {
        "month": None,
        "total": 0,
        "buckets": [],
        "monthly_essentials": None,
        "monthly_saving": None,
    }


def test_zero_and_unflagged_values_are_omitted():
    p = copy.deepcopy(sample())
    p["baskets"]["monthly_saving"] = 0
    p["forecast"]["surprise_fund_monthly"] = 0
    p["forecast"]["danger_days"] = []
    p["forecast"]["seasonal"]["warn"] = False
    keys = {i["key"] for i in insights.insights(p)}
    assert not keys & {"saver", "surprise_fund", "danger_days", "seasonal"}
    assert not [k for k in keys if k.startswith("habit_")]  # no habit flagged


def test_alerts_first_with_severity():
    out = insights.insights(sample())
    assert out[0]["section"] == "alerts" and out[0]["severity"] == "blue"


def test_empty_profile_has_no_insights():
    assert insights.insights({}) == []


def test_active_goals_left_to_goal_panel():
    p = sample()
    assert p["goals"]["active"]
    goal_rows = [i for i in insights.insights(p) if i["section"] == "goals"]
    assert all(i["title"] == "Goal idea" for i in goal_rows)


def test_goal_summary_picks_computed_fields():
    p = sample()
    p["goals"]["active"][0]["tip"] = {"text": "Cut takeaway", "shortfall": 40.0}
    p["goals"]["active"][0]["funding_cuts"] = [{"category": "x"}]
    out = insights.goal_summary(p)
    goal = out["active"][0]
    src = sample()["goals"]["active"][0]
    for key in ("name", "target", "saved", "progress_pct", "monthly_needed"):
        assert goal[key] == src[key]
    assert goal["tip"] == {"text": "Cut takeaway", "shortfall": 40.0}
    assert "funding_cuts" not in goal
    assert out["completed"] == []


def test_goal_summary_empty_profile():
    assert insights.goal_summary({}) == {"active": [], "completed": [], "clash": None}


def test_end_of_month_hidden_on_the_last_day():
    p = sample()
    p["forecast"]["end_of_month"] = {"expected": 500.0, "low": 500.0, "high": 500.0}
    assert "end_of_month" not in {i["key"] for i in insights.insights(p)}
