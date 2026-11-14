"""Chat loop limits and context for deeper tool use (round limit, result
budget, profile summary, system prompt)."""

import json

import pytest

from coach import services
from coach.gemini import loop
from coach.gemini.system_prompt import SYSTEM_PROMPT
from coach.gemini.tools import ToolContext, call_tool

from .conftest import AINO, response

pytestmark = pytest.mark.django_db

NEW_TOOLS = [
    "list_inferences",
    "get_inference",
    "manage_goal",
    "save_loan_details",
    "dismiss_suggestion",
]


def _function_results(contents):
    """Every function response sent back to Gemini, in order."""
    out = []
    for content in contents:
        for part in content.parts or []:
            if part.function_response is not None:
                out.append(part.function_response.response["result"])
    return out


def _chat(client, message="Tell me more", depth=2):
    return client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": message, "depth": depth},
        content_type="application/json",
    )


def test_round_limit_is_five():
    # F2 (handoff/Gemini_fix.md): back to the spec's 5 rounds for speed.
    assert loop.MAX_ROUNDS == 5


def test_system_prompt_asks_for_tools_in_one_round():
    assert "in the same turn" in SYSTEM_PROMPT


def test_tool_results_over_the_turn_budget_are_replaced(
    client, aino, fake_gemini, monkeypatch
):
    one = call_tool(ToolContext(AINO), "get_inference", {"item": "income.bills"})
    monkeypatch.setattr(loop, "MAX_TURN_RESULT_CHARS", len(json.dumps(one)) + 10)
    get = response(("get_inference", {"item": "income.bills"}))
    reply = response(("send_reply", {"text": "Done.", "depth": 2, "cards": []}))
    fake = fake_gemini(get, get, reply)

    _chat(client)

    results = _function_results(fake.models.calls[-1]["contents"])
    assert results[0]["available"] is True
    assert "budget" in results[1]["error"]


def test_over_budget_numbers_cannot_be_quoted(aino, monkeypatch):
    monkeypatch.setattr(loop, "MAX_TURN_RESULT_CHARS", 10)
    ctx = ToolContext(AINO)
    result = loop._call_within_budget(ctx, "get_safe_to_spend", {}, used=0)[0]
    assert "error" in result
    assert ctx.results == [result]


def test_profile_summary_counts_available_inferences(aino):
    profile = services.get_profile(AINO)
    summary = json.loads(loop.profile_summary(profile))
    items = call_tool(ToolContext(AINO), "list_inferences", {})["items"]
    assert summary["inferences_available"] == sum(r["available"] for r in items)


@pytest.mark.parametrize("name", NEW_TOOLS)
def test_system_prompt_explains_new_tools(name):
    assert name in SYSTEM_PROMPT


# --- end to end: read an inference, chart it -----------------------------------


def _daily_path_chart():
    out = call_tool(ToolContext(AINO), "get_inference", {"item": "forecast.daily_path"})
    return {
        "type": "chart",
        "kind": "line",
        "title": "Balance until payday",
        "unit": "EUR",
        "data": out["chart_data"],
    }


def test_chat_lists_reads_and_charts_an_inference(client, aino, fake_gemini):
    chart = _daily_path_chart()
    fake_gemini(
        response(("list_inferences", {"section": "forecast"})),
        response(("get_inference", {"item": "forecast.daily_path"})),
        response(
            (
                "send_reply",
                {
                    "text": "Here is your balance until payday.",
                    "depth": 2,
                    "cards": [chart],
                },
            )
        ),
    )
    body = _chat(client, "Show my balance until payday").json()
    assert body["cards"] == [chart]


def test_chat_rejects_a_chart_with_invented_points(client, aino, fake_gemini):
    chart = _daily_path_chart()
    fake_point = {"label": "2099-01-01", "value": 123456.0}
    bad = {**chart, "data": chart["data"] + [fake_point]}
    reply = response(("send_reply", {"text": "Here.", "depth": 2, "cards": [bad]}))
    fake = fake_gemini(
        response(("get_inference", {"item": "forecast.daily_path"})), reply, reply
    )
    body = _chat(client, "Show my balance until payday").json()
    assert body["cards"] == []  # fallback reply after one retry
    errors = [
        r for r in _function_results(fake.models.calls[-1]["contents"]) if "error" in r
    ]
    assert "123456" in errors[0]["error"]


# --- F2: where the time goes ---------------------------------------------------


def test_meta_reports_time_per_step(aino, monkeypatch):
    from .conftest import FakeClient

    client = FakeClient(
        response(("get_baskets", {})),
        response(("send_reply", {"text": "Done.", "depth": 1, "cards": []})),
    )
    _, meta = loop.chat(AINO, "How much is in my baskets?", client=client)

    steps = [t["step"] for t in meta["timings"]]
    assert steps.count("gemini") == 2
    assert "router" in steps and "tool" in steps and "validate" in steps
    tool = next(t for t in meta["timings"] if t["step"] == "tool")
    assert tool["name"] == "get_baskets"
    totals = meta["time_ms"]
    assert set(totals) == {"router", "gemini", "tool", "validate"}
    assert sum(totals.values()) <= meta["latency_ms"] + 1
