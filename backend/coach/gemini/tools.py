"""Gemini tool declarations and their Python implementations (P2.2).

Each tool is ``fn(ctx, **args)``; ``ctx`` is a :class:`ToolContext` with the
customer id, the cached profile and the confirmation state of this turn.
Every number a tool returns comes from the precomputed profile or an
inference formula; Gemini only explains them.
"""

import math
import re
from datetime import timedelta

from google.genai import types

from .. import planner, services
from ..models import AlertSnooze, Goal, GoalRating, Transaction

CONFIRM_RE = re.compile(
    r"\b(yes|yeah|yep|sure|ok|okay|confirm|confirmed|accept|accepted|do it|"
    r"save it|go ahead|sounds good|kyllä|joo|hyväksy)\b",
    re.I,
)


class ToolError(ValueError):
    """Bad tool arguments; returned to Gemini as an error result."""


class ToolContext:
    def __init__(self, customer_id, message="", previous_pending=None):
        self.customer_id = customer_id
        self.message = message
        self.previous_pending = previous_pending or {}
        self.pending = {}
        self.results = []
        self.tools_called = []
        self.alert_runner = None
        self._profile = None

    @property
    def profile(self):
        if self._profile is None:
            self._profile = services.get_profile(self.customer_id) or {}
        return self._profile

    def reload(self):
        self._profile = None

    @property
    def today(self):
        return services.profile_today(self.profile)

    def user_confirmed(self, kind):
        """True when the previous turn proposed ``kind`` and the user said yes."""
        return kind in self.previous_pending and bool(
            CONFIRM_RE.search(self.message or "")
        )


# --- declarations ----------------------------------------------------------

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "cut_category",
                "cancel_subscription",
                "pause_goal",
                "resize_goal",
                "move_saver_to_buffer",
            ],
        },
        "category": STR,
        "pct": NUM,
        "merchant_id": STR,
        "goal_id": INT,
        "factor": NUM,
        "amount": NUM,
    },
    "required": ["type"],
}

CARD_SCHEMA = {
    "type": "object",
    "description": "A UI card; extra fields depend on type (see CLAUDE.md).",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "number",
                "chart",
                "basket_bar",
                "slider",
                "goal",
                "level_progress",
                "question",
                "alert",
                "plan",
                "before_after",
            ],
        },
        "label": STR,
        "value": NUM,
        "unit": STR,
        "kind": STR,
        "title": STR,
        "data": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": STR, "value": NUM},
            },
        },
        "essential": NUM,
        "surprise": NUM,
        "leaky": NUM,
        "saver": NUM,
        "category": STR,
        "monthly_spend": NUM,
        "pct": NUM,
        "min_pct": NUM,
        "max_pct": NUM,
        "goal": {"type": "object", "properties": {}},
        "name": STR,
        "target": NUM,
        "saved": NUM,
        "target_date": STR,
        "difficulty": STR,
        "monthly_needed": NUM,
        "level": INT,
        "progress": NUM,
        "euros_to_go": NUM,
        "next_step": STR,
        "question": STR,
        "options": {"type": "array", "items": STR},
        "quick_answer": STR,
        "id": STR,
        "severity": STR,
        "text": STR,
        "steps": {"type": "array", "items": {"type": "object", "properties": {}}},
        "before": {"type": "object", "properties": {}},
        "after": {"type": "object", "properties": {}},
    },
    "required": ["type"],
}


def _decl(name, description, properties=None, required=None):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


DECLARATIONS = [
    _decl(
        "get_category_spend",
        "Total spend in one category for a month (default: last full month).",
        {"category": STR, "month": {"type": "string", "description": "YYYY-MM"}},
        ["category"],
    ),
    _decl(
        "get_safe_to_spend",
        "Safe to spend this week (#17), with payday (#1), buffer and bills due.",
    ),
    _decl("get_safe_to_save", "Safe to save today (#18) and danger days (#20)."),
    _decl("get_baskets", "Four-basket split for the month (#7-#10, #75)."),
    _decl("get_level", "Current level, progress and easiest next step (#28-#33)."),
    _decl(
        "simulate_cut",
        "What-if: cut a category by pct (0-1) (#24), optionally for a goal (#26).",
        {"category": STR, "pct": NUM, "goal_id": INT},
        ["category", "pct"],
    ),
    _decl(
        "forecast_balance",
        "End-of-month balance range (#19), danger days (#20), upcoming bills (#21).",
    ),
    _decl("get_spender_type", "Spender type and habit traits (#11-#16)."),
    _decl("list_goals", "Active goals with progress, plus the recommended goal."),
    _decl(
        "create_goal",
        "Save a goal. Only after the user confirmed it in their last message.",
        {
            "name": STR,
            "amount": NUM,
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "emoji": STR,
            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        ["name", "amount", "date"],
    ),
    _decl(
        "rate_goal",
        "Record a thumbs up/down on a suggested goal type (#54).",
        {"goal_type": STR, "up": BOOL},
        ["goal_type", "up"],
    ),
    _decl("get_detected_goals", "Goals detected from the data, as suggestions."),
    _decl(
        "get_mortgage_readiness",
        "Mortgage readiness score and gaps (#34-#35), loan burden (#76-#82).",
    ),
    _decl(
        "get_explainer",
        "Two-line plain-language explanation of a money word, with user numbers.",
        {"term": STR},
        ["term"],
    ),
    _decl(
        "get_benchmark",
        "Compare spending with the user's age group or area (#36-#37).",
        {"kind": {"type": "string", "enum": ["age", "area"]}, "category": STR},
        ["kind"],
    ),
    _decl("get_alerts", "Active alerts with severity, priority and trigger values."),
    _decl(
        "explain_alert",
        "The numbers that triggered an alert and the transactions behind it.",
        {"alert_id": STR},
        ["alert_id"],
    ),
    _decl(
        "suggest_fixes",
        "Up to 3 ranked actions with euro impact and the alerts each clears.",
        {"alert_ids": {"type": "array", "items": STR}},
    ),
    _decl(
        "simulate_plan",
        "Before/after numbers for a list of actions, and alerts still open.",
        {"actions": {"type": "array", "items": ACTION_SCHEMA}},
        ["actions"],
    ),
    _decl(
        "accept_plan",
        "Save a plan as a checklist goal. Only after the user confirmed it.",
        {"actions": {"type": "array", "items": ACTION_SCHEMA}},
        ["actions"],
    ),
    _decl(
        "snooze_alert",
        "Hide an alert for some days.",
        {"alert_id": STR, "days": INT},
        ["alert_id", "days"],
    ),
    _decl(
        "send_reply",
        "Final answer shown to the user. Always end with this.",
        {
            "text": STR,
            "depth": INT,
            "cards": {"type": "array", "items": CARD_SCHEMA},
            "chips": {"type": "array", "items": STR},
        },
        ["text", "depth", "cards", "chips"],
    ),
]

DECLARATIONS_BY_NAME = {d["name"]: d for d in DECLARATIONS}


def tool_declarations():
    return [
        types.FunctionDeclaration(
            name=d["name"],
            description=d["description"],
            parameters_json_schema=d["parameters"],
        )
        for d in DECLARATIONS
    ]


# --- argument validation ---------------------------------------------------

_CASTS = {"string": str, "number": float, "integer": int, "boolean": bool}


def validate_args(name, args):
    """Coerce args to the declared types, drop unknown keys, check required."""
    decl = DECLARATIONS_BY_NAME.get(name)
    if decl is None:
        raise ToolError(f"Unknown tool {name}")
    params = decl["parameters"]
    args = dict(args or {})
    clean = {}
    for key, schema in params["properties"].items():
        if key not in args or args[key] is None:
            continue
        value = args[key]
        cast = _CASTS.get(schema.get("type"))
        if cast is not None:
            try:
                value = cast(value)
            except (TypeError, ValueError) as exc:
                raise ToolError(f"{key} must be {schema['type']}") from exc
            if "enum" in schema and value not in schema["enum"]:
                raise ToolError(f"{key} must be one of {schema['enum']}")
        elif schema.get("type") == "array" and not isinstance(value, list):
            raise ToolError(f"{key} must be a list")
        clean[key] = value
    missing = [k for k in params["required"] if k not in clean]
    if missing:
        raise ToolError(f"Missing arguments: {', '.join(missing)}")
    return clean


# --- helpers ---------------------------------------------------------------


def _last_full_month(on):
    first = on.replace(day=1)
    return (first - timedelta(days=1)).strftime("%Y-%m")


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def unavailable(reason, **extra):
    """What a tool returns when the data does not support the inference.

    Gemini must then say it has no answer instead of using a default.
    """
    return {"available": False, "reason": reason, **extra}


def _missing(value):
    return value is None or value == [] or value == {}


# --- tool implementations --------------------------------------------------


def get_category_spend(ctx, category, month=None):
    month = month or _last_full_month(ctx.today)
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ToolError("month must be YYYY-MM")
    year, mon = (int(x) for x in month.split("-"))
    qs = Transaction.objects.filter(
        customer_id=ctx.customer_id,
        tx_amount_eur__lt=0,
        tx_date__year=year,
        tx_date__month=mon,
    )
    rows = [t for t in qs if _norm(category) in _norm(t.category)]
    if not rows:
        return {
            **unavailable(f"No spending in '{category}' in {month}."),
            "found": False,
            "category": category,
            "month": month,
        }
    total = round(sum(-t.tx_amount_eur for t in rows), 2)
    return {
        "available": True,
        "found": True,
        "category": category,
        "month": month,
        "total": total,
        "count": len(rows),
    }


def get_safe_to_spend(ctx):
    p = ctx.profile
    fc, payday = p.get("forecast", {}), p.get("income", {}).get("payday", {})
    next_payday = payday.get("next_payday")
    if fc.get("safe_to_spend_week") is None:
        return unavailable("Safe to spend could not be computed from the data.")
    bills = [
        b
        for b in fc.get("upcoming_bills", [])
        if not next_payday or b["date"] <= next_payday
    ]
    return {
        "safe_to_spend_week": fc.get("safe_to_spend_week"),
        "balance": p.get("balance"),
        "buffer": fc.get("buffer"),
        "payday_found": payday.get("found", False),
        "next_payday": next_payday,
        "days_to_payday": payday.get("days_to_payday"),
        "bills_before_payday": bills,
        "monthly_saving_planned": p.get("baskets", {}).get("monthly_saving"),
    }


def get_safe_to_save(ctx):
    fc = ctx.profile.get("forecast", {})
    if fc.get("safe_to_save_today") is None:
        return unavailable("Safe to save could not be computed from the data.")
    return {
        "safe_to_save_today": fc.get("safe_to_save_today"),
        "danger_days": fc.get("danger_days", []),
        "buffer": fc.get("buffer"),
    }


def get_baskets(ctx):
    baskets = ctx.profile.get("baskets") or {}
    if not any((baskets.get("totals") or {}).values()):
        return unavailable("No spending found for the latest month.")
    return baskets


def get_level(ctx):
    levels = ctx.profile.get("levels") or {}
    if levels.get("current") is None:
        return unavailable("Levels could not be computed from the data.")
    return levels


def simulate_cut(ctx, category, pct, goal_id=None):
    """#24 cut a category by pct; #26 goal date before/after."""
    if pct > 1:
        pct = pct / 100
    if not 0 <= pct <= 1:
        raise ToolError("pct must be between 0 and 1")
    means = ctx.profile.get("whatif", {}).get("category_means", {})
    match = next(
        (
            c
            for c in means
            if _norm(category) in _norm(c) or _norm(c) in _norm(category)
        ),
        None,
    )
    if match is None:
        return {
            **unavailable(f"No recent spending in '{category}' to cut."),
            "found": False,
            "category": category,
        }
    monthly_spend = means[match]
    monthly = round(pct * monthly_spend, 2)
    out = {
        "found": True,
        "category": match,
        "pct": pct,
        "monthly_spend": monthly_spend,
        "monthly_saving": monthly,
        "yearly_saving": round(monthly * 12, 2),
    }
    goals = ctx.profile.get("goals", {}).get("active", [])
    goal = next((g for g in goals if g["id"] == goal_id), None)
    if goal_id is not None and goal is None:
        out["goal"] = {"found": False}
    elif goal is not None:
        rate = float(ctx.profile.get("baskets", {}).get("monthly_saving") or 0)
        remaining = float(goal["target"]) - float(goal["saved"])
        before = math.ceil(remaining / rate) if rate > 0 else None
        after = math.ceil(remaining / (rate + monthly)) if rate + monthly > 0 else None
        out["goal"] = {
            "id": goal["id"],
            "name": goal["name"],
            "target": goal["target"],
            "saved": goal["saved"],
            "monthly_rate": rate,
            "months_before": before,
            "months_after": after,
            "months_sooner": (before - after) if before and after else None,
        }
    return out


def forecast_balance(ctx):
    fc = ctx.profile.get("forecast", {})
    if _missing(fc.get("end_of_month")):
        return unavailable("The balance forecast could not be computed.")
    return {
        "balance": ctx.profile.get("balance"),
        "end_of_month": fc.get("end_of_month"),
        "danger_days": fc.get("danger_days", []),
        "upcoming_bills": fc.get("upcoming_bills", []),
        "seasonal": fc.get("seasonal"),
    }


def get_spender_type(ctx):
    habits = ctx.profile.get("habits") or {}
    if not (habits.get("spender_type") or {}).get("label"):
        return unavailable("Not enough spending to tell a spender type.")
    return habits


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


def get_mortgage_readiness(ctx):
    m = dict(ctx.profile.get("mortgage", {}))
    if (m.get("readiness") or {}).get("score") is None:
        return unavailable(
            "The mortgage readiness model has not been fitted on the mortgage "
            "files (run manage.py build_artifacts)."
        )
    m["loan_details_entered"] = services.latest_loan(ctx.customer_id) is not None
    m["note"] = "Guidance only, not a loan decision."
    return m


EXPLAINERS = {
    "safe to spend": (
        "What you can spend this week without touching bills, savings or your "
        "buffer.",
        lambda p: {"value": p.get("forecast", {}).get("safe_to_spend_week")},
    ),
    "buffer": (
        "A small cushion kept aside for surprises: the larger of EUR 50 or 10% of "
        "your monthly essentials.",
        lambda p: {"value": p.get("forecast", {}).get("buffer")},
    ),
    "leaky": (
        "Small everyday spending that slips away, like coffee, snacks, takeaway "
        "and taxis.",
        lambda p: {"value": p.get("baskets", {}).get("totals", {}).get("leaky")},
    ),
    "essentials": (
        "Must-pay regular costs: rent, utilities, insurance, loans, groceries.",
        lambda p: {"value": p.get("baskets", {}).get("monthly_essentials")},
    ),
    "surprises": (
        "Must-pay costs that come irregularly, like a car repair or the dentist.",
        lambda p: {"value": p.get("forecast", {}).get("surprise_fund_monthly")},
    ),
    "saver": (
        "Money you move aside for later: savings, investments and goal pots.",
        lambda p: {"value": p.get("baskets", {}).get("monthly_saving")},
    ),
    "dsti": (
        "Debt service to income: the share of your net income going to loan "
        "payments. Finland's limit is 60% at a 6% stress rate.",
        lambda p: {"value": p.get("mortgage", {}).get("dsti")},
    ),
    "safety net": (
        "Your lowest balance measured in months of essentials. One month or more "
        "means you have a safety net.",
        lambda p: {"value": p.get("levels", {}).get("buffer_months")},
    ),
}


def get_explainer(ctx, term):
    key = next((k for k in EXPLAINERS if k in _norm(term)), None)
    if key is None:
        return {"found": False, "term": term}
    text, numbers = EXPLAINERS[key]
    values = {k: v for k, v in numbers(ctx.profile).items() if v is not None}
    return {"found": True, "term": key, "text": text, **values}


def get_benchmark(ctx, kind, category=None):
    rows = ctx.profile.get("benchmarks", {}).get(kind, [])
    if category:
        rows = [r for r in rows if _norm(category) in _norm(r["category"])]
    if not rows:
        return unavailable(
            "No peer group of at least 20 customers to compare with.", kind=kind
        )
    return {
        "kind": kind,
        "rows": rows,
        "source": ctx.profile.get("benchmarks", {}).get("source"),
    }


# --- alert coach -----------------------------------------------------------


def _open_alerts(ctx):
    return services.active_alerts(ctx.customer_id, ctx.profile, services.today())


def _df(ctx):
    df = services.transactions_df(ctx.customer_id)
    return df if df is not None else services.empty_df()


def get_alerts(ctx):
    return {"alerts": _open_alerts(ctx)}


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
            "merchant_id": t.merchant_id,
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
    if not ctx.user_confirmed("accept_plan"):
        ctx.pending["accept_plan"] = actions
        return {
            "status": "needs_confirmation",
            "actions": actions,
            "instruction": "Ask the user to accept the plan. Nothing was saved.",
        }
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


TOOLS = {
    "get_category_spend": get_category_spend,
    "get_safe_to_spend": get_safe_to_spend,
    "get_safe_to_save": get_safe_to_save,
    "get_baskets": get_baskets,
    "get_level": get_level,
    "simulate_cut": simulate_cut,
    "forecast_balance": forecast_balance,
    "get_spender_type": get_spender_type,
    "list_goals": list_goals,
    "create_goal": create_goal,
    "rate_goal": rate_goal,
    "get_detected_goals": get_detected_goals,
    "get_mortgage_readiness": get_mortgage_readiness,
    "get_explainer": get_explainer,
    "get_benchmark": get_benchmark,
    "get_alerts": get_alerts,
    "explain_alert": explain_alert,
    "suggest_fixes": suggest_fixes,
    "simulate_plan": simulate_plan,
    "accept_plan": accept_plan,
    "snooze_alert": snooze_alert,
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
