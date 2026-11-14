"""Alert API tests (context.md Tests, "Alert API tests")."""

from datetime import date

import pytest

from coach import services
from coach.models import Goal

from .conftest import response

pytestmark = pytest.mark.django_db

DEMO = "demo-aino"
ALERT = "a-89"


def alert_ids(client):
    return [a["id"] for a in client.get(f"/api/alerts/{DEMO}/").json()["alerts"]]


def test_alerts_sorted_by_priority(client):
    alerts = client.get(f"/api/alerts/{DEMO}/").json()["alerts"]
    priorities = [a["priority"] for a in alerts]
    assert priorities == sorted(priorities, reverse=True)


def test_snooze_hides_then_returns(client, monkeypatch):
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


def test_snooze_tool_hides_from_get_alerts(client, fake_gemini):
    from coach.gemini.tools import ToolContext, call_tool

    ctx = ToolContext(DEMO)
    call_tool(ctx, "snooze_alert", {"alert_id": ALERT, "days": 7})
    ids = [a["id"] for a in call_tool(ctx, "get_alerts", {})["alerts"]]
    assert ALERT not in ids


def test_accept_plan_without_confirmation_refused(client, fake_gemini):
    action = {"type": "cut_category", "category": "takeaway", "pct": 0.2}
    fake_gemini(
        response(("accept_plan", {"actions": [action]})),
        response(("send_reply", {"text": "Accept?", "depth": 4, "cards": []})),
    )
    client.post(
        "/api/chat/",
        {"customer_id": DEMO, "message": "Accept plan", "depth": 4},
        content_type="application/json",
    )
    assert Goal.objects.count() == 0


def test_accept_plan_after_proposal_and_yes(client, fake_gemini):
    action = {"type": "cut_category", "category": "takeaway", "pct": 0.2}
    fake_gemini(
        response(("accept_plan", {"actions": [action]})),
        response(("send_reply", {"text": "Accept?", "depth": 4, "cards": []})),
    )
    body = {"customer_id": DEMO, "depth": 4}
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
def test_loans_validation(client, payload):
    res = client.post(
        "/api/loans/", {"customer_id": DEMO, **payload}, content_type="application/json"
    )
    assert res.status_code == 400


def test_loans_valid_computes_stress_test(client):
    res = client.post(
        "/api/loans/",
        {"customer_id": DEMO, "balance": 150000, "interest_rate": 4, "years_left": 25},
        content_type="application/json",
    )
    assert res.status_code == 201
    stress = res.json()["mortgage"]["stress_test"]
    # context.md: stressed payment ~966.45, 48 % of 2,000 -> no alert.
    assert stress["stressed_payment"] == pytest.approx(966.45, abs=0.01)
    assert stress["dsti_stress"] == pytest.approx(0.483, abs=0.001)
    assert stress["fires"] is False
