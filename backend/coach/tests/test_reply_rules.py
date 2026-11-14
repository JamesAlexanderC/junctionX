"""Quick fixes from the live tests: card units, seasonal wording, privacy and
off-topic questions."""

import pytest

from coach.gemini.cards import clean_card
from coach.gemini.catalogue import CATALOGUE
from coach.gemini.system_prompt import SYSTEM_PROMPT

# --- #13: units are English (a count is a plain number) -----------------------------


@pytest.mark.parametrize(
    "unit, shown",
    [("EUR", "EUR"), ("%", "%"), ("months", "months"), ("kpl", ""), ("st", "")],
)
def test_number_card_keeps_only_known_units(unit, shown):
    card = {"type": "number", "label": "Impulse bursts", "value": 0, "unit": unit}
    assert clean_card(card)["unit"] == shown


def test_chart_card_unit_is_cleaned_too():
    card = {
        "type": "chart",
        "kind": "bar",
        "title": "x",
        "unit": "kpl",
        "data": [{"label": "a", "value": 1}],
    }
    assert clean_card(card)["unit"] == ""


# --- #23: the seasonal pot is the extra, not the month's total ---------------------


def test_seasonal_description_says_the_pot_is_extra():
    about = CATALOGUE["forecast.seasonal"].about
    assert "extra" in about and "not the month's total" in about


# --- privacy and off-topic -----------------------------------------------------------


def test_prompt_refuses_other_peoples_data_plainly():
    assert "another person" in SYSTEM_PROMPT


def test_prompt_redirects_off_topic_questions():
    assert "off-topic" in SYSTEM_PROMPT.lower()
