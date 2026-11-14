"""Shared fixtures: a scripted fake Gemini client and a fixed 'today'."""

from datetime import date

import pytest
from google.genai import types

from coach import services

TODAY = date(2026, 10, 18)


def response(*calls):
    parts = [types.Part.from_function_call(name=n, args=a) for n, a in calls]
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))]
    )


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": list(contents)})
        if len(self.script) > 1:
            return self.script.pop(0)
        return self.script[0]


class FakeClient:
    """Returns scripted function calls; the last response repeats forever."""

    def __init__(self, *script):
        self.models = FakeModels(script)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(services, "today", lambda: TODAY)
    settings.PROFILES_DIR = tmp_path / "profiles"
    settings.DEMO_MODE = False
    settings.GEMINI_API_KEY = ""


@pytest.fixture
def fake_gemini(monkeypatch):
    """Install a FakeClient as the Gemini client: fake_gemini(*responses)."""

    def install(*script):
        client = FakeClient(*script)
        monkeypatch.setattr("coach.gemini.loop.get_client", lambda: client)
        return client

    return install
