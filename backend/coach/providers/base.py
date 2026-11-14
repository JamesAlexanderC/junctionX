"""Provider interface for the coach.

A provider turns a conversation into a stream of contract events (see
docs/design.md): ``tool``, ``token``, ``chart``, ``concept``,
``suggestions``. The view adds ``meta`` first and ``done`` last.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from django.conf import settings


class Provider:
    """Base class: subclasses implement :meth:`stream`."""

    name = "base"
    model = None

    def stream(self, ctx, messages) -> Iterator[dict]:
        """Yield events answering the last user message in ``messages``.

        ``ctx`` is a :class:`coach.tools.CoachContext`; ``messages`` is a
        list of ``{"role": "user"|"assistant", "content": str}``.
        """
        raise NotImplementedError


def token_delay():
    return float(getattr(settings, "COACH_TOKEN_DELAY", 0.01))


def stream_text(text, delay=None):
    """Yield ``token`` events word by word with a tiny delay between them."""
    delay = token_delay() if delay is None else delay
    word = ""
    for ch in text:
        word += ch
        if ch.isspace():
            yield {"type": "token", "text": word}
            word = ""
            if delay:
                time.sleep(delay)
    if word:
        yield {"type": "token", "text": word}


def tool_event(name, label):
    return {"type": "tool", "name": name, "label": label}


def chart_event(chart):
    return {"type": "chart", "chart": chart}


def concept_event(concept):
    return {"type": "concept", "title": concept["title"], "text": concept["text"]}


def suggestions_event(items):
    return {"type": "suggestions", "items": list(items)[:3]}
