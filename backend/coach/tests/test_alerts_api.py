"""Alert API tests (context.md Tests, "Alert API tests")."""

from datetime import date

import pytest

from coach import services
from coach.gemini.system_prompt import FALLBACK_REPLY
from coach.models import Goal

from .conftest import AINO, TODAY, load_customer, response

pytestmark = pytest.mark.django_db

BROKE = "C-BROKE"
ALERT = "a-85"  # overdraft in the last 30 days


@pytest.fixture
def broke(db):
    """Test Aino with EUR 600 less on every balance: an overdraft alert."""
    from inferences.tests.fixtures import aino_df

    df = aino_df(until=TODAY)
    df["balance_after_eur"] = df["balance_after_eur"] - 600
    load_customer(df, BROKE)
    return BROKE


DEMO = BROKE


def alert_ids(client):
    return [a["id"] for a in client.get(f"/api/alerts/{DEMO}/").json()["alerts"]]


def test_alerts_sorted_by_priority(client, broke):
    alerts = client.get(f"/api/alerts/{DEMO}/").json()["alerts"]
    assert alerts
    priorities = [a["priority"] for a in alerts]
    assert priorities == sorted(priorities, reverse=True)


def test_snooze_hides_then_returns(client, broke, monkeypatch):
    assert ALERT in alert_ids(client)
    res = client.post(
        f"/api/alerts/{ALERT}/snooze/",
        {"customer_id": DEMO, "days": 3},
        content_type="application/json",
    )
    assert res.status_code == 200
    assert ALERT not in alert_ids(client)
    monkeypatch.setattr(services, "today", lambda: date(2026, 10, 21))
    assert ALERT in alert_ids(client)


def test_snooze_tool_hides_from_get_alerts(client, broke, fake_gemini):
    from coach.gemini.tools import ToolContext, call_tool

    ctx = ToolContext(DEMO)
    assert ALERT in [a["id"] for a in call_tool(ctx, "get_alerts", {})["alerts"]]
    call_tool(ctx, "snooze_alert", {"alert_id": ALERT, "days": 7})
    ids = [a["id"] for a in call_tool(ctx, "get_alerts", {})["alerts"]]
    assert ALERT not in ids


def test_accept_plan_without_confirmation_refused(client, aino, fake_gemini):
    action = {"type": "cut_category", "category": "takeaway", "pct": 0.2}
    fake_gemini(
        response(("accept_plan", {"actions": [action]})),
        response(("send_reply", {"text": "Accept?", "depth": 4, "cards": []})),
    )
    client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": "Accept plan", "depth": 4},
        content_type="application/json",
    )
    assert Goal.objects.count() == 0


def test_accept_plan_after_proposal_and_yes(client, aino, fake_gemini):
    action = {"type": "cut_category", "category": "takeaway", "pct": 0.2}
    fake_gemini(
        response(("accept_plan", {"actions": [action]})),
        response(("send_reply", {"text": "Accept?", "depth": 4, "cards": []})),
    )
    body = {"customer_id": AINO, "depth": 4}
    client.post(
        "/api/chat/",
        {**body, "message": "Make that a plan"},
        content_type="application/json",
    )
    fake_gemini(
        response(("accept_plan", {"actions": [action]})),
        response(("send_reply", {"text": "Saved.", "depth": 4, "cards": []})),
    )
    client.post(
        "/api/chat/",
        {**body, "message": "Yes, accept plan"},
        content_type="application/json",
    )
    goal = Goal.objects.get()
    assert goal.type == "plan" and goal.checklist[0]["action"]["category"] == "takeaway"


@pytest.mark.parametrize(
    "payload",
    [
        {"balance": -1, "interest_rate": 4, "years_left": 20},
        {"balance": 100000, "interest_rate": 25, "years_left": 20},
        {"balance": 100000, "interest_rate": 4, "years_left": 0},
        {"balance": 100000, "interest_rate": 4, "years_left": 41},
    ],
)
def test_loans_validation(client, aino, payload):
    res = client.post(
        "/api/loans/", {"customer_id": AINO, **payload}, content_type="application/json"
    )
    assert res.status_code == 400


def test_loans_valid_computes_stress_test(client, aino):
    res = client.post(
        "/api/loans/",
        {"customer_id": AINO, "balance": 150000, "interest_rate": 4, "years_left": 25},
        content_type="application/json",
    )
    assert res.status_code == 201
    stress = res.json()["mortgage"]["stress_test"]
    # context.md: stressed payment ~966.45, 48 % of 2,000 -> no alert.
    assert stress["stressed_payment"] == pytest.approx(966.45, abs=0.01)
    assert stress["ratio"] == pytest.approx(0.48, abs=0.01)
    assert stress["passes"] is True


# --- F4: the alert coach answers instead of falling back --------------------------


def _coach_reply(plan):
    if plan["steps"]:
        keep = ("text", "monthly_impact", "clears")
        steps = [{k: s[k] for k in keep} for s in plan["steps"]]
        return "Here is a plan.", [{"type": "plan", "steps": steps}]
    return plan["unclearable"][0]["why"], []


def _clear_alerts(client, fake_gemini, args):
    from coach.gemini.tools import ToolContext, call_tool

    plan = call_tool(ToolContext(BROKE), "suggest_fixes", args)
    text, cards = _coach_reply(plan)
    fake_gemini(
        response(("suggest_fixes", args)),
        response(("send_reply", {"text": text, "depth": 4, "cards": cards})),
    )
    body = client.post(
        "/api/chat/",
        {"customer_id": BROKE, "message": "Help me clear my alerts", "depth": 4},
        content_type="application/json",
    ).json()
    return plan, body


def test_clear_my_alerts_gives_a_plan_or_reason(client, broke, fake_gemini):
    plan, body = _clear_alerts(client, fake_gemini, {})
    assert body["text"] != FALLBACK_REPLY["text"]
    assert len(plan["steps"]) <= 3
    assert Goal.objects.count() == 0


def test_unclearable_alert_is_explained_not_failed(
    client, broke, fake_gemini, monkeypatch
):
    from coach import planner

    def stuck(df, profile, today):
        return profile["alerts"]

    monkeypatch.setattr(planner, "default_alert_runner", stuck)
    plan, body = _clear_alerts(client, fake_gemini, {"alert_ids": [ALERT]})
    assert plan["steps"] == []
    assert body["text"] == plan["unclearable"][0]["why"]
    assert Goal.objects.count() == 0
