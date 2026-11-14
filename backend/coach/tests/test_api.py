"""API tests with Gemini mocked (context.md Tests, section 2)."""

import pytest

from coach.gemini import router
from coach.gemini.system_prompt import FALLBACK_REPLY
from coach.models import Goal

from .conftest import response

pytestmark = pytest.mark.django_db

DEMO = "demo-aino"
PROFILE_KEYS = {
    "customer_id",
    "balance",
    "income",
    "baskets",
    "habits",
    "forecast",
    "whatif",
    "levels",
    "goals",
    "mortgage",
    "alerts",
}


def chat(client, message, depth=None):
    body = {"customer_id": DEMO, "message": message, "history": []}
    if depth:
        body["depth"] = depth
    return client.post("/api/chat/", body, content_type="application/json")


def test_home_returns_profile(client):
    res = client.get(f"/api/home/{DEMO}/")
    assert res.status_code == 200
    assert PROFILE_KEYS <= set(res.json())


def test_home_unknown_customer_404(client):
    assert client.get("/api/home/nobody/").status_code == 404


def test_customers_lists_demo(client):
    ids = [c["customer_id"] for c in client.get("/api/customers/").json()]
    assert DEMO in ids


def test_chat_tool_then_send_reply(client, fake_gemini):
    fake_gemini(
        response(("get_category_spend", {"category": "takeaway"})),
        response(
            (
                "send_reply",
                {
                    "text": "You spent EUR 90 on takeaway last month.",
                    "depth": 1,
                    "cards": [{"type": "number", "label": "Takeaway", "value": 90}],
                    "chips": ["Why so much?", "What if I cut it?"],
                },
            )
        ),
    )
    res = chat(client, "How much did I spend on takeaway last month?")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"text", "depth", "cards", "chips"}
    assert body["cards"][0]["value"] == 90


def test_no_send_reply_stops_after_5_rounds(client, fake_gemini):
    fake = fake_gemini(response(("get_baskets", {})))
    res = chat(client, "How much?", depth=1)
    assert res.json() == FALLBACK_REPLY
    assert len(fake.models.calls) == 5


def test_invented_number_retried_once_then_fallback(client, fake_gemini):
    bad = response(
        (
            "send_reply",
            {"text": "You can spend EUR 999 this week.", "depth": 1, "cards": []},
        )
    )
    fake = fake_gemini(response(("get_safe_to_spend", {})), bad, bad, bad)
    res = chat(client, "How much can I spend?", depth=1)
    assert res.json() == FALLBACK_REPLY
    # 1 tool round + first bad reply + one retry.
    assert len(fake.models.calls) == 3


def test_retry_succeeds_after_correction(client, fake_gemini):
    fake_gemini(
        response(("get_safe_to_spend", {})),
        response(("send_reply", {"text": "EUR 999", "depth": 1, "cards": []})),
        response(("send_reply", {"text": "EUR 64 this week.", "depth": 1})),
    )
    assert chat(client, "Safe?", depth=1).json()["text"] == "EUR 64 this week."


def test_unknown_card_type_removed(client, fake_gemini):
    fake_gemini(
        response(
            (
                "send_reply",
                {
                    "text": "Here you go.",
                    "depth": 1,
                    "cards": [{"type": "hologram"}, {"type": "number", "value": 1}],
                    "chips": ["a", "b", "c", "d"],
                },
            )
        )
    )
    body = chat(client, "hi", depth=1).json()
    assert [c["type"] for c in body["cards"]] == ["number"]
    assert len(body["chips"]) == 3


def _create_goal_call():
    return (
        "create_goal",
        {"name": "Japan", "amount": 1500, "date": "2027-06-01"},
    )


def _ok_reply():
    return ("send_reply", {"text": "Shall I save it?", "depth": 4, "cards": []})


def test_create_goal_without_confirmation_refused(client, fake_gemini):
    fake_gemini(response(_create_goal_call()), response(_ok_reply()))
    chat(client, "I want EUR 1,500 for Japan by June 2027", depth=4)
    assert Goal.objects.count() == 0


def test_create_goal_after_confirmation_recomputes_profile(client, fake_gemini):
    fake_gemini(response(_create_goal_call()), response(_ok_reply()))
    chat(client, "I want EUR 1,500 for Japan by June 2027", depth=4)
    fake_gemini(response(_create_goal_call()), response(_ok_reply()))
    chat(client, "Yes, save it", depth=4)
    assert Goal.objects.count() == 1
    profile = client.get(f"/api/home/{DEMO}/").json()
    new = [g for g in profile["goals"]["active"] if g.get("db")]
    assert new and new[0]["name"] == "Japan"
    assert "progress_pct" in new[0] and "on_track" in new[0]
    ladder = {r["level"]: r for r in profile["levels"]["ladder"]}
    assert ladder[4]["reached"] in (True, False)


def test_goal_form_creates_and_recomputes(client):
    res = client.post(
        "/api/goals/",
        {"customer_id": DEMO, "name": "Bike", "amount": 300, "date": "2027-03-01"},
        content_type="application/json",
    )
    assert res.status_code == 201
    names = [g["name"] for g in res.json()["profile"]["goals"]["active"]]
    assert "Bike" in names


@pytest.mark.parametrize(
    "amount,date", [(0, "2027-03-01"), (100, "2026-01-01"), (-5, "2027-03-01")]
)
def test_goal_form_validation(client, amount, date):
    res = client.post(
        "/api/goals/",
        {"customer_id": DEMO, "name": "Bad", "amount": amount, "date": date},
        content_type="application/json",
    )
    assert res.status_code == 400


def test_pause_goal_never_off_track(client):
    goal = client.post(
        "/api/goals/",
        {"customer_id": DEMO, "name": "Bike", "amount": 300, "date": "2027-03-01"},
        content_type="application/json",
    ).json()["goal"]
    res = client.patch(
        f"/api/goals/{goal['id']}/", {"paused": True}, content_type="application/json"
    )
    assert res.status_code == 200
    g = Goal.objects.get(pk=goal["id"])
    assert g.paused and g.paused_at is not None
    active = [x for x in res.json()["profile"]["goals"]["active"] if x.get("db")]
    assert active[0]["on_track"]


def test_rate_goal_weight(client):
    for up in (True, True, False):
        res = client.post(
            "/api/goals/rec-safety-net/rate/",
            {"customer_id": DEMO, "goal_type": "safety_net", "up": up},
            content_type="application/json",
        )
    assert res.json()["weight"] == pytest.approx(3 / 5)


def test_chip_with_depth_skips_router(client, fake_gemini, monkeypatch):
    called = []
    monkeypatch.setattr(router, "route", lambda *a, **k: called.append(1) or 2)
    fake_gemini(response(("send_reply", {"text": "ok", "depth": 2, "cards": []})))
    chat(client, "Show me why", depth=2)
    assert called == []
    chat(client, "Something without keywords")
    assert called == [1]


def test_offline_reply_without_key(client):
    body = chat(client, "Safe to spend?").json()
    assert body["cards"][0]["value"] == 64


def test_demo_cache(client, fake_gemini, settings):
    settings.DEMO_MODE = True
    fake = fake_gemini(response(("send_reply", {"text": "Hi!", "depth": 1})))
    chat(client, "When is payday?")
    chat(client, "when is PAYDAY")
    assert len(fake.models.calls) == 1


def test_router_rules():
    assert router.rule_depth("How much did I spend on taxis?") == 1
    assert router.rule_depth("Why is my safe to spend so low?") == 2
    assert router.rule_depth("What if I cut dining out by 20%?") == 3
    assert router.rule_depth("Help me buy a flat") == 4
    assert router.rule_depth("Should I buy Bitcoin?") is None
