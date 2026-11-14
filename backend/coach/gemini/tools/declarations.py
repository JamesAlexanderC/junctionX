"""Gemini function declarations and argument validation (P2.2)."""

from google.genai import types

from ..catalogue import CATALOGUE, section
from .context import ToolError
from .goals import GOAL_ACTIONS

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

SNAPSHOT = {
    "type": "object",
    "properties": {"safe_to_spend": NUM, "buffer_months": NUM, "goal_date": STR},
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
        # Nested fields are listed so Gemini can fill them (F4); keep them in
        # line with coach/gemini/cards.py (test_validate checks it).
        "goal": {
            "type": "object",
            "properties": {"target": NUM, "saved": NUM, "monthly_rate": NUM},
        },
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
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": STR,
                    "monthly_impact": NUM,
                    "clears": {"type": "array", "items": STR},
                },
            },
        },
        "before": SNAPSHOT,
        "after": SNAPSHOT,
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
    _decl(
        "manage_goal",
        "Change a saved goal: edit (changes), pause, resume, complete, abandon, "
        "add_saved (amount the user says they put in), check_step (plan step) "
        "or undo the last add_saved. Proposed first; saved after the user "
        "confirms. add_saved runs at once when the user's message states the "
        "amount and the goal is clear.",
        {
            "goal_id": INT,
            "action": {"type": "string", "enum": GOAL_ACTIONS},
            "changes": {
                "type": "object",
                "properties": {
                    "name": STR,
                    "amount": NUM,
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "emoji": STR,
                },
            },
            "amount": NUM,
            "step": INT,
        },
        ["goal_id", "action"],
    ),
    _decl("get_detected_goals", "Goals detected from the data, as suggestions."),
    _decl(
        "dismiss_suggestion",
        "Hide a detected goal suggestion for good. Only after the user confirmed.",
        {"suggestion_id": STR},
        ["suggestion_id"],
    ),
    _decl(
        "save_loan_details",
        "Save the loan balance (EUR), interest rate (percent a year) and years "
        "left the user told you. Only after the user confirmed.",
        {"balance": NUM, "interest_rate": NUM, "years_left": INT},
        ["balance", "interest_rate", "years_left"],
    ),
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
    _decl(
        "list_inferences",
        "Every computed inference for this user: item key, what it is, whether "
        "the data supports it (with the reason if not) and if it can be charted.",
        {
            "section": {
                "type": "string",
                "enum": sorted({section(item) for item in CATALOGUE}),
            }
        },
    ),
    _decl(
        "get_inference",
        "Read one computed inference by item key (see list_inferences). "
        "Chartable items include chart_data for a chart card.",
        {
            "item": {"type": "string", "enum": list(CATALOGUE)},
            "detail": {"type": "string", "enum": ["summary", "full"]},
        },
        ["item"],
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
        elif schema.get("type") == "object" and not isinstance(value, dict):
            raise ToolError(f"{key} must be an object")
        clean[key] = value
    missing = [k for k in params["required"] if k not in clean]
    if missing:
        raise ToolError(f"Missing arguments: {', '.join(missing)}")
    return clean
