"""MB-7: the coach's multibank tools, cards, router hint and prompt rules."""

import pytest

from coach.gemini import router
from coach.gemini.cards import clean_card
from coach.gemini.system_prompt import SYSTEM_PROMPT
from coach.gemini.tools import ToolContext, call_tool
from coach.gemini.validate import validate_reply

from .conftest import AINO

pytestmark = pytest.mark.django_db


def _call(name, **args):
    return call_tool(ToolContext(AINO), name, args)


@pytest.fixture
def linked(client, aino, synthetic):
    consent = client.post(
        "/api/consents/", {"customer_id": AINO, "bank_code": "NDEAFIHH"}, format="json"
    ).json()
    client.post(f"/api/consents/{consent['consent_id']}/authorise/")


def test_accounts_overview_without_links_is_sbank_only(aino):
    out = _call("get_accounts_overview")
    assert out["connected_banks"] == [] and out["coverage"] == "sbank_only"
    assert [a["bank"] for a in out["accounts"]] == ["S-Bank"]
    assert clean_card(out["card"])["type"] == "accounts"


def test_accounts_overview_lists_linked_accounts_as_simulated(linked):
    out = _call("get_accounts_overview")
    nordea = next(a for a in out["accounts"] if a["bank"] == "Nordea")
    assert nordea["simulated"] is True and out["simulated"] is True
    assert out["consent_expiries"][0]["bank"] == "Nordea"
    assert clean_card(out["card"]) == out["card"]


def test_insights_name_the_loan_its_bank_day_and_amount(linked):
    out = _call("get_multibank_insights")
    (loan,) = out["hidden_loans"]
    assert loan["bank"] == "Nordea" and loan["day_of_month"] == 3
    assert loan["evidence"] and not any("EXT" in e["name"] for e in loan["evidence"])
    assert out["simulated"] is True


def test_insights_without_links_say_so_and_give_coverage(aino):
    out = _call("get_multibank_insights")
    assert out["available"] is False and "connect" in out["reason"].lower()
    assert out["coverage"] == "sbank_only"


def test_compare_linked_view_returns_a_before_after_card(linked):
    out = _call("compare_linked_view")
    card = clean_card(out["card"])
    assert card["type"] == "before_after"
    assert set(card["after"]) >= {"safe_to_spend", "dsti", "level"}
    assert set(card["before"]) >= {"safe_to_spend", "level"}  # no loan: no DSTI
    reply = validate_reply(
        {"text": "Here is what changed.", "depth": 2, "cards": [out["card"]]},
        [out],
    )
    assert reply["cards"][0]["type"] == "before_after"


def test_compare_linked_view_needs_a_connected_bank(aino):
    out = _call("compare_linked_view")
    assert out["available"] is False


@pytest.mark.parametrize(
    "message",
    [
        "Connect my other bank",
        "What about my Nordea account?",
        "Näytä kaikki tilit",
        "toinen pankki",
        "Can you see all my accounts?",
        "yhdistä OP",
        "What is PSD2?",
    ],
)
def test_router_spots_multibank_questions(message):
    assert router.wants_multibank(message)


def test_router_leaves_other_questions_alone():
    assert not router.wants_multibank("How much did I spend on food?")


def test_prompt_states_the_multibank_rules():
    prompt = SYSTEM_PROMPT.lower()
    for words in (
        "which bank",
        "never ask for",
        "credentials",
        "cannot move money",
        "simulated",
        "connect another bank",
    ):
        assert words in prompt, words


def test_summary_names_connected_banks_so_every_answer_can(linked):
    import json

    from coach import services
    from coach.gemini import loop

    summary = json.loads(loop.profile_summary(services.get_profile(AINO)))
    assert summary["other_banks"] == ["Nordea"]
    assert summary["coverage"] == "full"


def test_summary_stays_as_before_without_other_banks(aino):
    import json

    from coach import services
    from coach.gemini import loop

    summary = json.loads(loop.profile_summary(services.get_profile(AINO)))
    assert "other_banks" not in summary and "coverage" not in summary


def test_hint_is_added_for_any_question_once_a_bank_is_connected(linked):
    from coach import services
    from coach.gemini import loop

    profile = services.get_profile(AINO)
    assert loop.wants_multibank_hint("What's my monthly income?", profile)
