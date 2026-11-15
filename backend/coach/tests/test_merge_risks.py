"""Risks from merging main, develop and per-user conversations (PR #19)."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from coach.gemini.validate import ReplyError, numbers_in_text, validate_reply
from coach.models import Goal

from .conftest import AINO, response

# --- 2: a slider cut saved as a plan, through the chat --------------------------

SLIDER_CUT = {"type": "cut_category", "category": "groceries", "pct": 25}


def _say(client, message):
    return client.post(
        "/api/chat/",
        {"customer_id": AINO, "message": message, "depth": 4},
        content_type="application/json",
    ).json()


def _accept_turn(fake_gemini, action=SLIDER_CUT):
    fake_gemini(
        response(("accept_plan", {"actions": [action]})),
        response(("send_reply", {"text": "Ok.", "depth": 4, "cards": []})),
    )


@pytest.mark.django_db
def test_slider_plan_is_saved_once_through_the_chat(client, aino, fake_gemini):
    _accept_turn(fake_gemini)
    assert _say(client, "Save this cut as a plan")["state_changed"] is False
    _accept_turn(fake_gemini)
    assert _say(client, "Yes")["state_changed"] is True
    _accept_turn(fake_gemini)
    _say(client, "Accept plan")
    assert Goal.objects.filter(type="plan").count() == 1


@pytest.mark.django_db
def test_yes_to_a_changed_slider_cut_is_asked_again(client, aino, fake_gemini):
    _accept_turn(fake_gemini)
    _say(client, "Save this cut as a plan")
    _accept_turn(fake_gemini, {**SLIDER_CUT, "pct": 30})
    assert _say(client, "Yes")["state_changed"] is False
    assert Goal.objects.count() == 0


# --- 4: two users on the same customer, no conversation id -----------------------

GOAL = {"name": "Japan", "amount": 1500, "date": "2027-06-01"}


def _client_for(username):
    user = get_user_model().objects.create_user(username, password="pw-123456789")
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.mark.django_db
def test_one_users_proposal_cannot_be_confirmed_by_another(aino, fake_gemini):
    alice, bob = _client_for("alice"), _client_for("bob")
    fake_gemini(
        response(("create_goal", GOAL)),
        response(("send_reply", {"text": "Shall I?", "depth": 4})),
    )
    _say(alice, "Private plan for Japan")
    fake = fake_gemini(
        response(("create_goal", GOAL)),
        response(("send_reply", {"text": "Ok.", "depth": 4})),
    )
    out = _say(bob, "Yes")
    assert Goal.objects.count() == 0
    assert out["state_changed"] is False
    assert "Private plan" not in str(fake.models.calls[0]["contents"])
    assert out["conversation_id"]


# --- 7: signed numbers and Finnish formats in replies ----------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("drops to -120.50 € on the 8th", [-120.5, 8]),
        ("drops to -1 428,40 €", [-1428.4]),
        ("likely 20-160 €", [20, 160]),
        ("+15.64 € back", [15.64]),
        ("1.428,40 € rent", [1428.4]),
    ],
)
def test_numbers_keep_their_sign_and_grouping(text, expected):
    assert numbers_in_text(text) == expected


def test_a_negative_balance_matches_its_tool_value():
    reply = {"text": "Your balance may drop to -120.50 €.", "depth": 1}
    assert validate_reply(reply, [{"low": -120.5}])["text"] == reply["text"]


def test_a_sign_flip_is_rejected():
    reply = {"text": "Your balance may drop to -120.50 €.", "depth": 1}
    with pytest.raises(ReplyError):
        validate_reply(reply, [{"low": 120.5}])
