"""A stalled Gemini call ends the turn instead of hanging the chat forever
(live: "Looking deeper into your data..." never finished)."""

import json

import httpx2
import pytest
from django.test import override_settings

from coach.gemini import loop
from coach.gemini.system_prompt import FALLBACK_REPLY

from .conftest import AINO


class StalledModels:
    def generate_content(self, model, contents, config=None):
        raise httpx2.ReadTimeout("Gemini did not answer in time")


class StalledClient:
    models = StalledModels()


@pytest.fixture
def stalled(monkeypatch):
    monkeypatch.setattr("coach.gemini.loop.get_client", lambda: StalledClient())


def _ask(client, stream=False):
    return client.post(
        "/api/chat/" + ("?stream=1" if stream else ""),
        {"customer_id": AINO, "message": "Cut restaurants by 20%", "depth": 3},
        content_type="application/json",
    )


@pytest.mark.django_db
def test_a_stalled_call_answers_with_the_fallback(client, aino, stalled):
    res = _ask(client)
    assert res.status_code == 200
    assert res.json()["text"] == FALLBACK_REPLY["text"]


@pytest.mark.django_db
def test_a_stalled_call_still_ends_the_stream_with_a_reply(client, aino, stalled):
    raw = b"".join(_ask(client, stream=True).streaming_content).decode()
    last = json.loads(raw.splitlines()[-1])
    assert last["type"] == "reply"
    assert last["reply"]["text"] == FALLBACK_REPLY["text"]


@override_settings(
    GEMINI_API_KEY="test-key", GEMINI_TIMEOUT_S=30, GEMINI_RETRY_ATTEMPTS=2
)
def test_the_client_has_a_timeout_and_retries(monkeypatch):
    seen = {}

    def fake_client(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr("google.genai.Client", fake_client)
    loop.get_client()
    options = seen["http_options"]
    assert options.timeout == 30_000  # milliseconds
    assert options.retry_options.attempts == 2
