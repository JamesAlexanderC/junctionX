"""ToolContext, ToolError and helpers shared by every tool (P2.2)."""

import re
from datetime import timedelta

from ... import services

CONFIRM_RE = re.compile(
    r"\b(yes|yeah|yep|sure|ok|okay|confirm|confirmed|accept|accepted|do it|"
    r"save it|go ahead|sounds good|kyllä|joo|hyväksy)\b",
    re.I,
)


UNDO_RE = re.compile(r"\b(undo|peru|peruuta|kumoa)\b", re.I)


class ToolError(ValueError):
    """Bad tool arguments; returned to Gemini as an error result."""


class ToolContext:
    def __init__(self, customer_id, message="", previous_pending=None):
        self.customer_id = customer_id
        self.message = message
        self.previous_pending = previous_pending or {}
        self.pending = {}
        self.results = []
        self.tools_called = []
        self.trace = []  # every tool call: args, result, exception (F3)
        self.validation_errors = []  # rejected send_reply reasons (F3)
        self.user_numbers = []  # earlier user messages and proposal (F1)
        self.timings = []  # [{step, ms, ...}] for router, gemini, tool (F2)
        self.conversational = False  # small talk: one round, send_reply only
        self.fixable = None  # alert ids a "Fix this" plan clears (per turn)
        self.alert_runner = None
        self._profile = None

    @property
    def profile(self):
        if self._profile is None:
            self._profile = services.get_profile(self.customer_id) or {}
        return self._profile

    def reload(self):
        self._profile = None

    @property
    def today(self):
        return services.profile_today(self.profile)

    def user_confirmed(self, kind):
        """True when the previous turn proposed ``kind`` and the user said yes."""
        return kind in self.previous_pending and bool(
            CONFIRM_RE.search(self.message or "")
        )


# --- propose, then confirm ---------------------------------------------------


def is_confirmed(ctx, kind, proposal=None):
    """The user said yes to the previous turn's ``kind`` proposal.

    With ``proposal`` the yes only counts for that exact proposal, so a
    changed request is proposed again instead of saved.
    """
    if not ctx.user_confirmed(kind):
        return False
    return proposal is None or ctx.previous_pending.get(kind) == proposal


def propose(ctx, kind, proposal, instruction, key="proposal"):
    """Remember ``proposal`` for the next turn; nothing is saved."""
    ctx.pending[kind] = proposal
    return {"status": "needs_confirmation", key: proposal, "instruction": instruction}


def form_errors(errors):
    """DRF serializer errors as one sentence for Gemini."""
    parts = []
    for field, messages in errors.items():
        text = " ".join(str(m) for m in messages)
        parts.append(text if field == "non_field_errors" else f"{field}: {text}")
    return "; ".join(parts)


# --- helpers ---------------------------------------------------------------


def _last_full_month(on):
    first = on.replace(day=1)
    return (first - timedelta(days=1)).strftime("%Y-%m")


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def unavailable(reason, **extra):
    """What a tool returns when the data does not support the inference.

    Gemini must then say it has no answer instead of using a default.
    """
    return {"available": False, "reason": reason, **extra}


def _missing(value):
    return value is None or value == [] or value == {}
