"""Tool registry, availability gating and dispatch (P2.2)."""

from . import alerts, goals, inference, loans, read
from .context import ToolError, unavailable
from .declarations import validate_args

TOOLS = {
    "get_category_spend": read.get_category_spend,
    "get_safe_to_spend": read.get_safe_to_spend,
    "get_safe_to_save": read.get_safe_to_save,
    "get_baskets": read.get_baskets,
    "get_level": read.get_level,
    "simulate_cut": read.simulate_cut,
    "forecast_balance": read.forecast_balance,
    "get_spender_type": read.get_spender_type,
    "list_goals": goals.list_goals,
    "create_goal": goals.create_goal,
    "rate_goal": goals.rate_goal,
    "get_detected_goals": goals.get_detected_goals,
    "get_mortgage_readiness": read.get_mortgage_readiness,
    "get_explainer": read.get_explainer,
    "get_benchmark": read.get_benchmark,
    "get_alerts": alerts.get_alerts,
    "explain_alert": alerts.explain_alert,
    "suggest_fixes": alerts.suggest_fixes,
    "simulate_plan": alerts.simulate_plan,
    "accept_plan": alerts.accept_plan,
    "snooze_alert": alerts.snooze_alert,
    "list_inferences": inference.list_inferences,
    "get_inference": inference.get_inference,
    "get_chart": inference.get_chart,
    "manage_goal": goals.manage_goal,
    "dismiss_suggestion": goals.dismiss_suggestion,
    "save_loan_details": loans.save_loan_details,
}


# Tool -> profile["availability"] item (inferences/availability.py). When the
# item is unavailable the tool returns {"available": false, "reason"} instead
# of running, so Gemini never sees a default standing in for missing data.
TOOL_AVAILABILITY = {
    "get_safe_to_spend": "forecast.safe_to_spend_week",
    "get_safe_to_save": "forecast.safe_to_save_today",
    "get_baskets": "baskets",
    "get_level": "levels",
    "simulate_cut": "whatif.category_cut",
    "forecast_balance": "forecast.end_of_month",
    "get_spender_type": "habits.spender_type",
    "get_detected_goals": "goals.detected",
    "get_mortgage_readiness": "mortgage.readiness",
}


def availability_item(name, args):
    if name == "get_benchmark":
        return f"benchmarks.{args.get('kind')}"
    return TOOL_AVAILABILITY.get(name)


def check_available(ctx, name, args):
    """None when the tool may run, else the unavailable result."""
    from inferences.availability import available

    item = availability_item(name, args)
    if item is None or available(ctx.profile, item):
        return None
    entry = (ctx.profile.get("availability") or {}).get(item) or {}
    return unavailable(
        entry.get("reason") or "The data does not support this.", item=item
    )


def call_tool(ctx, name, args):
    """Validate and run a tool; errors come back as a result for Gemini."""
    ctx.tools_called.append(name)
    try:
        clean = validate_args(name, args)
        result = check_available(ctx, name, clean) or TOOLS[name](ctx, **clean)
    except ToolError as exc:
        result = {"error": str(exc)}
    ctx.results.append(result)
    return result
