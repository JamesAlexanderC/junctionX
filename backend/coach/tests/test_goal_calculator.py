"""calculate_goal: goal maths for numbers the user types (live tests #26, #50,
"Can I reach it sooner?"). Python computes months, dates, monthly need,
difficulty and realism; Gemini never does the arithmetic.

Test Aino saves EUR 150 a month (baskets.monthly_saving); today 18 Oct 2026.
"""

import pytest

from coach import services
from coach.gemini.tools import DECLARATIONS, TOOLS, ToolContext, call_tool
from inferences import goals as goal_maths
from inferences import models

from .conftest import AINO, TODAY

pytestmark = pytest.mark.django_db


def _calc(**args):
    return call_tool(ToolContext(AINO), "calculate_goal", args)


def _rate():
    return services.get_profile(AINO)["baskets"]["monthly_saving"]


def test_tool_is_declared_and_registered():
    assert "calculate_goal" in {d["name"] for d in DECLARATIONS}
    assert "calculate_goal" in TOOLS


def test_when_could_i_save_an_amount(aino):
    out = _calc(amount=3000)
    months = models.months_to_goal(3000, 0, _rate())
    assert out["monthly_rate"] == _rate()
    assert out["months_needed"] == months
    assert out["reach_date"] == goal_maths._add_months(TODAY, months)
    assert out["difficulty"] == models.goal_difficulty(months)


def test_a_goal_by_a_date_says_if_it_is_realistic(aino):
    out = _calc(amount=5000, date="2026-12-25")
    need = goal_maths.monthly_needed(5000, 0, TODAY, "2026-12-25")
    assert out["monthly_needed"] == need
    assert out["realistic"] is False
    assert out["suggested_monthly"] == _rate()
    assert out["suggested_date"] == goal_maths._add_months(
        TODAY, models.months_to_goal(5000, 0, _rate())
    )


def test_a_monthly_amount_the_user_gives_is_used(aino):
    out = _calc(amount=3000, monthly=500)
    assert out["monthly_rate"] == 500
    assert out["months_needed"] == models.months_to_goal(3000, 0, 500)


def test_one_off_available_today_is_separate_from_the_monthly_rate(aino):
    out = _calc(amount=3000)
    today = services.get_profile(AINO)["forecast"]["safe_to_save_today"]
    assert out["available_today"] == today
    assert out["monthly_rate"] == _rate()  # not rate + one-off


@pytest.mark.parametrize(
    "args",
    [
        {"amount": 0},
        {"amount": 100, "date": "2020-01-01"},
        {"amount": 100, "monthly": -5},
    ],
)
def test_bad_inputs_are_errors(aino, args):
    assert "error" in _calc(**args)


def test_goal_proposal_carries_the_check(aino):
    ctx = ToolContext(AINO, "Save 5000 by Christmas")
    out = call_tool(
        ctx, "create_goal", {"name": "Xmas", "amount": 5000, "date": "2026-12-25"}
    )
    assert out["status"] == "needs_confirmation"
    assert out["check"]["realistic"] is False
    assert out["check"]["monthly_needed"] > 0


def test_list_goals_explains_the_one_off_in_safe_to_save(aino):
    out = call_tool(ToolContext(AINO), "list_goals", {})
    assert "one-off" in out["clash_note"]


def test_prompt_says_to_use_the_calculator():
    from coach.gemini.system_prompt import SYSTEM_PROMPT

    assert "calculate_goal" in SYSTEM_PROMPT
