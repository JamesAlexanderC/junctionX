"""send_reply card payloads (CLAUDE.md "Card payloads") as pydantic models.

``clean_card`` validates one card against its type and drops unknown fields,
so the frontend only ever gets the documented shape. ``NOT_DATA`` lists the
fields whose numbers are UI settings or ids, not claims about the user's
money; every other number in a card must come from a tool result.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Card(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Row(_Card):
    label: str
    value: float
    # FC-2: the forecast chart's 80% band and day markers (danger first).
    low: float | None = None
    high: float | None = None
    flag: Literal["danger", "bill", "payday"] | None = None


class _SliderGoal(_Card):
    target: float
    saved: float
    monthly_rate: float


class _PlanStep(_Card):
    text: str
    monthly_impact: float
    clears: list[str] = []


class _Rung(_Card):
    level: int
    name: str
    reached: bool


class _Snapshot(_Card):
    safe_to_spend: float | None = None
    buffer_months: float | None = None
    goal_date: str | None = None


class NumberCard(_Card):
    label: str
    value: float
    unit: str | None = None


class ChartCard(_Card):
    kind: Literal["bar", "line"]
    title: str
    unit: str | None = None
    data: list[_Row] = Field(min_length=1)


class BasketBarCard(_Card):
    essential: float
    surprise: float
    leaky: float
    saver: float


class SliderCard(_Card):
    category: str
    monthly_spend: float
    min_pct: float = 0
    max_pct: float = 50
    pct: float
    goal: _SliderGoal | None = None


class GoalCard(_Card):
    name: str
    target: float
    saved: float
    target_date: str | None = None
    difficulty: str | None = None
    monthly_needed: float | None = None


class LevelProgressCard(_Card):
    level: int  # the level the user is working towards
    name: str
    current_level: int | None = None  # FC-7: where the user is now
    current_name: str | None = None
    progress: float

    @field_validator("progress")
    @classmethod
    def clamp_progress(cls, value):
        """FC-7: a bar between 0 and 1; clamp rather than fail the reply."""
        return min(1.0, max(0.0, value))

    euros_to_go: float | None = None
    next_step: str | None = None
    ladder: list[_Rung] | None = None


class QuestionCard(_Card):
    question: str
    options: list[str] = Field(min_length=2, max_length=4)
    quick_answer: str | None = None


class AlertCard(_Card):
    id: str
    severity: Literal["red", "amber", "blue"]
    title: str
    text: str
    # Set by Python after validation (tools/alerts.mark_alert_cards): the app
    # shows "Fix this" only when a plan can clear the alert, else "Why?".
    fixable: bool | None = None


class PlanCard(_Card):
    steps: list[_PlanStep] = Field(min_length=1)


class BeforeAfterCard(_Card):
    before: _Snapshot
    after: _Snapshot


CARD_MODELS = {
    "number": NumberCard,
    "chart": ChartCard,
    "basket_bar": BasketBarCard,
    "slider": SliderCard,
    "goal": GoalCard,
    "level_progress": LevelProgressCard,
    "question": QuestionCard,
    "alert": AlertCard,
    "plan": PlanCard,
    "before_after": BeforeAfterCard,
}

# Fields that are not claims about money: ids, display settings, and the
# question card, whose options are choices Gemini offers, not facts.
ALWAYS_NOT_DATA = {"type", "id", "clears", "unit", "kind"}
NOT_DATA = {
    "slider": {"min_pct", "max_pct", "pct"},
    "question": {"question", "options", "quick_answer"},
}


def clean_card(card: dict) -> dict:
    """The card in its documented shape; raises pydantic.ValidationError."""
    model = CARD_MODELS[card["type"]]
    fields = model.model_validate(card).model_dump(exclude_none=True)
    return {"type": card["type"], **fields}


def data_fields(card: dict) -> dict:
    """The parts of a cleaned card whose numbers must come from tools."""
    skip = ALWAYS_NOT_DATA | NOT_DATA.get(card["type"], set())
    return {k: v for k, v in card.items() if k not in skip}


# --- what a card showed, as one line for the chat history (conversation A) ---

SUMMARY_FIELDS = {
    "alert": ("id", "title", "text"),
    "number": ("label", "value", "unit"),
    "goal": ("name", "saved", "target", "target_date"),
    "chart": ("title",),
    "basket_bar": ("essential", "surprise", "leaky", "saver"),
    "slider": ("category", "monthly_spend", "pct"),
    "level_progress": ("current_level", "current_name", "level", "name"),
    "question": ("question", "options"),
    "plan": ("steps",),
    "before_after": ("before", "after"),
}
LABEL_FIELDS = {"id", "title", "text", "label", "name", "question"}


def _short(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    if isinstance(value, dict):
        return ", ".join(f"{k} {_short(v)}" for k, v in value.items() if v is not None)
    if isinstance(value, list):
        return ", ".join(_short(v) for v in value)
    return str(value)


def _steps(steps):
    return "; ".join(
        f"{s.get('text')} ({_short(s.get('monthly_impact'))} a month)"
        for s in steps
        if isinstance(s, dict)
    )


def card_summary(card: dict) -> str:
    """'alert a-38 | Unusual charge | EUR 15.64 at ...': the facts a card
    showed, so the next turn can refer to it ("looks familiar")."""
    kind = card.get("type", "card")
    parts = []
    for field in SUMMARY_FIELDS.get(kind, ()):
        value = card.get(field)
        if value in (None, "", [], {}):
            continue
        text = _steps(value) if field == "steps" else _short(value)
        parts.append(text if field in LABEL_FIELDS else f"{field} {text}")
    if kind == "chart":
        parts.append(f"{len(card.get('data') or [])} points")
    return " | ".join([kind, *parts])
