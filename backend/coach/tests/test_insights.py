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


def test_empty_current_month_falls_back_to_last_full_month():
    p = sample()
    p["baskets"]["totals"] = {k: 0.0 for k in p["baskets"]["totals"]}
    item = next(i for i in insights.insights(p) if i["key"] == "baskets")
    assert item["title"] == "Where the money went (2026-09)"
    assert item["value"]["surprise"] == 400.0


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


def test_end_of_month_hidden_on_the_last_day():
    p = sample()
    p["forecast"]["end_of_month"] = {"expected": 500.0, "low": 500.0, "high": 500.0}
    assert "end_of_month" not in {i["key"] for i in insights.insights(p)}


def test_seasonal_insight_names_the_month():
    # Live: "Last year 2026-10 cost 1.4x a usual month".
    p = copy.deepcopy(sample())
    p["forecast"]["seasonal"] = {
        "warn": True,
        "next_month": "2026-11",
        "ratio": 1.4,
        "pot": 120.0,
    }
    item = next(i for i in insights.insights(p) if i["key"] == "seasonal")
    assert item["text"].startswith("Last November cost 1.4x a usual month.")
    assert "2026-11" not in item["text"]
