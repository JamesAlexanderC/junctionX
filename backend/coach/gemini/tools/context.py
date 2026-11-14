"""ToolContext, ToolError and helpers shared by every tool (P2.2)."""

import re
from copy import deepcopy
from datetime import timedelta

from ... import services
from ...models import ChatTurn

CONFIRM_RE = re.compile(
    r"(?:yes|yeah|yep|sure|ok|okay|confirm|confirmed|accept|accepted|do it|"
    r"save it|go ahead|sounds good|kyllä|joo|hyväksy|accept plan|accept the plan)"
    r"(?:[\s,]+(?:please|yes|save it|do it|go ahead|accept plan|accept the plan))*"
    r"[.!\s]*",
    re.I,
)


UNDO_RE = re.compile(r"\b(undo|peru|peruuta|kumoa)\b", re.I)


class ToolError(ValueError):
    """Bad tool arguments; returned to Gemini as an error result."""


class ToolContext:
    def __init__(
        self, customer_id, message="", previous_pending=None, previous_turn_id=None
    ):
        self.customer_id = customer_id
        self.message = message
        self.previous_pending = deepcopy(previous_pending or {})
        self.previous_turn_id = previous_turn_id
        self.consumed = set()
        self.state_changed = False
        self.pending = {}
        self.results = []
        self.tools_called = []
        self.trace = []  # every tool call: args, result, exception (F3)
        self.validation_errors = []  # rejected send_reply reasons (F3)
        self.user_numbers = []  # earlier user messages and proposal (F1)
        self.timings = []  # [{step, ms, ...}] for router, gemini, tool (F2)
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
            CONFIRM_RE.fullmatch((self.message or "").strip())
        )


# --- propose, then confirm ---------------------------------------------------


def is_confirmed(ctx, kind, proposal=None):
    """The user said yes to the previous turn's ``kind`` proposal.

    With ``proposal`` the yes only counts for that exact proposal, so a
    changed request is proposed again instead of saved.
    """
    if not ctx.user_confirmed(kind):
        return False
    if proposal is not None and ctx.previous_pending.get(kind) != proposal:
        return False
    remaining = {k: v for k, v in ctx.previous_pending.items() if k != kind}
    if ctx.previous_turn_id is not None:
        # Compare-and-swap in the tool's transaction: concurrent requests or
        # stale contexts cannot consume the same proposal a second time.
        claimed = ChatTurn.objects.filter(
            pk=ctx.previous_turn_id,
            customer_id=ctx.customer_id,
            pending=ctx.previous_pending,
        ).update(pending=remaining)
        if not claimed:
            raise ToolError("This proposal was already used or has changed.")
    ctx.previous_pending = remaining
    ctx.consumed.add(kind)
    ctx.pending.pop(kind, None)
    return True


def propose(ctx, kind, proposal, instruction, key="proposal"):
    """Remember ``proposal`` for the next turn; nothing is saved."""
    if kind in ctx.consumed:
        raise ToolError("This proposal was already applied in this turn.")
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
