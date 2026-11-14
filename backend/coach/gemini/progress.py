"""What the chat shows while a reply is on its way (F2).

Two kinds of event, both plain text the frontend shows under the coach:

- step: the tool Gemini just asked for, as a fixed label written here. It is
  exactly what the loop is doing and never holds a number.
- thought: the heading of Gemini's thought summary for the round (the bold
  line it opens with). It is model text no tool checked, so a heading with a
  digit, a tool name or anything long is dropped rather than shown (CLAUDE.md:
  every number comes from Python).
"""

import re

STEP_LABELS = {
    "get_category_spend": "Looking at your spending by category",
    "get_safe_to_spend": "Working out what is safe to spend",
    "get_safe_to_save": "Working out what you can safely save",
    "get_baskets": "Sorting your spending into baskets",
    "get_level": "Checking your level",
    "simulate_cut": "Testing a spending cut",
    "forecast_balance": "Forecasting your balance",
    "get_spender_type": "Looking at your spending habits",
    "list_goals": "Checking your goals",
    "create_goal": "Setting up a goal",
    "rate_goal": "Saving your goal rating",
    "get_detected_goals": "Looking for goals in your spending",
    "get_mortgage_readiness": "Checking your mortgage readiness",
    "get_explainer": "Finding an explanation",
    "get_benchmark": "Comparing you with people like you",
    "get_alerts": "Checking your alerts",
    "explain_alert": "Looking into an alert",
    "suggest_fixes": "Finding ways to fix it",
    "simulate_plan": "Testing a plan",
    "accept_plan": "Saving your plan",
    "snooze_alert": "Snoozing an alert",
    "list_inferences": "Seeing what your data can tell us",
    "get_inference": "Looking something up in your data",
    "get_chart": "Drawing a chart",
    "manage_goal": "Updating your goal",
    "dismiss_suggestion": "Dismissing that suggestion",
    "save_loan_details": "Saving your loan details",
    "send_reply": "Checking the answer",
}
DEFAULT_STEP = "Looking at your data"
ROUTER_STEP = "Reading your question"
RETRY_STEP = "Double-checking the numbers"

THOUGHT_MAX_CHARS = 60
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
# A digit, or a snake_case name such as get_baskets.
_UNSAFE = re.compile(r"\d|[a-z]+_[a-z_]+")


def step(tool_name):
    return {"type": "step", "text": STEP_LABELS.get(tool_name, DEFAULT_STEP)}


def thought_heading(text):
    """Short heading of one thought summary, or None if it is not safe to
    show. Uses the bold line Gemini opens with, else the first line."""
    if not text:
        return None
    match = _BOLD.search(text)
    head = match.group(1) if match else text.strip().splitlines()[0]
    head = " ".join(head.split()).strip(" .:*#")
    if not head or len(head) > THOUGHT_MAX_CHARS or _UNSAFE.search(head):
        return None
    return head


def thoughts(response):
    """Thought events for one Gemini response, in order, no repeats."""
    out, seen = [], set()
    try:
        parts = response.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        return out
    for part in parts:
        if not getattr(part, "thought", False):
            continue
        head = thought_heading(getattr(part, "text", None))
        if head and head not in seen:
            seen.add(head)
            out.append({"type": "thought", "text": head})
    return out
