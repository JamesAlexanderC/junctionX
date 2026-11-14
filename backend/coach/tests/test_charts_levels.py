"""Chart framework (get_chart) and levels guidance (get_level card, router hint).

Gemini picks a chartable item; Python builds the whole chart card, which the
phone draws. Saving questions bring the user's level into the answer (#28-#33).
"""

import pytest

from coach.gemini import router
from coach.gemini.cards import clean_card
from coach.gemini.catalogue import CATALOGUE
from coach.gemini.system_prompt import SYSTEM_PROMPT
from coach.gemini.tools import DECLARATIONS, TOOLS, ToolContext, call_tool
from coach.gemini.tools.inference import CHARTABLE

from .conftest import AINO, response

pytestmark = pytest.mark.django_db


def _call(name, **args):
    return call_tool(ToolContext(AINO), name, args)


def _chat(client, message, depth=3):
    return client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": message, "depth": depth},
        content_type="application/json",
    )


# --- get_chart -----------------------------------------------------------------


def test_get_chart_is_declared_registered_and_explained():
    decl = next(d for d in DECLARATIONS if d["name"] == "get_chart")
    assert set(decl["parameters"]["properties"]["item"]["enum"]) == set(CHARTABLE)
    assert "get_chart" in TOOLS
    assert "get_chart" in SYSTEM_PROMPT


def test_every_chartable_item_has_a_title():
    assert all(CATALOGUE[item].chart.title for item in CHARTABLE)


@pytest.mark.parametrize("item", CHARTABLE)
def test_get_chart_returns_a_valid_card(aino, item):
    out = _call("get_chart", item=item)
    if not out["available"]:
        assert out["reason"]
        return
    card = out["card"]
    assert card == clean_card(card)
    assert card["kind"] == CATALOGUE[item].chart.kind
    assert card["data"]


def test_get_chart_card_matches_the_inference(aino):
    chart = _call("get_chart", item="forecast.daily_path")["card"]
    inference = _call("get_inference", item="forecast.daily_path")
    assert chart["data"] == inference["chart_data"]
    assert chart["unit"] == "EUR"


def test_get_chart_refuses_unchartable_items(aino):
    out = _call("get_chart", item="income.stability")
    assert "error" in out


def test_chat_passes_a_get_chart_card_through(client, aino, fake_gemini):
    card = _call("get_chart", item="baskets.totals")["card"]
    fake_gemini(
        response(("get_chart", {"item": "baskets.totals"})),
        response(
            (
                "send_reply",
                {
                    "text": "Essentials are your biggest basket.",
                    "depth": 2,
                    "cards": [card],
                },
            )
        ),
    )
    body = _chat(client, "Where does my money go?", depth=2).json()
    assert body["cards"] == [card]


# --- levels guidance -----------------------------------------------------------


def test_level_card_ladder_only_fills_levels_climbed_in_order():
    from coach.gemini.tools.read import level_card

    names = ["a", "b", "c", "d", "e", "f"]
    levels = {
        "current": 1,
        "current_name": "a",
        "next": 2,
        "next_name": "b",
        "progress": 0.0,
        "ladder": [
            {"level": i, "name": n, "reached": i in (1, 5)}
            for i, n in enumerate(names, 1)
        ],
    }
    ladder = level_card(levels)["ladder"]
    assert [r["reached"] for r in ladder] == [True] + [False] * 5


def test_get_level_includes_a_ready_level_card(aino):
    out = _call("get_level")
    card = out["card"]
    assert card == clean_card(card)
    assert card["level"] == out["next"]
    assert card["name"] == out["next_name"]
    assert card["euros_to_go"] == out["euros_to_go"]
    assert [r["level"] for r in card["ladder"]] == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize(
    "message",
    ["How can I save more?", "How do I get to the next level?", "Miten säästän?"],
)
def test_saving_questions_want_levels(message):
    assert router.wants_levels(message)


def test_other_questions_do_not_want_levels():
    assert not router.wants_levels("When is my payday?")


def test_save_more_routes_to_what_if_depth():
    assert router.rule_depth("How can I save more?") == 3


def test_saving_question_gets_the_levels_hint(client, aino, fake_gemini):
    reply = response(("send_reply", {"text": "Ok.", "depth": 3, "cards": []}))
    fake = fake_gemini(reply)
    _chat(client, "How can I save more?")
    sent = str(fake.models.calls[0]["contents"][-1])
    assert "get_level" in sent


def test_chat_answers_saving_with_the_level_card(client, aino, fake_gemini):
    card = _call("get_level")["card"]
    fake_gemini(
        response(("get_level", {})),
        response(
            (
                "send_reply",
                {"text": "Your next level is Safety net.", "depth": 3, "cards": [card]},
            )
        ),
    )
    body = _chat(client, "How can I save more?").json()
    assert body["cards"] == [card]


def test_level_card_explains_a_level_without_a_euro_gap():
    from coach.gemini.tools.read import level_card

    levels = {
        "current": 0,
        "current_name": "Not started",
        "next": 1,
        "next_name": "Getting started",
        "progress": 0.0,
        "euros_to_go": None,
        "easiest_next_step": None,
        "next_missing": ["No regular payday found yet"],
        "ladder": [],
    }
    assert level_card(levels)["next_step"] == "No regular payday found yet"
