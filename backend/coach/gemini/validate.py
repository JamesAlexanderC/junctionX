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

# Thousands may be grouped by a space, a no-break space or a narrow no-break
# space ("1 428.40 €"), or by dots with a decimal comma ("1.428,40 €").
THOUSANDS_SPACES = "\u0020\u00a0\u202f"
SPACE_GROUPED = rf"\d{{1,3}}(?:[{THOUSANDS_SPACES}]\d{{3}})+(?:[.,]\d+)?(?!\d)"
DOT_GROUPED = r"\d{1,3}(?:\.\d{3})+,\d+"
COMMA_GROUPED = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"
# An optional sign is kept, so "-20" never matches a source value of 20.
GROUPED = f"{SPACE_GROUPED}|{DOT_GROUPED}|{COMMA_GROUPED}"
NUMBER_RE = re.compile(rf"(?<![\w.])[+-]?(?:{GROUPED}|\d+(?:[.,]\d+)?)")


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
    token = re.sub(f"[{THOUSANDS_SPACES}]", "", token)
    if re.fullmatch(rf"[+-]?{COMMA_GROUPED}", token):
        return float(token.replace(",", ""))
    if re.fullmatch(rf"[+-]?{DOT_GROUPED}", token):
        return float(token.replace(".", "").replace(",", "."))
    return float(token.replace(",", "."))


def numbers_in_text(text):
    return [parse_number(m.group()) for m in NUMBER_RE.finditer(text or "")]


def _matches(n, values):
    for v in values:
        candidates = (v, round(v), round(v, 1), round(v, 2))
        if any(abs(n - c) < 0.006 for c in candidates):
            return True
        # Within 1 % covers plain-language rounding ("about EUR 60").
        if v and abs(n - v) / abs(v) < 0.01:
            return True
    return False


def unmatched_numbers(text, tool_results, message=""):
    sources = quantity_sources([tool_results, message])
    return _text_unmatched(text, sources)


# Keys define units; only explicitly fractional fields permit x100. Basket
# `shares` and `*_pct` are already percentages, whereas habit `share` is 0..1.
FRACTION_KEYS = {
    "share",
    "top3_share",
    "saver_share",
    "cut_pct",
    "pct",
    "progress",
    "dsti",
    "ratio",
    "cv",
    "score",
    "readiness",
}
PERCENT_KEYS = {"shares", "trend_pp", "interest_rate", "progress_pct", "expected_pct"}
COUNT_KEYS = {
    "count",
    "level",
    "current",
    "next",
    "age",
    "customer_age",
    "days",
    "day",
    "months",
    "months_needed",
    "months_before",
    "months_after",
    "months_sooner",
    "years_left",
    "days_to_payday",
    "median_gap_days",
    "inference",
    "id",
    "effort",
    "bursts",
    "per_month",
    "unique_per_month",
    "inferences",
    "buffer_months",
}
DATE_RE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")
MONEY_BEFORE = re.compile(r"(?:EUR|€)\s*$", re.I)
MONEY_AFTER = re.compile(r"^\s*(?:EUR\b|euros?\b|€)", re.I)
PERCENT_AFTER = re.compile(r"^\s*(?:%|percent\b|per cent\b)", re.I)
COUNT_AFTER = re.compile(r"^\s*(?:days?|months?|years?|steps?|purchases?)\b", re.I)


def _source_kind(key, default):
    if key in FRACTION_KEYS or key.endswith(("_share", "_ratio")):
        return "fraction"
    if key in PERCENT_KEYS or key.endswith("_pct"):
        return "percent"
    if key in COUNT_KEYS or key.endswith(("_count", "_days", "_months", "_years")):
        return "count"
    if key.endswith("_id"):
        return "number"
    if "date" in key or key in {"month", "today", "as_of"}:
        return "date"
    return default


def _unit_kind(unit, default="number"):
    if unit in {"%", "percent"}:
        return "percent"
    if unit in {"eur", "€"}:
        return "money"
    if unit in {"day", "days", "month", "months", "year", "years", "count"}:
        return "count"
    return default


def _text_claims(text):
    """Classify explicit currency, percent and date claims before matching."""
    dates = list(DATE_RE.finditer(text))
    for match in NUMBER_RE.finditer(text):
        n = parse_number(match.group())
        before, after = text[: match.start()], text[match.end() :]
        if MONEY_BEFORE.search(before) or MONEY_AFTER.search(after):
            kind = "money"
        elif PERCENT_AFTER.search(after):
            kind = "percent"
        elif any(d.start() <= match.start() < d.end() for d in dates):
            kind = "date"
        elif COUNT_AFTER.search(after):
            kind = "count"
        else:
            kind = "number"
        yield n, kind


def quantity_sources(obj):
    """Unit-aware sources, retaining generic numbers for unlabelled prose."""
    sources = {
        kind: set()
        for kind in ("money", "percent", "number", "date", "count", "fraction")
    }

    def walk(value, kind="money"):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            n = float(value)
            sources["number"].add(n)
            sources[kind].add(n)
            if kind == "fraction":
                sources["percent"].add(n * 100)
        elif isinstance(value, str):
            for n, unit in _text_claims(value):
                sources["number"].add(n)
                # Dates, ids and counts never provide currency evidence.
                sources[unit].add(n)
        elif isinstance(value, dict):
            unit = str(value.get("unit", "")).casefold()
            item = str(value.get("item", value.get("term", ""))).split(".")[-1]
            for child_key, child in value.items():
                child_kind = _source_kind(child_key, kind)
                if child_key in {"value", "data"}:
                    child_kind = (
                        _unit_kind(unit) if unit else _source_kind(item, child_kind)
                    )
                walk(child, child_kind)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child, kind)

    walk(obj)
    return sources


def _text_unmatched(text, sources):
    bad = []
    for n, kind in _text_claims(text):
        if kind in {"number", "count"} and n in FREE_INTEGERS:
            continue
        if not _matches(n, sources[kind]):
            bad.append(n)
    return bad


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


def _check_card_numbers(cards, sources):
    for i, card in enumerate(cards):
        fields = data_fields(card)
        # Currency cards cannot borrow small free counts or date components.
        # Unitless number/chart cards default to EUR in the frontend.
        unit = card.get("unit", "EUR").casefold()
        kind = _unit_kind(unit)

        def check(value, key=""):
            bad = []
            if isinstance(value, bool) or value is None:
                return bad
            if isinstance(value, (int, float)):
                pool = _source_kind(key, kind) if key != "value" else kind
                if not _matches(value, sources[pool]):
                    bad.append(value)
            elif isinstance(value, str):
                bad.extend(_text_unmatched(value, sources))
            elif isinstance(value, dict):
                for k, child in value.items():
                    bad.extend(check(child, k))
            elif isinstance(value, list):
                for child in value:
                    bad.extend(check(child, key))
            return bad

        bad = check(fields)
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
    _check_card_numbers(cards, quantity_sources([tool_results, message]))
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
