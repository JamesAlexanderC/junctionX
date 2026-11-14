"""API tests with Gemini mocked (context.md Tests, section 2).

The customer is Test Aino loaded into the test DB; every profile is built by
the real inference engine, so expected numbers are read from the tools.
"""

import pytest

from coach import services
from coach.gemini import loop, router
from coach.gemini.system_prompt import FALLBACK_REPLY
from coach.gemini.tools import ToolContext, call_tool
from coach.models import Goal, Profile

from .conftest import AINO, response

pytestmark = pytest.mark.django_db

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
    body = {"customer_id": AINO, "message": message, "history": []}
    if depth:
        body["depth"] = depth
    return client.post("/api/chat/", body, content_type="application/json")


def safe_to_spend():
    return call_tool(ToolContext(AINO), "get_safe_to_spend", {})["safe_to_spend_week"]


def test_home_builds_profile_from_db(client, aino):
    res = client.get(f"/api/home/{AINO}/")
    assert res.status_code == 200
    body = res.json()
    assert PROFILE_KEYS <= set(body)
    assert body["today"] == "2026-10-18"
    assert body["income"]["payday"]["found"]
    row = Profile.objects.get(customer_id=AINO)
    assert row.built_with == services.profile_version()


def test_home_unknown_customer_404(client, aino):
    assert client.get("/api/home/nobody/").status_code == 404
    assert client.get("/api/insights/nobody/").status_code == 404


def test_no_demo_customer(client, db):
    assert client.get("/api/home/demo-aino/").status_code == 404
    assert client.get("/api/customers/").json() == []


def test_customers_search_and_limit(client, aino):
    from .conftest import load_customer
    from inferences.tests.fixtures import aino_df

    load_customer(aino_df().head(5), "C-OTHER", age=40, postal_code="33100")
    ids = [c["customer_id"] for c in client.get("/api/customers/").json()]
    assert ids == ["C-AINO", "C-OTHER"]
    found = client.get("/api/customers/?q=33").json()
    assert found == [
        {"customer_id": "C-OTHER", "customer_age": 40, "customer_postal_code": "33100"}
    ]
    assert len(client.get("/api/customers/?limit=1").json()) == 1


def test_chat_without_key_is_503(client, aino):
    res = chat(client, "Safe to spend?")
    assert res.status_code == 503
    assert res.json() == {"error": "Gemini is not configured: set GEMINI_API_KEY"}


def test_chat_unknown_customer_404(client, db, fake_gemini):
    fake_gemini(response(("send_reply", {"text": "hi", "depth": 1})))
    res = client.post(
        "/api/chat/",
        {"customer_id": "nobody", "message": "hi"},
        content_type="application/json",
    )
    assert res.status_code == 404


def test_chat_tool_then_send_reply(client, aino, fake_gemini):
    spend = call_tool(
        ToolContext(AINO), "get_category_spend", {"category": "groceries"}
    )
    assert spend["available"] and spend["total"] > 0
    total = spend["total"]
    fake_gemini(
        response(("get_category_spend", {"category": "groceries"})),
        response(
            (
                "send_reply",
                {
                    "text": f"You spent EUR {total:g} on groceries last month.",
                    "depth": 1,
                    "cards": [{"type": "number", "label": "Groceries", "value": total}],
                    "chips": ["Why so much?", "What if I cut it?"],
                },
            )
        ),
    )
    res = chat(client, "How much did I spend on groceries last month?")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"text", "depth", "cards", "chips"}
    assert body["cards"][0]["value"] == total


def test_unsupported_category_is_unavailable(aino):
    out = call_tool(ToolContext(AINO), "get_category_spend", {"category": "casino"})
    assert out["available"] is False and out["reason"]


def test_no_send_reply_stops_after_max_rounds(client, aino, fake_gemini):
    fake = fake_gemini(response(("get_baskets", {})))
    res = chat(client, "How much?", depth=1)
    assert res.json() == FALLBACK_REPLY
    assert len(fake.models.calls) == loop.MAX_ROUNDS


def test_invented_number_retried_once_then_fallback(client, aino, fake_gemini):
    bad = response(
        (
            "send_reply",
            {"text": "You can spend EUR 98765 this week.", "depth": 1, "cards": []},
        )
    )
    fake = fake_gemini(response(("get_safe_to_spend", {})), bad, bad, bad)
    res = chat(client, "How much can I spend?", depth=1)
    assert res.json() == FALLBACK_REPLY
    # 1 tool round + first bad reply + one retry.
    assert len(fake.models.calls) == 3


def test_retry_succeeds_after_correction(client, aino, fake_gemini):
    value = safe_to_spend()
    good = f"EUR {value:g} this week."
    fake_gemini(
        response(("get_safe_to_spend", {})),
        response(("send_reply", {"text": "EUR 98765", "depth": 1, "cards": []})),
        response(("send_reply", {"text": good, "depth": 1})),
    )
    assert chat(client, "Safe?", depth=1).json()["text"] == good


def test_unknown_card_type_removed(client, aino, fake_gemini):
    fake_gemini(
        response(
            (
                "send_reply",
                {
                    "text": "Here you go.",
                    "depth": 1,
                    "cards": [
                        {"type": "hologram"},
                        {"type": "number", "label": "Count", "value": 1},
                    ],
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


def _active(profile, name):
    return [g for g in profile["goals"]["active"] if g["name"] == name]


def test_create_goal_without_confirmation_refused(client, aino, fake_gemini):
    fake_gemini(response(_create_goal_call()), response(_ok_reply()))
    chat(client, "I want EUR 1,500 for Japan by June 2027", depth=4)
    assert Goal.objects.count() == 0


def test_create_goal_after_confirmation_recomputes_profile(client, aino, fake_gemini):
    fake_gemini(response(_create_goal_call()), response(_ok_reply()))
    chat(client, "I want EUR 1,500 for Japan by June 2027", depth=4)
    fake_gemini(response(_create_goal_call()), response(_ok_reply()))
    chat(client, "Yes, save it", depth=4)
    assert Goal.objects.count() == 1
    profile = client.get(f"/api/home/{AINO}/").json()
    new = _active(profile, "Japan")
    assert new and "progress_pct" in new[0] and "on_track" in new[0]
    ladder = {r["level"]: r for r in profile["levels"]["ladder"]}
    assert ladder[4]["reached"] in (True, False)


def test_goal_form_creates_and_recomputes(client, aino):
    res = client.post(
        "/api/goals/",
        {"customer_id": AINO, "name": "Bike", "amount": 300, "date": "2027-03-01"},
        content_type="application/json",
    )
    assert res.status_code == 201
    assert _active(res.json()["profile"], "Bike")


def test_goal_form_unknown_customer_404(client, db):
    res = client.post(
        "/api/goals/",
        {"customer_id": "nobody", "name": "Bike", "amount": 300, "date": "2027-03-01"},
        content_type="application/json",
    )
    assert res.status_code == 404


@pytest.mark.parametrize(
    "amount,date", [(0, "2027-03-01"), (100, "2026-01-01"), (-5, "2027-03-01")]
)
def test_goal_form_validation(client, aino, amount, date):
    res = client.post(
        "/api/goals/",
        {"customer_id": AINO, "name": "Bad", "amount": amount, "date": date},
        content_type="application/json",
    )
    assert res.status_code == 400


def test_pause_goal_never_off_track(client, aino):
    goal = client.post(
        "/api/goals/",
        {"customer_id": AINO, "name": "Bike", "amount": 300, "date": "2027-03-01"},
        content_type="application/json",
    ).json()["goal"]
    res = client.patch(
        f"/api/goals/{goal['id']}/", {"paused": True}, content_type="application/json"
    )
    assert res.status_code == 200
    g = Goal.objects.get(pk=goal["id"])
    assert g.paused and g.paused_at is not None
    assert _active(res.json()["profile"], "Bike")[0]["on_track"]


def test_rate_goal_weight(client, aino):
    for up in (True, True, False):
        res = client.post(
            "/api/goals/rec-safety-net/rate/",
            {"customer_id": AINO, "goal_type": "safety_net", "up": up},
            content_type="application/json",
        )
    assert res.json()["weight"] == pytest.approx(3 / 5)


def test_chip_with_depth_skips_router(client, aino, fake_gemini, monkeypatch):
    called = []
    monkeypatch.setattr(router, "route", lambda *a, **k: called.append(1) or 2)
    fake_gemini(response(("send_reply", {"text": "ok", "depth": 2, "cards": []})))
    chat(client, "Show me why", depth=2)
    assert called == []
    chat(client, "Something without keywords")
    assert called == [1]


def test_reply_cache_only_stores_real_answers(client, aino, fake_gemini, settings):
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


def test_tool_respects_availability_flags(aino):
    # No mortgage model is fitted in the test DB, so readiness is unavailable.
    out = call_tool(ToolContext(AINO), "get_mortgage_readiness", {})
    assert out["available"] is False and out["item"] == "mortgage.readiness"
    assert out["reason"]
