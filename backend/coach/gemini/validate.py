"""send_reply validation (P2.4): schema, number matching, card whitelist.

Numbers in the text and in every card (cards.data_fields) must come from a
tool result of this turn or the user's message. Each known card must match
its payload (cards.py); unknown card types are dropped.
"""

import json
import re
from typing import Any

import pandas as pd

from inferences.common import merchant_name
from inferences.thresholds import MERCHANT_ID_RE

from pydantic import BaseModel, Field, ValidationError, field_validator

from .cards import CARD_MODELS, clean_card, data_fields

CARD_TYPES = set(CARD_MODELS)
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


def _unmatched(numbers, allowed):
    return [n for n in numbers if n not in FREE_INTEGERS and not _matches(n, allowed)]


def unmatched_numbers(text, tool_results, message=""):
    allowed = collect_numbers(tool_results) | collect_numbers(message)
    return _unmatched(numbers_in_text(text), allowed)


def _clean_cards(cards):
    """Known cards in their documented shape; unknown types are dropped."""
    out = []
    for i, card in enumerate(cards):
        if card["type"] not in CARD_TYPES:
            continue
        try:
            out.append(clean_card(card))
        except ValidationError as exc:
            problems = [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            ]
            raise ReplyError(
                f"card {i} ({card['type']}) does not match its payload: "
                f"{problems}. Fix the card and resend."
            ) from exc
    return out


def _check_card_numbers(cards, allowed):
    for i, card in enumerate(cards):
        bad = _unmatched(sorted(collect_numbers(data_fields(card))), allowed)
        if bad:
            raise ReplyError(
                f"These numbers in card {i} ({card['type']}) are not in any tool "
                f"result from this turn: {bad}. Only use numbers returned by tools."
            )


MERCHANT_RE = re.compile(MERCHANT_ID_RE)


def _check_merchant_ids(text, cards):
    """#24: users never see raw merchant ids; name the friendly version."""
    found = MERCHANT_RE.search(f"{text} {json.dumps(cards)}")
    if found:
        raw = found.group(0)
        friendly = merchant_name(pd.DataFrame(), raw)
        raise ReplyError(
            f"Do not show raw merchant ids like {raw}; say '{friendly}' instead."
        )


def validate_reply(args, tool_results, message=""):
    """Return a clean reply dict or raise ReplyError with a reason for Gemini."""
    try:
        reply = SendReply.model_validate(dict(args or {}))
    except ValidationError as exc:
        raise ReplyError(f"send_reply schema error: {exc.errors()}") from exc
    # First: its digits ("0016") would otherwise fail as an unknown number.
    _check_merchant_ids(reply.text, reply.cards)
    bad = unmatched_numbers(reply.text, tool_results, message)
    if bad:
        raise ReplyError(
            "These numbers are not in any tool result from this turn: "
            f"{bad}. Only use numbers returned by tools."
        )
    cards = _clean_cards(reply.cards)
    allowed = collect_numbers(tool_results) | collect_numbers(message)
    _check_card_numbers(cards, allowed)
    return {
        "text": reply.text,
        "depth": reply.depth,
        "cards": cards,
        "chips": _chips(reply.chips, cards),
    }


def _chips(chips, cards):
    """Chips without the answers a question card already offers as buttons."""
    offered = {
        str(o).strip().casefold()
        for card in cards
        if card["type"] == "question"
        for o in [*card.get("options", []), card.get("quick_answer")]
        if o
    }
    out = [str(c) for c in chips if str(c).strip().casefold() not in offered]
    return out[:MAX_CHIPS]
