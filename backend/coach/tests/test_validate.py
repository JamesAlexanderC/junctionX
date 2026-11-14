import pytest

from coach.gemini.validate import ReplyError, numbers_in_text, validate_reply


def test_numbers_in_text_formats():
    assert numbers_in_text("EUR 1,500 and 12.99 or 12,99, 20%") == [
        1500,
        12.99,
        12.99,
        20,
    ]


def test_numbers_must_come_from_tools():
    results = [{"safe_to_spend_week": 64.0, "next_payday": "2026-10-23"}]
    ok = validate_reply({"text": "EUR 64 until 23 Oct", "depth": 1}, results)
    assert ok["text"]
    with pytest.raises(ReplyError):
        validate_reply({"text": "EUR 65", "depth": 1}, results)


def test_share_as_percent_and_user_numbers():
    results = [{"share": 0.143}]
    validate_reply({"text": "14.3% leaky", "depth": 2}, results)
    validate_reply({"text": "Cut by 20%", "depth": 3}, [], message="cut 20%")


def test_bad_depth_rejected():
    with pytest.raises(ReplyError):
        validate_reply({"text": "x", "depth": 7}, [])


# --- cards: shape and numbers (CLAUDE.md "Card payloads") ---------------------

BASKETS = [{"totals": {"essential": 820.0, "surprise": 120.0, "leaky": 212.5}}]
CHART_RESULT = [{"chart_data": [{"label": "2026-08", "value": 5320.29}]}]


def _reply(*cards, text="Here you go."):
    return {"text": text, "depth": 2, "cards": list(cards)}


def test_card_numbers_must_come_from_tools():
    card = {
        "type": "chart",
        "kind": "bar",
        "title": "Income",
        "data": [{"label": "2026-08", "value": 9999.0}],
    }
    with pytest.raises(ReplyError, match="card"):
        validate_reply(_reply(card), CHART_RESULT)


def test_chart_card_from_tool_data_passes():
    card = {
        "type": "chart",
        "kind": "line",
        "title": "Income",
        "data": [{"label": "2026-08", "value": 5320.29}],
    }
    out = validate_reply(_reply(card), CHART_RESULT)
    assert out["cards"] == [card]


def test_numbers_inside_card_strings_are_checked():
    card = {"type": "number", "label": "Save EUR 500 a month", "value": 820.0}
    with pytest.raises(ReplyError):
        validate_reply(_reply(card), BASKETS)


@pytest.mark.parametrize(
    "card",
    [
        {"type": "chart", "kind": "bar", "title": "x"},  # no data
        {
            "type": "chart",
            "kind": "pie",
            "title": "x",
            "data": [{"label": "a", "value": 820.0}],
        },
        {"type": "number", "value": 820.0},  # no label
        {"type": "alert", "id": "a1", "severity": "purple", "title": "t", "text": "t"},
        {"type": "question", "question": "Which?", "options": ["only one"]},
    ],
)
def test_malformed_cards_are_rejected(card):
    with pytest.raises(ReplyError, match="card"):
        validate_reply(_reply(card), BASKETS)


def test_slider_position_fields_are_not_data():
    card = {
        "type": "slider",
        "category": "takeaway",
        "monthly_spend": 212.5,
        "min_pct": 0,
        "max_pct": 50,
        "pct": 35,
    }
    validate_reply(_reply(card), BASKETS)


def test_question_options_may_hold_new_numbers():
    card = {
        "type": "question",
        "question": "How much a month?",
        "options": ["EUR 50", "EUR 75", "EUR 150"],
    }
    validate_reply(_reply(card), [])


def test_alert_ids_are_not_checked_as_numbers():
    card = {
        "type": "alert",
        "id": "a-38-C-r768983",
        "severity": "amber",
        "title": "Unusual charge",
        "text": "Looks fine?",
    }
    validate_reply(_reply(card), [])


def test_unknown_fields_are_dropped_from_cards():
    card = {
        "type": "basket_bar",
        "essential": 820.0,
        "surprise": 120.0,
        "leaky": 212.5,
        "saver": 0,
        "colour": "red",
    }
    out = validate_reply(_reply(card), BASKETS)
    assert "colour" not in out["cards"][0]


def test_unknown_card_types_are_still_dropped_quietly():
    out = validate_reply(_reply({"type": "hologram", "value": 4242}), [])
    assert out["cards"] == []


def test_chips_repeating_question_options_are_dropped():
    card = {
        "type": "question",
        "question": "When would you like to achieve this goal?",
        "options": ["July 2027", "October 2027", "December 2027"],
    }
    args = {
        "text": "When?",
        "depth": 4,
        "cards": [card],
        "chips": ["July 2027", "october 2027 ", "Different goal"],
    }
    reply = validate_reply(args, [], "")
    assert reply["chips"] == ["Different goal"]
