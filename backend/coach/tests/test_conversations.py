"""Conversations isolate stored context, confirmations and cached replies."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from coach.models import ChatTurn, Conversation, Goal
from .conftest import AINO, response

pytestmark = pytest.mark.django_db
GOAL = {"name": "Japan", "amount": 1500, "date": "2027-06-01"}


def chat(client, conversation, message="Hello"):
    return client.post(
        "/api/chat/",
        {
            "customer_id": AINO,
            "message": message,
            "depth": 4,
            "conversation_id": str(conversation),
        },
        content_type="application/json",
    )


def reply():
    return response(("send_reply", {"text": "Done.", "depth": 4}))


def test_history_and_confirmation_are_isolated(client, aino, fake_gemini):
    first, second = uuid4(), uuid4()
    fake_gemini(response(("create_goal", GOAL)), reply())
    chat(client, first, "Private conversation about Japan")
    fake = fake_gemini(response(("create_goal", GOAL)), reply())
    out = chat(client, second, "Yes")
    assert out.status_code == 200
    assert Goal.objects.count() == 0
    assert out.json()["state_changed"] is False
    contents = str(fake.models.calls[0]["contents"])
    assert "Private conversation" not in contents
    fake_gemini(response(("create_goal", GOAL)), reply())
    assert chat(client, first, "Yes").json()["state_changed"] is True
    assert Goal.objects.count() == 1


def test_other_user_cannot_open_conversation(client, aino, fake_gemini):
    conversation = uuid4()
    fake_gemini(reply())
    chat(client, conversation)
    other = APIClient()
    other.force_authenticate(get_user_model().objects.create_user("other"))
    assert chat(other, conversation).status_code == 404
    assert ChatTurn.objects.count() == 1


def test_legacy_history_is_not_attached_to_new_conversations(client, aino, fake_gemini):
    ChatTurn.objects.create(customer_id=AINO, message="Old private history")
    fake = fake_gemini(reply())
    chat(client, uuid4())
    assert "Old private history" not in str(fake.models.calls[0]["contents"])
    assert Conversation.objects.count() == 1


def test_conversation_cannot_switch_customer(client, aino, fake_gemini):
    fake_gemini(reply())
    conversation = uuid4()
    chat(client, conversation)
    out = client.post(
        "/api/chat/",
        {
            "customer_id": "different",
            "message": "Hello",
            "depth": 1,
            "conversation_id": str(conversation),
        },
        content_type="application/json",
    )
    assert out.status_code == 404
