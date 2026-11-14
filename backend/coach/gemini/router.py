"""Depth router: keyword rules first, Flash-Lite only when no rule matches."""

import logging
import re

log = logging.getLogger(__name__)

# Order matters: deeper intents win over "how much" inside "help me plan".
RULES = [
    (4, re.compile(r"\b(help me|plan|i want|buy a|save for|clear my)\b", re.I)),
    (
        3,
        re.compile(
            r"\b(what if|what would|could i save|can i save|save more|"
            r"spend less|cancel|cut)\b",
            re.I,
        ),
    ),
    (2, re.compile(r"\b(why|explain|what kind|what's my|what is my)\b", re.I)),
    (1, re.compile(r"\b(how much|when|kuinka paljon|milloin|paljonko)\b", re.I)),
]

ROUTER_PROMPT = (
    "Classify the money question by depth. Reply with one digit only: "
    "1 = a fact, 2 = explain, 3 = what-if, 4 = coach or plan.\nQuestion: "
)


# Saving or progress questions get the user's level in the answer (#28-#33).
LEVELS_RE = re.compile(
    r"\b(sav(e|es|ed|ing)|spend less|level|next step|doing well|improve|"
    r"säästä\w*|taso\w*)\b",
    re.I,
)

LEVELS_HINT = (
    "This is about saving or progress: call get_level, attach its card, and "
    "frame the answer as the step to the next level."
)


def wants_levels(message):
    return bool(LEVELS_RE.search(message or ""))


def rule_depth(message):
    for depth, pattern in RULES:
        if pattern.search(message):
            return depth
    return None


def route(message, client=None, model=None):
    """Return depth 1-4 for ``message``."""
    depth = rule_depth(message)
    if depth is not None or client is None:
        return depth or 2
    try:
        resp = client.models.generate_content(
            model=model, contents=ROUTER_PROMPT + message
        )
        match = re.search(r"[1-4]", resp.text or "")
        return int(match.group()) if match else 2
    except Exception:  # noqa: BLE001 - router must never break chat
        log.exception("router failed, defaulting to depth 2")
        return 2
