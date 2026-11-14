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


@pytest.mark.parametrize(
    "message",
    ["do not save it", "don't save it", "yes, but change the amount", "not okay"],
)
def test_negative_or_ambiguous_confirmation_saves_nothing(
    client, aino, fake_gemini, message
):
    fake_gemini(response(("create_goal", GOAL)), _reply("Shall I save it?", CARD))
    _chat(client, "Create a house deposit goal")
    fake_gemini(response(("create_goal", GOAL)), _reply("Let us check first."))
    _chat(client, message)
    assert Goal.objects.count() == 0


def test_repeated_tool_calls_consume_confirmation_once(client, aino, fake_gemini):
    fake_gemini(response(("create_goal", GOAL)), _reply("Shall I save it?", CARD))
    _chat(client, "Create a house deposit goal")
    fake_gemini(
        response(("create_goal", GOAL), ("create_goal", GOAL)),
        _reply("Saved."),
    )
    _chat(client, "Yes, save it")
    assert Goal.objects.count() == 1
    from coach.models import ChatTurn

    assert ChatTurn.objects.order_by("-id").first().pending == {}


def test_stale_context_cannot_reuse_persisted_confirmation(aino):
    from coach.gemini.tools import ToolContext, call_tool
    from coach.models import ChatTurn

    pending = {"create_goal": GOAL}
    previous = ChatTurn.objects.create(
        customer_id=AINO, message="Goal", pending=pending
    )
    contexts = [
        ToolContext(AINO, "yes", previous_pending=pending, previous_turn_id=previous.id)
        for _ in range(2)
    ]
    for ctx in contexts:
        call_tool(ctx, "create_goal", GOAL)
    assert Goal.objects.count() == 1
    previous.refresh_from_db()
    assert previous.pending == {}


def test_failed_write_does_not_consume_confirmation(aino, monkeypatch):
    from coach import services
    from coach.gemini.tools import ToolContext, call_tool
    from coach.models import ChatTurn

    pending = {"create_goal": GOAL}
    previous = ChatTurn.objects.create(
        customer_id=AINO, message="Goal", pending=pending
    )
    ctx = ToolContext(
        AINO, "yes", previous_pending=pending, previous_turn_id=previous.id
    )

    def failed_refresh(customer_id):
        raise RuntimeError("Profile rebuild failed")

    monkeypatch.setattr(services, "refresh_profile", failed_refresh)
    assert "error" in call_tool(ctx, "create_goal", GOAL)
    assert Goal.objects.count() == 0
    previous.refresh_from_db()
    assert previous.pending == pending
    assert ctx.previous_pending == pending


@pytest.mark.parametrize("message", ["Yes", "Yes, save it!", "Yes, go ahead", "joo"])
def test_explicit_confirmations_are_accepted(message):
    from coach.gemini.tools import ToolContext

    assert ToolContext(AINO, message, {"create_goal": GOAL}).user_confirmed(
        "create_goal"
    )


def test_slider_reference_date_is_set_by_server(client, aino, fake_gemini):
    fake_gemini(
        response(("simulate_cut", {"category": "takeaway", "pct": 0.2})),
        _reply(
            "Try it.",
            {
                "type": "slider",
                "category": "takeaway",
                "monthly_spend": 90,
                "pct": 20,
                "as_of": "2099-01-01",
            },
        ),
    )
    assert _chat(client, "Cut takeaway")["cards"][0]["as_of"] == "2026-10-18"


def test_cached_sliders_receive_reference_date(client, aino, settings, user):
    settings.DEMO_MODE = True
    from coach.models import Conversation

    conversation = Conversation.objects.create(owner=user, customer_id=AINO)
    cached = DemoCache.objects.create(
        conversation=conversation,
        customer_id=AINO,
        question="cut takeaway",
        reply={
            "text": "Try it.",
            "depth": 3,
            "cards": [
                {
                    "type": "slider",
                    "category": "takeaway",
                    "monthly_spend": 90,
                    "pct": 20,
                }
            ],
        },
    )
    assert _chat(client, "Cut takeaway")["cards"][0]["as_of"] == "2026-10-18"
    cached.refresh_from_db()
    assert "as_of" not in cached.reply["cards"][0]
