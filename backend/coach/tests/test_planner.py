"""Planner tests (context.md Tests, "Planner tests (alert coach)")."""

import copy
import json

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
