"""Goal tools: list, create, change, rate and detected goals (#54, #63, #72).

Every write is proposed first and saved only after the user says yes to the
same proposal (``is_confirmed``). manage_goal ``add_saved`` also runs at once
when the request is unambiguous (``_clear_add``), with an undo for one turn.
Changes go through GoalSerializer, so chat and the REST form share rules.
"""

from ... import services
from ...models import DismissedSuggestion, Goal, GoalRating
from ...serializers import GoalSerializer
from ..validate import numbers_in_text
from .context import (
    UNDO_RE,
    ToolError,
    _norm,
    form_errors,
    is_confirmed,
    propose,
    unavailable,
)

GOAL_ACTIONS = [
    "edit",
    "pause",
    "resume",
    "complete",
    "abandon",
    "add_saved",
    "check_step",
    "undo",
]
EDITABLE = {"name", "amount", "date", "priority", "emoji"}
AMOUNT_TOLERANCE = 0.006
CONFIRM_CHANGE = "Ask the user to confirm this change. Nothing was saved."


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
    if not is_confirmed(ctx, "create_goal"):
        return propose(
            ctx,
            "create_goal",
            proposal,
            "Ask the user to confirm this goal. Nothing was saved.",
        )
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


# --- manage_goal -------------------------------------------------------------


def _evaluated(ctx, goal):
    """The goal as the rebuilt profile shows it (or its stored fields)."""
    services.refresh_profile(ctx.customer_id)
    ctx.reload()
    active = ctx.profile.get("goals", {}).get("active", [])
    found = next((g for g in active if g.get("id") == goal.id), None)
    return found or Goal.objects.get(pk=goal.pk).as_dict()


def _own_active_goal(ctx, goal_id):
    goal = Goal.objects.filter(pk=goal_id, customer_id=ctx.customer_id).first()
    if goal is None:
        raise ToolError(f"No goal {goal_id} for this user; call list_goals.")
    if goal.status != "active":
        raise ToolError(f"This goal is already {goal.status}.")
    return goal


def _form_save(goal, data):
    """Validate ``data`` with the goal form now; return a function that saves."""
    form = GoalSerializer(goal, data=data, partial=True)
    if not form.is_valid():
        raise ToolError(form_errors(form.errors))
    return form.save


def _check_step_save(goal, step):
    checklist = goal.checklist or []
    if step is None or not 0 <= step < len(checklist):
        raise ToolError(f"step must be 0 to {len(checklist) - 1} for this plan.")
    ticked = [
        {**item, "done": True} if i == step else item
        for i, item in enumerate(checklist)
    ]
    return lambda: Goal.objects.filter(pk=goal.pk).update(checklist=ticked)


def _edit_data(changes):
    if not changes:
        raise ToolError("edit needs changes: name, amount, date, priority or emoji.")
    unknown = set(changes) - EDITABLE
    if unknown:
        raise ToolError(f"Cannot change {sorted(unknown)}; only {sorted(EDITABLE)}.")
    return changes


def _saver(goal, action, changes, amount, step):
    """Check the request now and return a function that applies it."""
    if action == "check_step":
        return _check_step_save(goal, step)
    if action == "add_saved":
        if amount is None or amount <= 0:
            raise ToolError("add_saved needs an amount greater than 0.")
        return _form_save(goal, {"saved": round(goal.saved + amount, 2)})
    if action == "pause" and goal.paused:
        raise ToolError("This goal is already paused.")
    if action == "resume" and not goal.paused:
        raise ToolError("This goal is not paused.")
    data = {
        "edit": lambda: _edit_data(changes),
        "pause": lambda: {"paused": True},
        "resume": lambda: {"paused": False},
        "complete": lambda: {"status": "completed"},
        "abandon": lambda: {"status": "abandoned"},
    }[action]()
    return _form_save(goal, data)


def _named(goal, message):
    """The goal's name appears in the message as whole words."""
    name = _norm(goal.name)
    return bool(name) and f" {name} " in f" {_norm(message)} "


def _clear_add(ctx, goal, amount):
    """Option C: add_saved may run without a yes when Python can see that
    the exact amount is in the user's message, exactly one active goal fits
    and the amount does not overshoot what is left to save."""
    in_message = any(
        abs(n - amount) < AMOUNT_TOLERANCE for n in numbers_in_text(ctx.message)
    )
    active = list(Goal.objects.filter(customer_id=ctx.customer_id, status="active"))
    named = [g.id for g in active if _named(g, ctx.message)]
    fits = len(active) == 1 or named == [goal.id]
    left = goal.target - goal.saved
    return in_message and fits and amount <= left + AMOUNT_TOLERANCE


def _undo(ctx, goal):
    last = ctx.previous_pending.get("undo") or {}
    if last.get("goal_id") != goal.id or not UNDO_RE.search(ctx.message or ""):
        raise ToolError("Nothing to undo: only the last add_saved can be undone.")
    saved = max(0.0, round(goal.saved - float(last["amount"]), 2))
    _form_save(goal, {"saved": saved})()
    return {"status": "updated", "undone": last, "goal": _evaluated(ctx, goal)}


def manage_goal(ctx, goal_id, action, changes=None, amount=None, step=None):
    """#72 and friends: edit, pause, resume, complete, abandon, add_saved,
    check_step (plan goals) or undo the last add_saved."""
    if action not in GOAL_ACTIONS:
        raise ToolError(f"action must be one of {GOAL_ACTIONS}")
    goal = _own_active_goal(ctx, goal_id)
    if action == "undo":
        return _undo(ctx, goal)
    save = _saver(goal, action, changes, amount, step)
    request = {"changes": changes, "amount": amount, "step": step}
    proposal = {"goal_id": goal_id, "action": action}
    proposal.update({k: v for k, v in request.items() if v is not None})
    fast = action == "add_saved" and _clear_add(ctx, goal, amount)
    if not fast and not is_confirmed(ctx, "manage_goal", proposal):
        return propose(ctx, "manage_goal", proposal, CONFIRM_CHANGE)
    save()
    if action == "add_saved":
        ctx.pending["undo"] = {"goal_id": goal.id, "amount": float(amount)}
    return {"status": "updated", "goal": _evaluated(ctx, goal)}


# --- ratings and suggestions -------------------------------------------------


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


def dismiss_suggestion(ctx, suggestion_id):
    """Hide a detected-goal suggestion (#56 to #62) for good."""
    detected = ctx.profile.get("goals", {}).get("detected", [])
    if suggestion_id not in {g.get("id") for g in detected}:
        raise ToolError("Unknown suggestion; see get_detected_goals for ids.")
    proposal = {"suggestion_id": suggestion_id}
    if not is_confirmed(ctx, "dismiss_suggestion", proposal):
        return propose(
            ctx,
            "dismiss_suggestion",
            proposal,
            "Ask the user to confirm hiding this suggestion. Nothing was saved.",
        )
    DismissedSuggestion.objects.get_or_create(
        customer_id=ctx.customer_id, suggestion_id=suggestion_id
    )
    services.refresh_profile(ctx.customer_id)
    ctx.reload()
    return {"status": "dismissed", "suggestion_id": suggestion_id}
