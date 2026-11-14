"""Gemini chat loop (context.md "Gemini chat loop", P2.3, P2.4, P2.6)."""

import copy
import json
import logging
import re
import time

from django.conf import settings
from google.genai import errors as genai_errors
from google.genai import types

from .. import services
from ..models import ChatTurn, DemoCache
from . import router
from .system_prompt import FALLBACK_REPLY, SYSTEM_PROMPT
from .tools import ToolContext, call_tool, tool_declarations
from .tools.inference import list_inferences
from .validate import ReplyError, validate_reply

log = logging.getLogger("coach.gemini")

# Deeper questions chain tools (list_inferences -> get_inference -> ...).
MAX_ROUNDS = 8
HISTORY_TURNS = 6
# Total size of tool results per turn, so the context stays small (~15k tokens).
MAX_TURN_RESULT_CHARS = 60_000
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


def build_config():
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=tool_declarations())],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="ANY")
        ),
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
    result = call_tool(ctx, name, args)
    size = len(json.dumps(result, default=str))
    if used + size > MAX_TURN_RESULT_CHARS:
        result = {"error": BUDGET_ERROR}
        ctx.results[-1] = result
        ctx.trace[-1] = {**ctx.trace[-1], "result": result, "over_budget": True}
        return result, used
    return result, used + size


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
            if t.reply.get("text"):
                contents.append(_text("model", t.reply["text"]))
        return contents
    for item in (history or [])[-HISTORY_TURNS * 2 :]:
        role = "model" if item.get("role") in ("assistant", "model") else "user"
        text = item.get("text") or item.get("content") or ""
        if text:
            contents.append(_text(role, text))
    return contents


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

    if client is None:
        raise GeminiNotConfigured("Gemini is not configured: set GEMINI_API_KEY")

    routed = depth is None
    if routed:
        depth = router.route(message, client=client, model=settings.GEMINI_ROUTER_MODEL)

    contents = _history_contents(customer_id, history)
    contents.append(
        _text(
            "user",
            f"Profile summary: {profile_summary(profile)}\n"
            f"Answer at depth {depth}.\nUser: {message}",
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
    if settings.DEMO_MODE and not reason:
        DemoCache.objects.update_or_create(
            customer_id=customer_id, question=question, defaults={"reply": reply}
        )
    if reason:
        reply = _explain_fallback(ctx, reply, reason, detail, rounds)
    meta = {
        "model": settings.GEMINI_MODEL,
        "depth": depth,
        "routed": routed,
        "tools": ctx.tools_called,
        "rounds": rounds,
        "fallback": bool(reason),
        "fallback_reason": reason,
        "latency_ms": round((time.monotonic() - started) * 1000),
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
    config = build_config()
    retried = False
    used = 0
    for round_no in range(1, MAX_ROUNDS + 1):
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=contents, config=config
        )
        contents.append(resp.candidates[0].content)
        parts = []
        for call in resp.function_calls or []:
            args = dict(call.args or {})
            if call.name == "send_reply":
                try:
                    reply = validate_reply(args, ctx.results, ctx.message)
                    return reply, round_no, None, None
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
        contents.append(types.Content(role="user", parts=parts))
    return None, MAX_ROUNDS, "max_rounds", f"No send_reply after {MAX_ROUNDS} rounds."
