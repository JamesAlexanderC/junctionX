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
