"""F1 (handoff/Gemini_fix.md): a goal is saved at "Yes, save it".

Live repro (CUST02305): Gemini never called create_goal on the request turn,
so no proposal was stored and the "yes" could not confirm anything. These
tests pin the whole flow with Gemini mocked.
"""

import pytest

from coach.models import DemoCache, Goal

from .conftest import AINO, response

pytestmark = pytest.mark.django_db

GOAL = {
    "name": "House deposit",
    "amount": 20000,
    "date": "2028-12-01",
    "priority": "high",
}
CARD = {
    "type": "goal",
    "name": "House deposit",
    "target": 20000,
    "saved": 0,
    "target_date": "2028-12-01",
}


def _chat(client, message):
    return client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": message, "depth": 4},
        content_type="application/json",
    ).json()


def _reply(text, *cards):
    return response(("send_reply", {"text": text, "depth": 4, "cards": list(cards)}))


def _propose_then_confirm(client, fake_gemini, confirm_args=GOAL):
    fake_gemini(response(("create_goal", GOAL)), _reply("Shall I save it?", CARD))
    first = _chat(client, "Create a goal: House deposit, 20000 euros by 2028")
    fake_gemini(response(("create_goal", confirm_args)), _reply("Saved.", CARD))
    second = _chat(client, "Yes, save it")
    return first, second


def test_goal_is_saved_after_request_proposal_and_yes(client, aino, fake_gemini):
    first, second = _propose_then_confirm(client, fake_gemini)

    assert Goal.objects.count() == 1
    goal = Goal.objects.get()
    assert (goal.name, goal.target, goal.target_date.isoformat()) == (
        "House deposit",
        20000,
        "2028-12-01",
    )
    assert goal.priority == "high"
    assert [c["type"] for c in second["cards"]] == ["goal"]
    goals = client.get(f"/api/goals/?customer_id={AINO}").json()["active"]
    assert [g["name"] for g in goals] == ["House deposit"]


def test_yes_saves_the_proposed_goal_not_new_arguments(client, aino, fake_gemini):
    drifted = {**GOAL, "amount": 2000}
    _propose_then_confirm(client, fake_gemini, confirm_args=drifted)
    assert Goal.objects.get().target == 20000


def test_reply_may_repeat_numbers_the_user_said_earlier(client, aino, fake_gemini):
    question = {
        "type": "question",
        "question": "How important is it?",
        "options": ["High", "Medium", "Low"],
    }
    fake_gemini(_reply("Which priority?", question))
    _chat(client, "I want 20000 euros for a house deposit by December 2028")
    fake_gemini(_reply("A 20,000 euro house deposit by 2028, high priority?"))
    body = _chat(client, "High")
    assert body["text"].startswith("A 20,000 euro")


def test_reply_may_repeat_numbers_from_the_stored_proposal(client, aino, fake_gemini):
    fake_gemini(response(("create_goal", GOAL)), _reply("Shall I save it?", CARD))
    _chat(client, "Save a house deposit goal")
    fake_gemini(_reply("Just to check: 20,000 by 1 Dec 2028?"))
    body = _chat(client, "wait, how much was it?")
    assert body["text"].startswith("Just to check")


def test_demo_mode_never_caches_a_proposal(client, aino, fake_gemini, settings):
    settings.DEMO_MODE = True
    fake_gemini(response(("create_goal", GOAL)), _reply("Shall I save it?", CARD))
    _chat(client, "Create a goal: House deposit, 20000 euros by 2028")
    assert DemoCache.objects.count() == 0


def test_system_prompt_says_to_call_the_tool_to_propose():
    from coach.gemini.system_prompt import SYSTEM_PROMPT

    assert "first call only records the proposal" in SYSTEM_PROMPT
