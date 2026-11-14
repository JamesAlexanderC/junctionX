"""send_reply validation (P2.4): schema, number matching, card whitelist."""

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

CARD_TYPES = {
    "number",
    "chart",
    "basket_bar",
    "slider",
    "goal",
    "level_progress",
    "question",
    "alert",
    "plan",
    "before_after",
}
MAX_CHIPS = 3
# Small counts ("2 easy steps", "3 months") are allowed without a tool source.
FREE_INTEGERS = set(range(0, 11))

NUMBER_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")


class ReplyError(ValueError):
    pass


class SendReply(BaseModel):
    text: str = Field(min_length=1)
    depth: int = Field(ge=1, le=4)
    cards: list[dict[str, Any]] = []
    chips: list[str] = []

    @field_validator("cards")
    @classmethod
    def cards_have_type(cls, cards):
        for card in cards:
            if not isinstance(card.get("type"), str):
                raise ValueError("every card needs a string type")
        return cards


def parse_number(token):
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", token):
        return float(token.replace(",", ""))
    return float(token.replace(",", "."))


def numbers_in_text(text):
    return [parse_number(m.group()) for m in NUMBER_RE.finditer(text or "")]


def collect_numbers(obj, out=None):
    """Every number in a tool result, including numbers inside strings."""
    out = set() if out is None else out
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        out.update(numbers_in_text(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, out)
    return out


def _matches(n, values):
    for v in values:
        candidates = (v, round(v), round(v, 1), round(v, 2), v * 100, round(v * 100))
        if any(abs(n - c) < 0.006 for c in candidates):
            return True
        # Within 1 % covers plain-language rounding ("about EUR 60").
        if v and abs(n - v) / abs(v) < 0.01:
            return True
    return False


def unmatched_numbers(text, tool_results, message=""):
    allowed = collect_numbers(tool_results) | collect_numbers(message)
    bad = []
    for n in numbers_in_text(text):
        if n in FREE_INTEGERS or _matches(n, allowed):
            continue
        bad.append(n)
    return bad


def validate_reply(args, tool_results, message=""):
    """Return a clean reply dict or raise ReplyError with a reason for Gemini."""
    try:
        reply = SendReply.model_validate(dict(args or {}))
    except ValidationError as exc:
        raise ReplyError(f"send_reply schema error: {exc.errors()}") from exc
    bad = unmatched_numbers(reply.text, tool_results, message)
    if bad:
        raise ReplyError(
            "These numbers are not in any tool result from this turn: "
            f"{bad}. Only use numbers returned by tools."
        )
    cards = [c for c in reply.cards if c["type"] in CARD_TYPES]
    return {
        "text": reply.text,
        "depth": reply.depth,
        "cards": cards,
        "chips": [str(c) for c in reply.chips][:MAX_CHIPS],
    }
