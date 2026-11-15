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


class _Check(_Card):
    text: str
    met: bool


class _Requirement(_Card):
    text: str
    checks: list[_Check] = []


class _Snapshot(_Card):
    safe_to_spend: float | None = None
    buffer_months: float | None = None
    goal_date: str | None = None
    # Multibank before/after (MULTIBANK_PLAN.md): S-Bank only vs all banks.
    dsti: float | None = None
    level: int | None = None
    monthly_income: float | None = None


class _AccountRow(_Card):
    bank: str
    name: str
    type: str
    balance: float | None = None
    iban_masked: str | None = None
    simulated: bool = False


# #13 (live test): units are English words the app formats; anything else
# ("kpl", "st") becomes "" so a count shows as a plain number. (A missing unit
# would make the number card fall back to EUR.)
KNOWN_UNITS = {"EUR", "€", "%", "date", "x", "days", "weeks", "months", "years"}


def _english_unit(value):
    return value if value is None or value in KNOWN_UNITS else ""


class NumberCard(_Card):
    # Optional (item 5): Gemini often left it out, and each rejected reply
    # cost another 6-16 s Gemini call; the app draws the card without it.
    label: str = ""
    value: float
    unit: str | None = None

    _unit = field_validator("unit")(classmethod(lambda cls, v: _english_unit(v)))


class ChartCard(_Card):
    kind: Literal["bar", "line"]
    title: str
    unit: str | None = None
    data: list[_Row] = Field(min_length=1)

    _unit = field_validator("unit")(classmethod(lambda cls, v: _english_unit(v)))


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
    as_of: str | None = None

    @field_validator("pct")
    @classmethod
    def pct_is_a_percent(cls, v):
        # simulate_cut takes a fraction (0.2 = 20 %); the slider wants percent.
        return round(v * 100, 2) if 0 < v <= 1 else v


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
    requirement: _Requirement | None = None
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


class AccountsCard(_Card):
    """Every account with its bank and a 'simulated' tag for other banks."""

    accounts: list[_AccountRow] = Field(min_length=1)
    coverage: Literal["sbank_only", "partial", "full"] | None = None


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
    "accounts": AccountsCard,
}

# Fields that are not claims about money: ids, display settings, and the
# question card, whose options are choices Gemini offers, not facts.
ALWAYS_NOT_DATA = {"type", "id", "clears", "unit", "kind"}
NOT_DATA = {
    "slider": {"min_pct", "max_pct", "pct", "as_of"},
    "question": {"question", "options", "quick_answer"},
    "accounts": {"coverage"},
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


def reference_dates(reply, today):
    """Slider dates are trusted server metadata, never chosen by the model."""
    for card in reply.get("cards", []):
        if card.get("type") == "slider":
            card["as_of"] = today.isoformat()
    return reply


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
