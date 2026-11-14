"""Conversational replies (A, B, C, F agreed with Will).

A: what the coach showed (cards) is in the history and the open alerts are
   in the profile summary, so "looks familiar" has something to refer to.
B: the coach may repeat numbers it already said in the last turns.
C: small talk, thanks, acknowledgements and feelings are answered in one
   round without the router or data tools; never when a proposal waits.
F: run_evals has multi-turn conversation flows.
"""

import json

import pytest

from coach import services
from coach.gemini import loop, router
from coach.gemini.cards import card_summary
from coach.gemini.system_prompt import FALLBACK_REPLY
from coach.models import ChatTurn

from .conftest import AINO, FakeClient, response

pytestmark = pytest.mark.django_db

ALERT_CARD = {
    "type": "alert",
    "id": "a-38-X",
    "severity": "amber",
    "title": "Unusual charge",
    "text": "EUR 15.64 at a lifestyle shop is much more than usual. Looks fine?",
}


def _reply(text, *cards):
    return response(("send_reply", {"text": text, "depth": 1, "cards": list(cards)}))


def _seed_alert_turn():
    ChatTurn.objects.create(
        customer_id=AINO,
        message="What alerts do I have?",
        reply={"text": "You have one alert.", "depth": 1, "cards": [ALERT_CARD]},
    )


# --- A: cards and alerts in the context --------------------------------------------


def test_card_summary_keeps_the_facts_of_an_alert():
    text = card_summary(ALERT_CARD)
    assert "a-38-X" in text and "Unusual charge" in text and "15.64" in text


@pytest.mark.parametrize(
    "card, words",
    [
        ({"type": "number", "label": "Safe to spend", "value": 18.7}, "18.7"),
        ({"type": "goal", "name": "Japan", "target": 1500, "saved": 50}, "Japan"),
        ({"type": "hologram"}, "hologram"),
    ],
)
def test_card_summary_covers_any_card(card, words):
    assert words in card_summary(card)


def test_history_includes_what_was_shown(aino):
    _seed_alert_turn()
    texts = [c.parts[0].text for c in loop._history_contents(AINO, [])]
    assert any("Unusual charge" in t and "15.64" in t for t in texts)


def test_profile_summary_lists_open_alerts(aino):
    profile = dict(services.get_profile(AINO))
    profile["alerts"] = [{"id": "a-20", "title": "Tight days ahead"}]
    summary = json.loads(loop.profile_summary(profile))
    assert summary["alerts"] == [{"id": "a-20", "title": "Tight days ahead"}]


# --- B: numbers the coach already said -----------------------------------------------


def test_reply_may_repeat_a_number_from_an_earlier_coach_reply(
    client, aino, fake_gemini
):
    _seed_alert_turn()
    fake_gemini(_reply("Good to know the 15.64 charge was you."))
    body = client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": "looks familiar, had problems", "depth": 1},
        content_type="application/json",
    ).json()
    assert body["text"] == "Good to know the 15.64 charge was you."


# --- C: conversational turns ------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "thanks!",
        "Kiitos",
        "hi",
        "my dog died",
        "looks familiar, had problems",
        "ok cool",
        "that was me",
        "I'm feeling really stressed today",
    ],
)
def test_small_talk_is_conversational(message):
    assert router.is_conversational(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "How much did I spend on restaurants?",
        "yes",
        "Undo",
        "High",
        "I'm stressed about money",
        "thanks, what's my balance?",
        "why is that?",
        "Show my baskets",
        "Pause my goal",
    ],
)
def test_questions_and_answers_are_not_conversational(message):
    assert router.is_conversational(message) is False


def _final_round_spy(client):
    seen = []
    original = client.models.generate_content

    def spy(model, contents, config=None):
        names = [d.name for d in config.tools[0].function_declarations]
        seen.append(names)
        return original(model, contents, config)

    client.models.generate_content = spy
    return seen


def test_conversational_turn_answers_in_one_round_without_the_router(aino):
    client = FakeClient(_reply("I'm so sorry about your dog."))
    seen = _final_round_spy(client)
    reply, meta = loop.chat(AINO, "my dog died", client=client)
    assert reply["text"] == "I'm so sorry about your dog."
    assert meta["conversational"] is True and meta["rounds"] == 1
    assert seen == [["send_reply"]]  # one Gemini call, no router call


def test_ok_is_not_small_talk_while_a_proposal_waits(aino):
    ChatTurn.objects.create(
        customer_id=AINO,
        message="Save a Japan goal",
        reply={"text": "Shall I save it?", "depth": 4, "cards": []},
        pending={
            "create_goal": {"name": "Japan", "amount": 1500, "date": "2027-06-01"}
        },
    )
    client = FakeClient(_reply("Saved."))
    _, meta = loop.chat(AINO, "ok cool", depth=4, client=client)
    assert meta["conversational"] is False


def test_conversational_reply_is_never_the_fallback(client, aino, fake_gemini):
    fake_gemini(_reply("Thanks for telling me. I'm here if you need anything."))
    body = client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": "thanks!"},
        content_type="application/json",
    ).json()
    assert body["text"] != FALLBACK_REPLY["text"]


# --- F: conversation evals ------------------------------------------------------------------


def test_run_evals_has_conversation_flows():
    from coach.management.commands.run_evals import CONVERSATION_FLOWS

    flat = [m for flow in CONVERSATION_FLOWS for m in flow]
    assert "looks familiar, had problems" in flat
    assert "my dog died" in flat
    assert any(len(flow) > 1 for flow in CONVERSATION_FLOWS)
