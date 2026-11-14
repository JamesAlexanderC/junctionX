"""Speed #2: Gemini's thinking is set by the question's depth.

Depth 1 (facts) and small talk: thinking off. Depth 2 (explain): low.
Depths 3-4 (what-if, plans): the model's default, so harder reasoning
keeps its full thinking.
"""

import pytest

from coach.gemini import loop

from .conftest import AINO, FakeClient, response

pytestmark = pytest.mark.django_db


def _thinking_seen(message, depth=None):
    client = FakeClient(
        response(("send_reply", {"text": "Ok.", "depth": depth or 1, "cards": []}))
    )
    seen = []
    original = client.models.generate_content

    def spy(model, contents, config=None):
        if config is not None:  # skip the router call
            seen.append(config.thinking_config)
        return original(model, contents, config)

    client.models.generate_content = spy
    _, meta = loop.chat(AINO, message, depth=depth, client=client)
    return seen[0], meta


def test_facts_think_not_at_all(aino):
    thinking, meta = _thinking_seen("How much did I spend on taxis?", depth=1)
    assert thinking.thinking_budget == 0
    assert meta["thinking"] == "off"


def test_small_talk_thinks_not_at_all(aino):
    thinking, meta = _thinking_seen("thanks!")
    assert thinking.thinking_budget == 0
    assert meta["thinking"] == "off"


def test_explanations_think_a_little(aino):
    thinking, meta = _thinking_seen("Tell me about my spending", depth=2)
    assert str(thinking.thinking_level).lower().endswith("low")
    assert meta["thinking"] == "low"


@pytest.mark.parametrize("depth", [3, 4])
def test_what_ifs_and_plans_keep_the_default(aino, depth):
    thinking, meta = _thinking_seen("Help me plan my money", depth=depth)
    assert thinking is None
    assert meta["thinking"] == "default"
