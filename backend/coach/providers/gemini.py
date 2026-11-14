"""Gemini provider: google-genai with a manual function-calling loop.

Automatic function calling is disabled so every tool call goes through
:func:`coach.tools.run_tool` (and shows up as a ``tool`` event). After at most
:data:`MAX_TOOL_ROUNDS` rounds of tool calls the model must answer in text,
which is streamed as ``token`` events. If the API fails before any answer
text was sent, the turn falls back to the offline coach.
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from .. import tools as coach_tools
from .base import (
    Provider,
    chart_event,
    concept_event,
    suggestions_event,
    tool_event,
)
from .offline import OfflineProvider, suggestions_for_tools

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_CHARTS = 2

SYSTEM_PROMPT = """\
You are Money Coach, the friendly in-app money coach of S-Pankki, a Finnish \
bank. You talk with one customer about their own account data.

How to answer:
- Plain, warm, concise English. Short paragraphs; "- " lists when listing.
- Every number you mention must come from a tool result in this conversation. \
Never invent, estimate or round figures beyond what the tools return. If a \
tool cannot answer, say so.
- Call tools first: pick the most specific tool(s) for the question. You may \
call several.
- Put key numbers in **bold**, money as €1,234 (or €12.50 under €100).
- Keep it under about 150 words. Finish with one practical, specific tip \
starting with "**Tip:**".
- Explain money ideas simply (safe to spend, savings rate, the three \
baskets, compound interest, loan-to-value, stress test, emergency fund).
- You do not give investment advice (specific stocks, funds, crypto); \
suggest talking to an S-Pankki adviser instead.
- The app shows charts from tool results under your answer, so do not draw \
tables or ASCII charts.
- When safe_to_spend says well_covered, talk about the total free until \
payday and the customer's usual weekly spend, not a per-day figure. For spare \
cash, use the idle_cash numbers (a three-month buffer) so they match the app.
- When a change compares against a tiny or zero base, quote both amounts \
instead of a percentage.

Context: customer {customer_id}. "Today" is {today}; the data ends there, so \
"last month" means {last_month}. Spending is grouped into three baskets: \
must-pay bills (housing, utilities, groceries, subscriptions), surprise \
essentials (health, home & tech, travel) and everyday leakage (restaurants, \
entertainment, lifestyle, transportation incl. taxis)."""


def system_prompt(ctx):
    from finance import analytics as a

    last = a.resolve_period("last_month", ctx.today)[2]
    return SYSTEM_PROMPT.format(
        customer_id=ctx.customer_id,
        today=ctx.today.isoformat(),
        last_month=last,
    )


def function_declarations():
    return [
        types.FunctionDeclaration(
            name=d["name"],
            description=d["description"],
            parameters_json_schema=d["parameters"],
        )
        for d in coach_tools.declarations()
    ]


def to_contents(messages):
    """Chat history -> Gemini ``Content`` list (assistant -> model)."""
    out = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        text = (m.get("content") or "").strip()
        if text:
            out.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text)])
            )
    return out


def _parts(chunk):
    candidates = getattr(chunk, "candidates", None) or []
    if not candidates or not candidates[0].content:
        return []
    return list(candidates[0].content.parts or [])


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key, model, client=None, fallback=None):
        self.model = model
        self._api_key = api_key
        self._client = client
        self.fallback = fallback or OfflineProvider()

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _config(self, ctx, final=False):
        mode = "NONE" if final else "AUTO"
        return types.GenerateContentConfig(
            system_instruction=system_prompt(ctx),
            tools=[types.Tool(function_declarations=function_declarations())],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=mode)
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            temperature=0.4,
        )

    def stream(self, ctx, messages):
        state = {"text": False}
        try:
            yield from self._run(ctx, messages, state)
        except Exception as exc:  # noqa: BLE001 - any API/network failure
            log.warning("Gemini failed, falling back to offline coach: %s", exc)
            if state["text"]:
                yield {
                    "type": "token",
                    "text": "\n\n_(The connection to the AI coach dropped, so "
                    "this answer may be incomplete.)_",
                }
                return
            yield tool_event(
                "offline_fallback",
                "AI coach unavailable, using the built-in coach…",
            )
            yield from self.fallback.stream(ctx, messages)

    def _run(self, ctx, messages, state):
        contents = to_contents(messages)
        charts, concepts, used = [], [], []
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            final = round_no == MAX_TOOL_ROUNDS
            parts, calls, round_text = [], [], False
            stream = self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=self._config(ctx, final=final),
            )
            for chunk in stream:
                for part in _parts(chunk):
                    parts.append(part)
                    if part.function_call:
                        calls.append(part.function_call)
                    elif part.text and not part.thought:
                        state["text"] = round_text = True
                        yield {"type": "token", "text": part.text}
            if not calls or final:
                break
            if round_text:
                yield {"type": "token", "text": "\n\n"}
            contents.append(types.Content(role="model", parts=parts))
            responses = []
            for call in calls:
                name = call.name or ""
                args = dict(call.args or {})
                yield tool_event(name, coach_tools.label_for(name))
                result = coach_tools.run_tool(ctx, name, args)
                used.append(name)
                if result.get("chart") and len(charts) < MAX_CHARTS:
                    charts.append(result["chart"])
                if result.get("concept") and not concepts:
                    concepts.append(result["concept"])
                responses.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id,
                            name=name,
                            response={"result": _jsonable(result["data"])},
                        )
                    )
                )
            contents.append(types.Content(role="user", parts=responses))
        if not state["text"]:
            raise RuntimeError("Gemini returned no answer text")
        for chart in charts:
            yield chart_event(chart)
        for c in concepts:
            yield concept_event(c)
        question = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        items = suggestions_for_tools(ctx, used, question)
        if items:
            yield suggestions_event(items)


def _jsonable(data):
    """Round-trip through JSON so dates/Decimals become plain values."""
    return json.loads(json.dumps(data, default=str))
