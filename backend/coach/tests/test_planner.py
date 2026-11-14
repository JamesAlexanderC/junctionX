"""Planner tests (context.md Tests, "Planner tests (alert coach)")."""

import copy
import json
import re

import pytest
from pathlib import Path

from coach import planner

TODAY_STR = "2026-10-18"


def base_profile():
    path = Path(__file__).parent / "fixtures" / "profile_demo.json"
    p = json.loads(path.read_text())
    p["goals"]["active"] = []  # keep goal actions out of the scripted test
    p["alerts"] = [
        {"id": "danger", "severity": "amber", "impact_date": "2026-10-23"},
        {"id": "goal_off", "severity": "amber", "impact_date": "2026-11-17"},
        {"id": "creep", "severity": "blue", "impact_date": "2026-11-17"},
        {"id": "similar_subs", "severity": "blue", "impact_date": "2026-11-17"},
    ]
    for a in p["alerts"]:
        a["priority"] = None
    return p


def fake_rules(df, profile, today):
    """Leaky total > 155 fires three alerts; two same-MCC subs fire one."""
    out = []
    by_id = {a["id"]: a for a in base_profile()["alerts"]}
    if profile["baskets"]["totals"]["leaky"] > 155:
        out += [by_id["danger"], by_id["goal_off"], by_id["creep"]]
    mccs = [s["mcc_code"] for s in profile["income"]["subscriptions"]]
    if len(mccs) != len(set(mccs)):
        out.append(by_id["similar_subs"])
    if profile.get("balance", 0) < 100:
        out.append({"id": "low", "severity": "red", "impact_date": TODAY_STR})
    return out


def run(profile=None, **kw):
    profile = profile or base_profile()
    return planner.suggest_fixes(
        profile, profile["alerts"], run_alerts=fake_rules, **kw
    )


def test_takeaways_first_then_subscription():
    plan = run()
    steps = plan["steps"]
    assert len(steps) == 2
    first, second = steps
    assert first["action"]["type"] == "cut_category"
    assert first["action"]["category"] == "takeaway"
    assert first["action"]["pct"] == 0.2
    assert first["score"] == pytest.approx(0.25, abs=0.001)
    assert set(first["clears"]) == {"danger", "goal_off", "creep"}
    assert second["action"]["type"] == "cancel_subscription"
    assert second["score"] == pytest.approx(0.033, abs=0.001)
    assert plan["still_open"] == []


def test_simulated_plan_clears_exactly_what_planner_said():
    profile = base_profile()
    plan = run(profile)
    actions = [s["action"] for s in plan["steps"]]
    claimed = {i for s in plan["steps"] for i in s["clears"]}
    sim = planner.simulate_plan(
        profile, actions, profile["alerts"], run_alerts=fake_rules
    )
    assert set(sim["cleared"]) == claimed
    assert sim["after"]["safe_to_spend"] > sim["before"]["safe_to_spend"]


def test_never_suggests_useless_action_or_more_than_3_steps():
    many = base_profile()
    plan = run(many, max_steps=3)
    assert len(plan["steps"]) <= 3
    for step in plan["steps"]:
        assert step["clears"]


def test_nothing_clearable_returns_no_steps():
    profile = base_profile()
    plan = planner.suggest_fixes(
        profile, profile["alerts"], run_alerts=lambda d, p, t: profile["alerts"]
    )
    assert plan["steps"] == []


def test_saver_to_buffer_only_with_red_alert():
    profile = base_profile()
    kinds = {a["type"] for a in planner.candidate_actions(profile, profile["alerts"])}
    assert "move_saver_to_buffer" not in kinds
    red = copy.deepcopy(profile["alerts"]) + [{"id": "low", "severity": "red"}]
    kinds = {a["type"] for a in planner.candidate_actions(profile, red)}
    assert "move_saver_to_buffer" in kinds


def test_apply_action_does_not_mutate_input():
    profile = base_profile()
    before = copy.deepcopy(profile)
    planner.apply_action(
        profile,
        {
            "type": "cut_category",
            "category": "takeaway",
            "pct": 0.2,
            "monthly_impact": 18.0,
        },
    )
    assert profile == before


# --- F4: explain alerts nothing can clear (handoff/Gemini_fix.md) -----------------


def _stuck(profile):
    """Every alert stays open whatever the planner tries."""
    return planner.suggest_fixes(
        profile, profile["alerts"], run_alerts=lambda d, p, t: profile["alerts"]
    )


def test_every_open_alert_gets_a_reason():
    profile = base_profile()
    plan = _stuck(profile)
    reasons = {r["id"]: r for r in plan["unclearable"]}
    assert set(reasons) == {a["id"] for a in profile["alerts"]}
    for r in reasons.values():
        # #24: plain words, no planner internals ("none of the 9 changes").
        assert "the most any of them saves is EUR" in r["why"]
        assert not re.search(r"\b\d+ changes\b", r["why"])
        assert r["options"]


def test_tight_days_reason_names_the_bill_and_the_balance():
    profile = base_profile()
    profile["balance"] = 2273.70
    profile["forecast"]["upcoming_bills"] = [
        {"date": "2026-10-05", "name": "Housing", "amount": 2266.98},
        {"date": "2026-11-05", "name": "Later", "amount": 999.0},
    ]
    profile["alerts"] = [
        {
            "id": "a-20",
            "inference": 20,
            "severity": "amber",
            "title": "Tight days ahead",
            "impact_date": "2026-10-05",
            "priority": None,
        }
    ]
    (reason,) = _stuck(profile)["unclearable"]
    assert "Housing of EUR 2,266.98 is due on 2026-10-05" in reason["why"]
    assert "EUR 2,273.70" in reason["why"]
    assert "Later" not in reason["why"]
    assert any("Housing" in o for o in reason["options"])


def test_reason_without_any_possible_change():
    profile = base_profile()
    profile["baskets"]["leaky_categories"] = []
    profile["income"]["subscriptions"] = []
    profile["income"]["possibly_unused"] = []
    profile["goals"]["active"] = []
    profile["baskets"]["totals"]["saver"] = 0
    plan = planner.suggest_fixes(
        profile, profile["alerts"], run_alerts=lambda d, p, t: profile["alerts"]
    )
    assert "nothing the coach can change" in plan["unclearable"][0]["why"]


def test_cleared_alerts_need_no_reason():
    assert run()["unclearable"] == []
