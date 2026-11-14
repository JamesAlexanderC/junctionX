"""Alert coach tools (context.md "Alert coach", P2.7)."""

from datetime import timedelta

import pandas as pd

from inferences.common import merchant_name

from ... import planner
from ...models import AlertSnooze, Goal, Transaction
from ... import services
from .context import ToolError, is_confirmed, propose

# --- alert coach -----------------------------------------------------------


def _open_alerts(ctx):
    return services.active_alerts(ctx.customer_id, ctx.profile, services.today())


def _df(ctx):
    df = services.transactions_df(ctx.customer_id)
    return df if df is not None else services.empty_df()


def fixable_ids(ctx):
    """Alert ids the 'Fix this' plan would clear, from the planner itself
    (cached for the turn). Alerts outside it get 'Why?' instead of 'Fix
    this', which looped: e.g. 'Bill went up' depends on past payments that
    no plan step can change."""
    if ctx.fixable is None:
        plan = planner.suggest_fixes(
            ctx.profile, _open_alerts(ctx), df=_df(ctx), run_alerts=ctx.alert_runner
        )
        ctx.fixable = {i for step in plan.get("steps", []) for i in step["clears"]}
    return ctx.fixable


def get_alerts(ctx):
    ids = fixable_ids(ctx)
    return {"alerts": [{**a, "fixable": a["id"] in ids} for a in _open_alerts(ctx)]}


def mark_alert_cards(ctx, reply):
    """Set each alert card's fixable flag from Python, whatever Gemini sent."""
    cards = reply.get("cards") or []
    if not any(c.get("type") == "alert" for c in cards):
        return reply
    ids = fixable_ids(ctx)
    marked = [
        {**c, "fixable": c.get("id") in ids} if c.get("type") == "alert" else c
        for c in cards
    ]
    return {**reply, "cards": marked}


def explain_alert(ctx, alert_id):
    alert = next((a for a in _open_alerts(ctx) if a["id"] == alert_id), None)
    if alert is None:
        return {"found": False, "alert_id": alert_id}
    ids = alert.get("evidence_tx_ids") or []
    txs = [
        {
            "tx_id": t.tx_id,
            "date": t.tx_date.isoformat(),
            "amount": t.tx_amount_eur,
            "category": t.category,
            # #24: a friendly name ("a grocery shop"), never the raw MRC id.
            "merchant": merchant_name(pd.DataFrame(), t.merchant_id),
        }
        for t in Transaction.objects.filter(tx_id__in=ids[:5])
    ]
    return {"found": True, "alert": alert, "transactions": txs}


def _check_actions(actions):
    clean = []
    for a in actions:
        if not isinstance(a, dict) or "type" not in a:
            raise ToolError("each action needs a type")
        clean.append(a)
    return clean


def _complete_actions(ctx, actions):
    """Fill effort / impact / text from the planner's candidate list."""
    alerts = _open_alerts(ctx)
    candidates = planner.candidate_actions(ctx.profile, alerts)
    out = []
    for a in _check_actions(actions):
        match = next(
            (
                c
                for c in candidates
                if planner._same_target(c, a)
                and (a.get("pct") is None or c.get("pct") == a.get("pct"))
            ),
            None,
        )
        if match is None:
            raise ToolError(f"Action not available: {a}")
        out.append(match)
    return out


def suggest_fixes(ctx, alert_ids=None):
    alerts = _open_alerts(ctx)
    if alert_ids:
        alerts = [a for a in alerts if a["id"] in set(alert_ids)]
    plan = planner.suggest_fixes(
        ctx.profile, alerts, df=_df(ctx), run_alerts=ctx.alert_runner
    )
    if plan["steps"]:
        ctx.pending["accept_plan"] = [s["action"] for s in plan["steps"]]
    return plan


def simulate_plan(ctx, actions):
    actions = _complete_actions(ctx, actions)
    result = planner.simulate_plan(
        ctx.profile,
        actions,
        _open_alerts(ctx),
        df=_df(ctx),
        run_alerts=ctx.alert_runner,
    )
    ctx.pending["accept_plan"] = actions
    return result


def accept_plan(ctx, actions):
    """Saves the plan as a checklist goal; only after the user confirmed."""
    actions = _complete_actions(ctx, actions)
    if not is_confirmed(ctx, "accept_plan"):
        return propose(
            ctx,
            "accept_plan",
            actions,
            "Ask the user to accept the plan. Nothing was saved.",
            key="actions",
        )
    monthly = round(sum(a["monthly_impact"] for a in actions), 2)
    on = services.today()
    goal = Goal.objects.create(
        customer_id=ctx.customer_id,
        name="My money plan",
        emoji="✅",
        type="plan",
        target=max(monthly * 3, 1),
        start_date=on,
        target_date=on + timedelta(days=90),
        checklist=[{"text": a["text"], "done": False, "action": a} for a in actions],
    )
    services.refresh_profile(ctx.customer_id)
    ctx.reload()
    return {"status": "accepted", "goal_id": goal.id, "monthly_impact": monthly}


def snooze_alert(ctx, alert_id, days):
    if not 1 <= days <= 90:
        raise ToolError("days must be 1-90")
    until = services.today() + timedelta(days=days)
    AlertSnooze.objects.create(
        customer_id=ctx.customer_id, alert_id=alert_id, until=until
    )
    return {"alert_id": alert_id, "snoozed_until": until.isoformat()}
