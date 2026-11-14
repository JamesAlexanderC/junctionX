"""F3 (handoff/Gemini_fix.md): every fallback reply says why.

Each path that returns FALLBACK_REPLY logs the customer, the message, every
tool call (args, result or exception with traceback), the validation errors
and the limit hit. With settings.DEBUG the reply also carries a "debug" field.
"""

import logging

import pytest
from google.genai import errors

from coach.gemini import loop
from coach.gemini.system_prompt import FALLBACK_REPLY
from coach.gemini.tools import registry

from .conftest import AINO, response

pytestmark = pytest.mark.django_db

INVENTED = response(
    ("send_reply", {"text": "You can spend EUR 98765.", "depth": 1, "cards": []})
)


def _chat(client, message="How much can I spend?"):
    return client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": message, "depth": 1},
        content_type="application/json",
    )


def _fallback_logs(caplog):
    return [r for r in caplog.records if "chat fallback" in r.getMessage()]


@pytest.fixture
def debug_on(settings):
    settings.DEBUG = True


def test_invalid_reply_fallback_says_why(client, aino, fake_gemini, caplog, debug_on):
    fake_gemini(response(("get_safe_to_spend", {})), INVENTED, INVENTED)
    with caplog.at_level(logging.WARNING, logger="coach.gemini"):
        body = _chat(client).json()

    debug = body["debug"]
    assert debug["reason"] == "invalid_reply"
    assert len(debug["validation_errors"]) == 2
    assert "98765" in debug["validation_errors"][0]
    assert [t["tool"] for t in debug["tools"]] == ["get_safe_to_spend"]
    (record,) = _fallback_logs(caplog)
    text = record.getMessage()
    assert AINO in text and "How much can I spend?" in text
    assert "invalid_reply" in text and "98765" in text


def test_round_limit_fallback_says_why(client, aino, fake_gemini, caplog, debug_on):
    fake_gemini(response(("get_baskets", {})))
    with caplog.at_level(logging.WARNING, logger="coach.gemini"):
        body = _chat(client).json()

    assert body["debug"]["reason"] == "max_rounds"
    assert len(body["debug"]["tools"]) == loop.MAX_ROUNDS
    assert "max_rounds" in _fallback_logs(caplog)[0].getMessage()


def test_tool_exception_is_caught_logged_and_shown(
    client, aino, fake_gemini, caplog, monkeypatch, debug_on
):
    def boom(ctx):
        raise RuntimeError("boom in baskets")

    monkeypatch.setitem(registry.TOOLS, "get_baskets", boom)
    fake_gemini(response(("get_baskets", {})))
    with caplog.at_level(logging.WARNING, logger="coach.gemini"):
        res = _chat(client)

    assert res.status_code == 200
    first = res.json()["debug"]["tools"][0]
    assert "boom in baskets" in first["exception"]
    assert "Traceback" in first["traceback"]
    assert "boom in baskets" in _fallback_logs(caplog)[0].getMessage()


def test_tool_exception_tells_gemini_without_internals(aino, monkeypatch):
    from coach.gemini.tools import ToolContext, call_tool

    def boom(ctx):
        raise RuntimeError("secret internals")

    monkeypatch.setitem(registry.TOOLS, "get_baskets", boom)
    result = call_tool(ToolContext(AINO), "get_baskets", {})
    assert "error" in result and "secret internals" not in result["error"]


def test_gemini_api_error_falls_back_with_reason(
    client, aino, fake_gemini, caplog, debug_on
):
    fake = fake_gemini(response(("get_baskets", {})))

    def fail(**kwargs):
        raise errors.ClientError(404, {"error": {"message": "model gone"}})

    fake.models.generate_content = fail
    with caplog.at_level(logging.WARNING, logger="coach.gemini"):
        res = _chat(client)

    assert res.status_code == 200
    assert res.json()["debug"]["reason"] == "gemini_error"
    assert "model gone" in res.json()["debug"]["detail"]
    assert "gemini_error" in _fallback_logs(caplog)[0].getMessage()


def test_no_debug_field_when_debug_is_off(client, aino, fake_gemini, settings):
    settings.DEBUG = False
    fake_gemini(response(("get_baskets", {})))
    assert _chat(client).json() == FALLBACK_REPLY


def test_good_reply_has_no_debug_field(client, aino, fake_gemini, debug_on):
    fake_gemini(response(("send_reply", {"text": "Hi.", "depth": 1, "cards": []})))
    assert "debug" not in _chat(client).json()


def test_meta_reports_the_fallback_reason(aino):
    from .conftest import FakeClient

    client = FakeClient(response(("get_baskets", {})))
    _, meta = loop.chat(AINO, "hi", depth=1, client=client)
    assert meta["fallback"] is True
    assert meta["fallback_reason"] == "max_rounds"
