"""Goal tools: list, create, rate and detected goals (#54, #63)."""

from ...models import Goal, GoalRating
from ... import services
from .context import ToolError, unavailable


def list_goals(ctx):
    g = ctx.profile.get("goals", {})
    return {
        "active": g.get("active", []),
        "recommended": g.get("recommended"),
        "clash": g.get("clash"),
    }


def create_goal(ctx, name, amount, date, emoji="", priority="medium"):
    """#63: saved only after the user confirmed in the previous turn."""
    from datetime import date as date_cls

    try:
        target_date = date_cls.fromisoformat(date)
    except ValueError as exc:
        raise ToolError("date must be YYYY-MM-DD") from exc
    if amount <= 0:
        raise ToolError("amount must be > 0")
    if target_date <= services.today():
        raise ToolError("date must be in the future")
    proposal = {
        "name": name,
        "amount": amount,
        "date": date,
        "emoji": emoji,
        "priority": priority,
    }
    if not ctx.user_confirmed("create_goal"):
        ctx.pending["create_goal"] = proposal
        return {
            "status": "needs_confirmation",
            "proposal": proposal,
            "instruction": "Ask the user to confirm this goal. Nothing was saved.",
        }
    goal = Goal.objects.create(
        customer_id=ctx.customer_id,
        name=name,
        emoji=emoji,
        target=amount,
        start_date=services.today(),
        target_date=target_date,
        priority=priority,
    )
    services.refresh_profile(ctx.customer_id)
    ctx.reload()
    saved = next(
        (
            g
            for g in ctx.profile.get("goals", {}).get("active", [])
            if g.get("db") and g["id"] == goal.id
        ),
        goal.as_dict(),
    )
    return {"status": "created", "goal": saved}


def rate_goal(ctx, goal_type, up):
    """#54 weight = (ups + 1) / (ups + downs + 2)."""
    GoalRating.objects.create(customer_id=ctx.customer_id, goal_type=goal_type, up=up)
    qs = GoalRating.objects.filter(customer_id=ctx.customer_id, goal_type=goal_type)
    ups = qs.filter(up=True).count()
    downs = qs.filter(up=False).count()
    services.invalidate(ctx.customer_id)
    ctx.reload()
    return {
        "goal_type": goal_type,
        "ups": ups,
        "downs": downs,
        "weight": round((ups + 1) / (ups + downs + 2), 4),
    }


def get_detected_goals(ctx):
    detected = ctx.profile.get("goals", {}).get("detected", [])
    if not detected:
        return unavailable("No saving patterns detected in the data.", detected=[])
    return {"available": True, "detected": detected}
