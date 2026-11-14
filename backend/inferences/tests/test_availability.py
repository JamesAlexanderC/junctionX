"""Availability flags: only insights the customer's data supports are shown."""

import json

from inferences.availability import RULES, available
from inferences.profile import build_profile
from inferences.tests.fixtures import TODAY, aino_df

CUSTOMER = {"customer_id": "aino", "age": 24, "postal_code": "00510"}


def test_every_item_has_a_flag_on_aino():
    p = build_profile(aino_df(), CUSTOMER, TODAY)
    json.dumps(p)
    assert set(p["availability"]) == set(RULES)
    for item, flag in p["availability"].items():
        assert flag["available"] is (flag["reason"] is None), item
        assert flag["inferences"], item


def test_aino_supported_and_unsupported_items():
    p = build_profile(aino_df(), CUSTOMER, TODAY)
    a = p["availability"]
    for item in (
        "balance",
        "income.payday",
        "income.monthly_income",
        "income.bills",
        "income.subscriptions",
        "baskets",
        "baskets.saver",
        "forecast.safe_to_spend_week",
        "habits.spender_type",
    ):
        assert a[item]["available"], item
    # One account, no peer table, no fitted model, no loans: not shown.
    for item in (
        "multibank",
        "benchmarks.age",
        "mortgage.readiness",
        "mortgage.loan_burden",
        "mortgage.stress_test",
    ):
        assert not a[item]["available"], item
        assert a[item]["reason"], item


def test_empty_customer_shows_nothing_invented():
    p = build_profile(None, {"customer_id": "x"}, TODAY)
    assert p["balance"] is None
    assert p["habits"]["spender_type"]["label"] is None
    assert p["habits"]["loyalty"]["label"] is None
    assert not any(lv["reached"] for lv in p["levels"]["ladder"])
    shown = [k for k, v in p["availability"].items() if v["available"]]
    assert shown == []
    assert not available(p, "income.payday")


def test_home_goal_has_no_guessed_price():
    from inferences import goals

    det = goals._detect_home(
        {"bills": [{"category": "housing"}]},
        {"age": 30, "postal_code": "00510"},
        {"readiness": {"score": 0.6}},
    )
    assert det["target"] is None
    assert det["needs"] == "target_price"
