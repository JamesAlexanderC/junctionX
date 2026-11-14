"""Gemini chat loop (context.md "Gemini chat loop", P2.3, P2.4, P2.6)."""

import copy
import json
import logging
import re
import time

from django.conf import settings
from google.genai import types

from .. import services
from ..models import ChatTurn, DemoCache
from . import router
from .system_prompt import FALLBACK_REPLY, SYSTEM_PROMPT
from .tools import ToolContext, call_tool, tool_declarations
from .validate import ReplyError, validate_reply

log = logging.getLogger("coach.gemini")

MAX_ROUNDS = 5
HISTORY_TURNS = 6


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
            "leaky_categories": [
                c["category"]
                for c in profile.get("baskets", {}).get("leaky_categories", [])
            ],
        }
    )


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


def offline_reply(profile):
    """Canned send_reply used when no Gemini key is configured (P2.1)."""
    safe = profile.get("forecast", {}).get("safe_to_spend_week")
    if safe is None:
        return copy.deepcopy(FALLBACK_REPLY)
    return {
        "text": f"You can safely spend EUR {safe:g} this week. (Offline demo reply.)",
        "depth": 1,
        "cards": [
            {"type": "number", "label": "Safe to spend", "value": safe, "unit": "EUR"}
        ],
        "chips": ["Show me why", "What can I do?", "Make it a goal"],
    }


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
        reply = offline_reply(profile)
        ChatTurn.objects.create(customer_id=customer_id, message=message, reply=reply)
        return reply, {"offline": True, "tools": []}

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
    reply, rounds, fallback = _run(client, contents, ctx)
    if fallback:
        reply = copy.deepcopy(FALLBACK_REPLY)
    ChatTurn.objects.create(
        customer_id=customer_id, message=message, reply=reply, pending=ctx.pending
    )
    if settings.DEMO_MODE and not fallback:
        DemoCache.objects.update_or_create(
            customer_id=customer_id, question=question, defaults={"reply": reply}
        )
    meta = {
        "model": settings.GEMINI_MODEL,
        "depth": depth,
        "routed": routed,
        "tools": ctx.tools_called,
        "rounds": rounds,
        "fallback": fallback,
        "latency_ms": round((time.monotonic() - started) * 1000),
    }
    log.info("chat %s", meta)
    return reply, meta


def _run(client, contents, ctx):
    """The tool loop: at most MAX_ROUNDS rounds, one retry on a bad reply."""
    config = build_config()
    retried = False
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
                    return reply, round_no, False
                except ReplyError as exc:
                    log.warning("send_reply rejected: %s", exc)
                    if retried:
                        return None, round_no, True
                    retried = True
                    result = {"error": str(exc), "instruction": "Fix and resend."}
            else:
                result = call_tool(ctx, call.name, args)
            parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": result}
                )
            )
        if not parts:
            parts.append(_text("user", "Call send_reply to answer.").parts[0])
        contents.append(types.Content(role="user", parts=parts))
    return None, MAX_ROUNDS, True
