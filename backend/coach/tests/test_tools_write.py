"""Write tools: manage_goal, save_loan_details, dismiss_suggestion.

Every write is proposed first and runs only when the next user message says
yes to the same proposal. The one fast path is manage_goal add_saved when
Python can see the request is unambiguous (option C): the exact amount is in
the user's message, one active goal fits, and it does not overshoot.
"""

from datetime import date, timedelta

import pytest

from coach import services
from coach.gemini.tools import DECLARATIONS, TOOLS, ToolContext, call_tool
from coach.models import DismissedSuggestion, Goal, LoanDetails

from .conftest import AINO, TODAY

WRITE_TOOLS = {"manage_goal", "save_loan_details", "dismiss_suggestion"}


def turn(name, args, message, previous=None, customer=AINO):
    """One tool call in a chat turn; returns (result, pending for next turn)."""
    ctx = ToolContext(customer, message, previous_pending=previous)
    return call_tool(ctx, name, args), ctx.pending


def confirmed(name, args, first="Please do that"):
    """Propose, then say yes with the same args; returns the second result."""
    _, pending = turn(name, args, first)
    result, _ = turn(name, args, "Yes, go ahead", previous=pending)
    return result


def make_goal(name="Japan", target=1500.0, saved=0.0, **extra):
    return Goal.objects.create(
        customer_id=AINO,
        name=name,
        target=target,
        saved=saved,
        start_date=TODAY,
        target_date=date(2027, 6, 1),
        **extra,
    )


def test_write_tools_declared_and_registered():
    assert WRITE_TOOLS <= {d["name"] for d in DECLARATIONS}
    assert WRITE_TOOLS <= set(TOOLS)


# --- confirmation ----------------------------------------------------------------


def test_edit_is_proposed_not_saved(aino):
    goal = make_goal()
    args = {"goal_id": goal.id, "action": "edit", "changes": {"name": "Tokyo"}}
    out, pending = turn("manage_goal", args, "Rename it to Tokyo")
    assert out["status"] == "needs_confirmation"
    assert "manage_goal" in pending
    goal.refresh_from_db()
    assert goal.name == "Japan"


def test_edit_saved_after_yes_to_same_proposal(aino):
    goal = make_goal()
    args = {"goal_id": goal.id, "action": "edit", "changes": {"name": "Tokyo"}}
    out = confirmed("manage_goal", args)
    assert out["status"] == "updated"
    goal.refresh_from_db()
    assert goal.name == "Tokyo"


def test_yes_to_a_different_proposal_is_not_saved(aino):
    goal = make_goal()
    first = {"goal_id": goal.id, "action": "edit", "changes": {"name": "Tokyo"}}
    _, pending = turn("manage_goal", first, "Rename it to Tokyo")
    other = {"goal_id": goal.id, "action": "edit", "changes": {"name": "Osaka"}}
    out, _ = turn("manage_goal", other, "yes", previous=pending)
    assert out["status"] == "needs_confirmation"
    goal.refresh_from_db()
    assert goal.name == "Japan"


def test_yes_without_any_proposal_is_not_saved(aino):
    goal = make_goal()
    args = {"goal_id": goal.id, "action": "pause"}
    out, _ = turn("manage_goal", args, "yes")
    assert out["status"] == "needs_confirmation"
    goal.refresh_from_db()
    assert goal.paused is False


# --- manage_goal actions ---------------------------------------------------------


def test_unknown_or_foreign_goal_is_an_error(aino):
    other = Goal.objects.create(
        customer_id="someone-else",
        name="Car",
        target=100,
        start_date=TODAY,
        target_date=date(2027, 1, 1),
    )
    for goal_id in (other.id, 999999):
        out, _ = turn("manage_goal", {"goal_id": goal_id, "action": "pause"}, "x")
        assert "error" in out


@pytest.mark.parametrize(
    "changes",
    [{"amount": -5}, {"date": (TODAY - timedelta(days=1)).isoformat()}],
)
def test_edit_uses_the_goal_form_validation(aino, changes):
    goal = make_goal()
    out, _ = turn(
        "manage_goal", {"goal_id": goal.id, "action": "edit", "changes": changes}, "x"
    )
    assert "error" in out


def test_pause_then_resume_shifts_dates_like_the_rest_api(aino, settings):
    goal = make_goal()
    confirmed("manage_goal", {"goal_id": goal.id, "action": "pause"})
    goal.refresh_from_db()
    assert goal.paused is True and goal.paused_at == TODAY

    settings.AS_OF_DATE = (TODAY + timedelta(days=10)).isoformat()
    confirmed("manage_goal", {"goal_id": goal.id, "action": "resume"})
    goal.refresh_from_db()
    assert goal.paused is False
    assert goal.target_date == date(2027, 6, 11)


def test_pause_twice_is_an_error(aino):
    goal = make_goal(paused=True, paused_at=TODAY)
    out, _ = turn("manage_goal", {"goal_id": goal.id, "action": "pause"}, "x")
    assert "error" in out


@pytest.mark.parametrize("action, status", [("complete", "completed")])
def test_complete_sets_status(aino, action, status):
    goal = make_goal()
    confirmed("manage_goal", {"goal_id": goal.id, "action": action})
    goal.refresh_from_db()
    assert goal.status == status


def test_abandon_sets_status(aino):
    goal = make_goal()
    confirmed("manage_goal", {"goal_id": goal.id, "action": "abandon"})
    goal.refresh_from_db()
    assert goal.status == "abandoned"


def test_finished_goal_cannot_be_changed(aino):
    goal = make_goal(status="completed")
    out, _ = turn("manage_goal", {"goal_id": goal.id, "action": "pause"}, "x")
    assert "error" in out


def test_check_step_ticks_a_plan_step(aino):
    goal = make_goal(
        name="My money plan",
        type="plan",
        checklist=[{"text": "Cut takeaway", "done": False, "action": {}}],
    )
    confirmed("manage_goal", {"goal_id": goal.id, "action": "check_step", "step": 0})
    goal.refresh_from_db()
    assert goal.checklist[0]["done"] is True


@pytest.mark.parametrize("step", [5, None])
def test_check_step_needs_a_valid_step(aino, step):
    goal = make_goal(type="plan", checklist=[{"text": "a", "done": False}])
    args = {"goal_id": goal.id, "action": "check_step"}
    if step is not None:
        args["step"] = step
    out, _ = turn("manage_goal", args, "x")
    assert "error" in out


def test_profile_is_rebuilt_after_a_write(aino):
    goal = make_goal()
    services.get_profile(AINO)
    confirmed(
        "manage_goal",
        {"goal_id": goal.id, "action": "edit", "changes": {"name": "Tokyo"}},
    )
    names = [g["name"] for g in services.get_profile(AINO)["goals"]["active"]]
    assert "Tokyo" in names


# --- add_saved fast path (option C) ------------------------------------------------


def add(goal, amount, message, previous=None):
    args = {"goal_id": goal.id, "action": "add_saved", "amount": amount}
    return turn("manage_goal", args, message, previous=previous)


def test_add_saved_runs_at_once_when_unambiguous(aino):
    goal = make_goal()
    out, pending = add(goal, 50, "I put €50 in my trip fund")
    assert out["status"] == "updated"
    goal.refresh_from_db()
    assert goal.saved == 50
    assert pending["undo"] == {"goal_id": goal.id, "amount": 50.0}


def test_add_saved_asks_when_amount_not_in_message(aino):
    goal = make_goal()
    out, _ = add(goal, 50, "Add some money to my goal")
    assert out["status"] == "needs_confirmation"
    goal.refresh_from_db()
    assert goal.saved == 0


def test_add_saved_asks_when_several_goals_and_none_named(aino):
    goal = make_goal()
    make_goal(name="Car")
    out, _ = add(goal, 50, "I put 50 in")
    assert out["status"] == "needs_confirmation"


def test_add_saved_runs_when_the_goal_is_named(aino):
    goal = make_goal()
    make_goal(name="Car")
    out, _ = add(goal, 50, "I put 50 in Japan")
    assert out["status"] == "updated"


def test_add_saved_asks_when_it_overshoots_the_target(aino):
    goal = make_goal(target=100, saved=80)
    out, _ = add(goal, 50, "I put 50 in")
    assert out["status"] == "needs_confirmation"


def test_add_saved_runs_after_confirmation(aino):
    goal = make_goal()
    _, pending = add(goal, 50, "Add some money")
    out, _ = add(goal, 50, "yes", previous=pending)
    assert out["status"] == "updated"
    goal.refresh_from_db()
    assert goal.saved == 50


@pytest.mark.parametrize("amount", [0, -20])
def test_add_saved_needs_a_positive_amount(aino, amount):
    goal = make_goal()
    out, _ = add(goal, amount, f"I put {amount} in")
    assert "error" in out


def test_undo_reverses_the_last_add(aino):
    goal = make_goal()
    _, pending = add(goal, 50, "I put 50 in")
    out, _ = turn(
        "manage_goal", {"goal_id": goal.id, "action": "undo"}, "Undo", previous=pending
    )
    assert out["status"] == "updated"
    goal.refresh_from_db()
    assert goal.saved == 0


def test_undo_without_a_previous_add_is_an_error(aino):
    goal = make_goal(saved=50)
    out, _ = turn("manage_goal", {"goal_id": goal.id, "action": "undo"}, "Undo")
    assert "error" in out
    goal.refresh_from_db()
    assert goal.saved == 50


# --- save_loan_details ---------------------------------------------------------------

LOAN = {"balance": 120000, "interest_rate": 4.0, "years_left": 20}


def test_loan_is_proposed_then_saved(aino):
    out, pending = turn("save_loan_details", LOAN, "My loan is 120k at 4%")
    assert out["status"] == "needs_confirmation"
    assert LoanDetails.objects.count() == 0
    out, _ = turn("save_loan_details", LOAN, "yes", previous=pending)
    assert out["status"] == "saved"
    assert LoanDetails.objects.get().balance == 120000
    assert out["mortgage"]["loan_details"]["balance"] == 120000


@pytest.mark.parametrize(
    "bad",
    [{"interest_rate": 25}, {"years_left": 0}, {"balance": -1}],
)
def test_loan_uses_the_loan_form_validation(aino, bad):
    out, _ = turn("save_loan_details", {**LOAN, **bad}, "x")
    assert "error" in out


# --- dismiss_suggestion ----------------------------------------------------------------


def _detected_ids():
    return [g["id"] for g in services.get_profile(AINO)["goals"]["detected"]]


def test_dismissed_suggestion_never_shows_again(aino):
    target = _detected_ids()[0]
    out = confirmed("dismiss_suggestion", {"suggestion_id": target})
    assert out["status"] == "dismissed"
    assert DismissedSuggestion.objects.filter(customer_id=AINO).count() == 1
    assert target not in _detected_ids()


def test_dismiss_is_proposed_first(aino):
    target = _detected_ids()[0]
    out, _ = turn("dismiss_suggestion", {"suggestion_id": target}, "hide that")
    assert out["status"] == "needs_confirmation"
    assert target in _detected_ids()


def test_dismiss_unknown_suggestion_is_an_error(aino):
    out, _ = turn("dismiss_suggestion", {"suggestion_id": "det-nope"}, "x")
    assert "error" in out
