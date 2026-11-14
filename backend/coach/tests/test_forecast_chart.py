"""FC-2 (handoff/forcasting.md): the balance forecast chart carries its range.

Each point of the forecast.daily_path chart has the 80% band (low, high) and
an optional flag (danger, bill, payday) worked out in Python, so the app only
draws them and every number still comes from a tool.
"""

import copy

import pytest
from pydantic import ValidationError

from coach import services
from coach.gemini.cards import clean_card
from coach.gemini.tools import ToolContext, call_tool
from coach.gemini.validate import ReplyError, validate_reply

from .conftest import AINO

pytestmark = pytest.mark.django_db


def _chart(customer, profile=None, item="forecast.daily_path"):
    ctx = ToolContext(customer)
    if profile is not None:
        ctx._profile = profile
    return call_tool(ctx, "get_chart", {"item": item})


def test_forecast_chart_points_carry_the_band(aino):
    path = services.get_profile(AINO)["forecast"]["daily_path"]
    card = _chart(AINO)["card"]
    assert card["title"] == "Expected balance (likely range)"
    assert [(p["value"], p["low"], p["high"]) for p in card["data"]] == [
        (p["expected"], p["low"], p["high"]) for p in path
    ]


def test_forecast_chart_flags_danger_bill_and_payday_days(aino):
    profile = copy.deepcopy(services.get_profile(AINO))
    days = [p["date"] for p in profile["forecast"]["daily_path"]]
    profile["forecast"]["danger_days"] = [days[1]]
    profile["forecast"]["upcoming_bills"] = [
        {"date": days[2], "name": "Rent", "amount": 650.0},
        {"date": days[1], "name": "Phone", "amount": 20.0},  # danger wins
    ]
    profile["income"]["payday"]["next_payday"] = days[3]

    data = _chart(AINO, profile)["card"]["data"]
    flags = {p["label"]: p.get("flag") for p in data}

    assert flags[days[1]] == "danger"
    assert flags[days[2]] == "bill"
    assert flags[days[3]] == "payday"
    assert flags[days[0]] is None


def test_other_charts_have_no_band(aino):
    card = _chart(AINO, item="baskets.totals")["card"]
    assert all("low" not in p and "flag" not in p for p in card["data"])


def test_band_card_from_get_chart_passes_validation(aino):
    result = _chart(AINO)
    reply = validate_reply(
        {"text": "Here is your balance.", "depth": 2, "cards": [result["card"]]},
        [result],
    )
    assert reply["cards"][0]["data"][0]["low"] == result["card"]["data"][0]["low"]


def test_invented_band_numbers_are_rejected(aino):
    result = _chart(AINO)
    card = copy.deepcopy(result["card"])
    card["data"][0]["high"] = 987654.0
    with pytest.raises(ReplyError, match="987654"):
        validate_reply({"text": "Here.", "depth": 2, "cards": [card]}, [result])


def test_card_rejects_an_unknown_flag():
    card = {
        "type": "chart",
        "kind": "line",
        "title": "x",
        "data": [{"label": "2026-10-01", "value": 1.0, "flag": "party"}],
    }
    with pytest.raises(ValidationError):
        clean_card(card)


# --- FC-7: wording, level card and charts for tight days ----------------------------


def test_danger_days_are_described_as_below_eur_50():
    from coach.gemini.catalogue import CATALOGUE

    about = CATALOGUE["forecast.danger_days"].about
    assert "EUR 50" in about and "buffer" not in about


@pytest.mark.parametrize("term", ["danger days", "tight days"])
def test_explainer_knows_tight_days(aino, term):
    out = call_tool(ToolContext(AINO), "get_explainer", {"term": term})
    assert out["found"] is True and "EUR 50" in out["text"]


def test_level_card_shows_current_level_and_clamps_progress():
    from coach.gemini.tools.read import level_card

    levels = {
        "current": 2,
        "current_name": "In control",
        "next": 3,
        "next_name": "Safety net",
        "progress": -0.18,
        "euros_to_go": 1089.71,
        "ladder": [],
    }
    card = level_card(levels)
    assert card["progress"] == 0.0
    assert (card["current_level"], card["current_name"]) == (2, "In control")
    assert (card["level"], card["name"]) == (3, "Safety net")
    assert clean_card(card)["current_level"] == 2


def test_prompt_attaches_the_balance_chart_for_tight_days():
    from coach.gemini.system_prompt import SYSTEM_PROMPT

    assert "money get tight" in SYSTEM_PROMPT


def test_level_card_out_of_range_progress_is_clamped_not_rejected():
    card = {"type": "level_progress", "level": 3, "name": "Safety net"}
    assert clean_card({**card, "progress": -0.18})["progress"] == 0.0
    assert clean_card({**card, "progress": 97})["progress"] == 1.0
