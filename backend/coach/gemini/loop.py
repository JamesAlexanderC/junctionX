"""Gemini chat loop (context.md "Gemini chat loop", P2.3, P2.4, P2.6)."""

import copy
import json
import logging
import re
import time
from contextlib import contextmanager

from django.conf import settings
from google.genai import errors as genai_errors
from google.genai import types

from .. import services
from ..models import ChatTurn, DemoCache
from . import router
from .system_prompt import FALLBACK_REPLY, SYSTEM_PROMPT
from .tools import ToolContext, call_tool, tool_declarations
from .tools.alerts import mark_alert_cards
from .tools.inference import list_inferences
from .cards import card_summary
from .validate import ReplyError, validate_reply

log = logging.getLogger("coach.gemini")

# The spec's 5 rounds (F2: speed); call tools together to fit deeper answers.
MAX_ROUNDS = 5
HISTORY_TURNS = 6
SUMMARY_ALERTS = 5  # open alerts named in the profile summary (conversation A)
CONVERSATION_NOTE = (
    "This message is conversation, not a data question. Reply warmly and "
    "briefly with send_reply. Use the earlier turns and what was shown if they "
    "help; offer one follow-up chip if useful."
)
# Total size of tool results per turn, so the context stays small (~15k tokens).
MAX_TURN_RESULT_CHARS = 60_000
LAST_ROUND_NOTE = (
    "Last step: answer now with send_reply, using only the tool results you "
    "already have. If they do not cover everything, say what you can and why."
)
BUDGET_ERROR = (
    "The tool result budget for this turn is used up. Answer with the results "
    "you already have and call send_reply."
)


def get_client():
    """Real google-genai client; tests monkeypatch this."""
    if not settings.GEMINI_API_KEY:
        return None
    from google import genai

    return genai.Client(api_key=settings.GEMINI_API_KEY)


def build_config(final=False):
    """Gemini config; on the final round only send_reply may be called, so a
    turn always ends with an answer built from the tools already used (FC-3:
    Gemini kept looking for more data until the rounds ran out)."""
    calling = types.FunctionCallingConfig(
        mode="ANY", allowed_function_names=["send_reply"] if final else None
    )
    declarations = tool_declarations()
    if final:
        # Live, Gemini ignored allowed_function_names, so declare only this.
        declarations = [d for d in declarations if d.name == "send_reply"]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=declarations)],
        tool_config=types.ToolConfig(function_calling_config=calling),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def normalise_question(text):
    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()[:500]


def profile_summary(profile):
    """Small profile summary sent as input context (Controls: Input)."""
    payday = profile.get("income", {}).get("payday", {})
    levels = profile.get("levels", {})
    goals = profile.get("goals", {}).get("active", [])
    return json.dumps(
        {
            "today": profile.get("today"),
            "next_payday": payday.get("next_payday"),
            "level": levels.get("current_name"),
            "spender_type": profile.get("habits", {})
            .get("spender_type", {})
            .get("label"),
            "goals": [{"id": g["id"], "name": g["name"]} for g in goals],
            "alert_count": len(profile.get("alerts", [])),
            # Conversation A: lets "that one" / "looks familiar" find an alert.
            "alerts": [
                {"id": a.get("id"), "title": a.get("title")}
                for a in profile.get("alerts", [])[:SUMMARY_ALERTS]
            ],
            "inferences_available": _available_count(profile),
            "leaky_categories": [
                c["category"]
                for c in profile.get("baskets", {}).get("leaky_categories", [])
            ],
        }
    )


def _available_count(profile):
    """How many catalogue items this profile supports (see list_inferences)."""
    ctx = ToolContext(profile.get("customer_id", ""))
    ctx._profile = profile
    return sum(row["available"] for row in list_inferences(ctx)["items"])


def _call_within_budget(ctx, name, args, used):
    """Run a tool; past the turn's budget its result is replaced by an error,
    also in ctx.results so its numbers cannot be quoted. Returns (result,
    chars used so far)."""
    with _timed(ctx, "tool", name=name):
        result = call_tool(ctx, name, args)
    size = len(json.dumps(result, default=str))
    if used + size > MAX_TURN_RESULT_CHARS:
        result = {"error": BUDGET_ERROR}
        ctx.results[-1] = result
        ctx.trace[-1] = {**ctx.trace[-1], "result": result, "over_budget": True}
        return result, used
    return result, used + size


def _with_cards_shown(reply):
    """The reply text plus a line naming what its cards showed (conversation
    A): without it "looks familiar" had nothing to refer to."""
    text = reply.get("text") or ""
    shown = [card_summary(c) for c in reply.get("cards") or [] if isinstance(c, dict)]
    if shown:
        text = f"{text}\n[Shown: {'; '.join(shown)}]".strip()
    return text


def _earlier_coach_replies(customer_id):
    """What the coach said in the last HISTORY_TURNS turns (conversation B):
    its numbers were checked against tools when first said."""
    stored = ChatTurn.objects.filter(customer_id=customer_id).order_by(
        "-created_at", "-id"
    )[:HISTORY_TURNS]
    return [t.reply for t in stored]


def _history_contents(customer_id, history):
    turns = list(
        ChatTurn.objects.filter(customer_id=customer_id).order_by("-created_at", "-id")[
            :HISTORY_TURNS
        ]
    )[::-1]
    contents = []
    if turns:
        for t in turns:
            contents.append(_text("user", t.message))
            said = _with_cards_shown(t.reply)
            if said:
                contents.append(_text("model", said))
        return contents
    for item in (history or [])[-HISTORY_TURNS * 2 :]:
        role = "model" if item.get("role") in ("assistant", "model") else "user"
        text = item.get("text") or item.get("content") or ""
        if text:
            contents.append(_text(role, text))
    return contents


TIMED_STEPS = ("router", "gemini", "tool", "validate")


@contextmanager
def _timed(ctx, step, **extra):
    """F2: record how long one step of the turn took, in ms."""
    start = time.monotonic()
    try:
        yield
    finally:
        took = round((time.monotonic() - start) * 1000, 1)
        ctx.timings.append({"step": step, **extra, "ms": took})


def _time_per_step(ctx):
    totals = dict.fromkeys(TIMED_STEPS, 0.0)
    for t in ctx.timings:
        totals[t["step"]] = round(totals[t["step"]] + t["ms"], 1)
    return totals


def _earlier_user_messages(customer_id, history):
    """What the user said in the last HISTORY_TURNS turns (stored or sent)."""
    stored = ChatTurn.objects.filter(customer_id=customer_id).order_by(
        "-created_at", "-id"
    )[:HISTORY_TURNS]
    said = [t.message for t in stored]
    if said:
        return said
    return [
        item.get("text") or item.get("content") or ""
        for item in (history or [])[-HISTORY_TURNS * 2 :]
        if item.get("role") not in ("assistant", "model")
    ]


def _text(role, text):
    return types.Content(role=role, parts=[types.Part.from_text(text=text)])


class GeminiNotConfigured(RuntimeError):
    """No GEMINI_API_KEY: the API answers 503 instead of a made-up reply."""


def chat(
    customer_id, message, history=None, depth=None, client=None, alert_runner=None
):
    """Answer one user message. Returns (reply, meta)."""
    started = time.monotonic()
    profile = services.get_profile(customer_id)
    if profile is None:
        raise LookupError(customer_id)
    question = normalise_question(message)
    if settings.DEMO_MODE:
        cached = DemoCache.objects.filter(
            customer_id=customer_id, question=question
        ).first()
        if cached:
            ChatTurn.objects.create(
                customer_id=customer_id, message=message, reply=cached.reply
            )
            return cached.reply, {"cached": True, "tools": []}

    client = client if client is not None else get_client()
    previous = (
        ChatTurn.objects.filter(customer_id=customer_id)
        .order_by("-created_at", "-id")
        .first()
    )
    ctx = ToolContext(
        customer_id, message, previous_pending=previous.pending if previous else {}
    )
    ctx.alert_runner = alert_runner
    # F1: numbers the user gave earlier, or that sit in the stored proposal,
    # may be repeated in the reply ("A 20,000 euro goal by 2028?").
    ctx.user_numbers = [
        ctx.previous_pending,
        *_earlier_user_messages(customer_id, history),
        *_earlier_coach_replies(customer_id),
    ]
    # Conversation C: small talk gets one round with send_reply only. Never
    # while a proposal waits, so "ok" / "yes" still confirms it.
    ctx.conversational = not ctx.previous_pending and router.is_conversational(message)

    if client is None:
        raise GeminiNotConfigured("Gemini is not configured: set GEMINI_API_KEY")

    if ctx.conversational and depth is None:
        depth = 1  # small talk: no router call needed
    routed = depth is None
    if routed:
        with _timed(ctx, "router"):
            depth = router.route(
                message, client=client, model=settings.GEMINI_ROUTER_MODEL
            )

    contents = _history_contents(customer_id, history)
    contents.append(
        _text(
            "user",
            f"Profile summary: {profile_summary(profile)}\n"
            f"Answer at depth {depth}.\n"
            + (f"{router.LEVELS_HINT}\n" if router.wants_levels(message) else "")
            + (f"{CONVERSATION_NOTE}\n" if ctx.conversational else "")
            + f"User: {message}",
        )
    )
    try:
        reply, rounds, reason, detail = _run(client, contents, ctx)
    except genai_errors.APIError as exc:
        log.exception("Gemini call failed for %s", customer_id)
        reply, rounds, reason, detail = None, 0, "gemini_error", str(exc)
    if reason:
        reply = copy.deepcopy(FALLBACK_REPLY)
    ChatTurn.objects.create(
        customer_id=customer_id, message=message, reply=reply, pending=ctx.pending
    )
    # A turn that left a proposal waiting is never cached: a replay would not
    # restore the proposal, so the user's "yes" could not confirm it (F1).
    if settings.DEMO_MODE and not reason and not ctx.pending:
        DemoCache.objects.update_or_create(
            customer_id=customer_id, question=question, defaults={"reply": reply}
        )
    if reason:
        reply = _explain_fallback(ctx, reply, reason, detail, rounds)
    meta = {
        "model": settings.GEMINI_MODEL,
        "depth": depth,
        "routed": routed,
        "conversational": ctx.conversational,
        "tools": ctx.tools_called,
        "rounds": rounds,
        "fallback": bool(reason),
        "fallback_reason": reason,
        "latency_ms": round((time.monotonic() - started) * 1000),
        "time_ms": _time_per_step(ctx),
        "timings": ctx.timings,
    }
    log.info("chat %s", meta)
    return reply, meta


def _explain_fallback(ctx, reply, reason, detail, rounds):
    """F3: log why this turn fell back; add it to the reply when DEBUG."""
    report = {
        "reason": reason,
        "detail": detail,
        "rounds": rounds,
        "tools": ctx.trace,
        "validation_errors": ctx.validation_errors,
    }
    log.warning(
        "chat fallback %s",
        json.dumps(
            {"customer_id": ctx.customer_id, "message": ctx.message, **report},
            default=str,
        ),
    )
    if settings.DEBUG:
        return {**reply, "debug": report}
    return reply


def _run(client, contents, ctx):
    """The tool loop: at most MAX_ROUNDS rounds, one retry on a bad reply.

    Returns (reply, rounds, fallback reason or None, detail).
    """
    config, final_config = build_config(), build_config(final=True)
    retried = False
    used = 0
    for round_no in range(1, MAX_ROUNDS + 1):
        with _timed(ctx, "gemini", round=round_no):
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=(
                    final_config
                    if round_no == MAX_ROUNDS or ctx.conversational
                    else config
                ),
            )
        contents.append(resp.candidates[0].content)
        parts = []
        for call in resp.function_calls or []:
            args = dict(call.args or {})
            if call.name == "send_reply":
                try:
                    with _timed(ctx, "validate"):
                        reply = validate_reply(
                            args, ctx.results + ctx.user_numbers, ctx.message
                        )
                    return mark_alert_cards(ctx, reply), round_no, None, None
                except ReplyError as exc:
                    log.warning("send_reply rejected: %s", exc)
                    ctx.validation_errors.append(str(exc))
                    if retried:
                        return None, round_no, "invalid_reply", str(exc)
                    retried = True
                    result = {"error": str(exc), "instruction": "Fix and resend."}
            else:
                result, used = _call_within_budget(ctx, call.name, args, used)
            parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": result}
                )
            )
        if not parts:
            parts.append(_text("user", "Call send_reply to answer.").parts[0])
        if round_no == MAX_ROUNDS - 1:
            parts.append(_text("user", LAST_ROUND_NOTE).parts[0])
        contents.append(types.Content(role="user", parts=parts))
    return None, MAX_ROUNDS, "max_rounds", f"No send_reply after {MAX_ROUNDS} rounds."
