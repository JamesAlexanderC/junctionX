"""POST /api/chat/?stream=1: progress events, then the reply (F2)."""

import json

from google.genai import types

from coach.gemini import loop, progress

from .conftest import AINO, response


def stream(client, message, depth=1):
    body = {"customer_id": AINO, "message": message, "history": []}
    if depth:
        body["depth"] = depth
    return client.post("/api/chat/?stream=1", body, content_type="application/json")


def events(res):
    raw = b"".join(res.streaming_content).decode()
    return [json.loads(line) for line in raw.splitlines() if line]


def with_thought(resp, text):
    """Put a thought-summary part in front of a scripted response."""
    parts = resp.candidates[0].content.parts
    parts.insert(0, types.Part(text=text, thought=True))
    return resp


def reply(text="Hi there."):
    return response(("send_reply", {"text": text, "depth": 1, "cards": []}))


def test_stream_sends_steps_thoughts_then_reply(client, aino, fake_gemini):
    fake_gemini(
        with_thought(
            response(("get_baskets", {})),
            "**Reviewing spending baskets**\n\nI will look at the baskets.",
        ),
        reply(),
    )
    res = stream(client, "Where does my money go?")
    assert res.status_code == 200
    assert res["Content-Type"] == "application/x-ndjson"
    out = events(res)
    assert out[0] == {"type": "thought", "text": "Reviewing spending baskets"}
    assert out[1] == {"type": "step", "text": progress.STEP_LABELS["get_baskets"]}
    assert out[2] == {"type": "step", "text": progress.STEP_LABELS["send_reply"]}
    assert out[-1]["type"] == "reply"
    assert out[-1]["reply"]["text"] == "Hi there."
    assert "meta" not in out[-1]


def test_routed_turn_starts_with_reading_step(client, aino, fake_gemini, monkeypatch):
    monkeypatch.setattr(loop.router, "route", lambda *a, **k: 1)
    fake_gemini(reply())
    out = events(stream(client, "hi", depth=None))
    assert out[0] == {"type": "step", "text": progress.ROUTER_STEP}


def test_unknown_customer_is_still_404(client, db, fake_gemini):
    fake_gemini(reply())
    res = client.post(
        "/api/chat/?stream=1",
        {"customer_id": "nobody", "message": "hi", "history": []},
        content_type="application/json",
    )
    assert res.status_code == 404


def test_no_key_is_still_503(client, aino, monkeypatch):
    monkeypatch.setattr(loop, "get_client", lambda: None)
    res = stream(client, "hi")
    assert res.status_code == 503
    assert "error" in res.json()


def test_failure_midway_ends_with_an_error_event(client, aino, monkeypatch):
    def broken(*a, **k):
        yield {"type": "step", "text": "Reading your question"}
        raise RuntimeError("boom")

    monkeypatch.setattr(loop, "chat_stream", broken)
    out = events(stream(client, "hi"))
    assert out[0]["type"] == "step"
    assert out[-1]["type"] == "error"
    assert "boom" not in out[-1]["error"]


def test_plain_request_is_unchanged(client, aino, fake_gemini):
    fake_gemini(response(("get_baskets", {})), reply())
    res = client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": "hi", "history": [], "depth": 1},
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.json()["text"] == "Hi there."


def test_thought_heading_drops_numbers_and_tool_names():
    assert progress.thought_heading("**Checking the bills**\nmore") == (
        "Checking the bills"
    )
    assert progress.thought_heading("Planning the answer.\nDetails") == (
        "Planning the answer"
    )
    assert progress.thought_heading("**Spending EUR 64 a week**") is None
    assert progress.thought_heading("**Calling get_baskets now**") is None
    assert progress.thought_heading("**" + "long " * 20 + "**") is None
    assert progress.thought_heading("") is None


def test_unknown_tool_gets_a_generic_step():
    assert progress.step("something_new")["text"] == progress.DEFAULT_STEP


def test_every_tool_has_a_step_label():
    from coach.gemini.tools.registry import TOOLS

    assert set(TOOLS) | {"send_reply"} == set(progress.STEP_LABELS)
