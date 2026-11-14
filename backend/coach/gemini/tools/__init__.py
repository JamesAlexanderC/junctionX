"""Gemini tool declarations and their Python implementations (P2.2).

Each tool is ``fn(ctx, **args)``; ``ctx`` is a :class:`ToolContext` with the
customer id, the cached profile and the confirmation state of this turn.
Every number a tool returns comes from the precomputed profile or an
inference formula; Gemini only explains them.

Layout: ``context`` (ToolContext, helpers), ``declarations`` (schemas and
argument validation), ``read`` / ``goals`` / ``alerts`` (implementations),
``registry`` (name -> function, availability gating, ``call_tool``).
"""

from .alerts import snooze_alert
from .context import CONFIRM_RE, ToolContext, ToolError, unavailable
from .declarations import DECLARATIONS, tool_declarations, validate_args
from .goals import create_goal, rate_goal
from .registry import TOOLS, call_tool, check_available

__all__ = [
    "CONFIRM_RE",
    "DECLARATIONS",
    "TOOLS",
    "ToolContext",
    "ToolError",
    "call_tool",
    "check_available",
    "create_goal",
    "rate_goal",
    "snooze_alert",
    "tool_declarations",
    "unavailable",
    "validate_args",
]
