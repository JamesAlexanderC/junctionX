"""Saldo REST API (CLAUDE.md "API", P2.1, P2.5, P2.8)."""

import json
import logging
from itertools import chain

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import insights as insights_mod
from . import services
from .gemini import loop
from .gemini.tools import ToolContext, rate_goal, snooze_alert
from .models import Conversation, Goal, LoanDetails
from .serializers import (
    ChatRequest,
    GoalSerializer,
    LoanSerializer,
    RateSerializer,
    SnoozeSerializer,
)

log = logging.getLogger("coach.api")
NDJSON = "application/x-ndjson"


def _not_found(customer_id):
    return Response(
        {"detail": f"Unknown customer {customer_id}"}, status=status.HTTP_404_NOT_FOUND
    )


@api_view(["GET"])
def customers(request):
    try:
        limit = max(1, min(500, int(request.query_params.get("limit", 50))))
    except ValueError:
        limit = 50
    return Response(
        services.list_customers(q=request.query_params.get("q"), limit=limit)
    )


@api_view(["GET"])
def demo_customers(request):
    """Demo picks (one per app level) and every customer with their income
    level, app level and spender type (build_customer_index)."""
    return Response(services.demo_directory())


@api_view(["GET"])
def insights(request, customer_id):
    profile = services.get_profile(customer_id)
    if profile is None:
        return _not_found(customer_id)
    profile = dict(profile)
    profile["alerts"] = services.active_alerts(customer_id, profile)
    return Response(
        {
            "customer_id": customer_id,
            "as_of": profile.get("today"),
            "insights": insights_mod.insights(profile),
        }
    )


@api_view(["GET"])
def home(request, customer_id):
    profile = services.get_profile(customer_id)
    if profile is None:
        return _not_found(customer_id)
    profile = dict(profile)
    profile["alerts"] = services.active_alerts(customer_id, profile)
    return Response(profile)


@api_view(["POST"])
def chat(request):
    """POST {customer_id, message, history, depth?} -> send_reply JSON.

    With ?stream=1 the answer is NDJSON instead, one event a line, so the
    chat can show what the coach is doing (coach/gemini/progress.py):
    {"type": "step"|"thought", "text"} while it works, then {"type": "reply",
    "reply": <send_reply>}, or {"type": "error", "error"} if it broke midway.
    404 and 503 are still plain JSON statuses, sent before any event.
    """
    req = ChatRequest(data=request.data)
    req.is_valid(raise_exception=True)
    data = req.validated_data
    conversation = _conversation_for(request.user, data)
    if conversation is None:
        return Response({"detail": "Conversation not found"}, status=404)
    # History comes from the stored turns of this conversation, not the client.
    events = loop.chat_stream(
        data["customer_id"],
        data["message"],
        history=None,
        conversation=conversation,
        depth=data.get("depth"),
    )
    try:
        first = next(events)
    except LookupError:
        return _not_found(data["customer_id"])
    except loop.GeminiNotConfigured as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    events = _with_conversation_id(chain([first], events), conversation)
    if request.query_params.get("stream") != "1":
        done = [e for e in events if e["type"] == "done"]
        return Response(done[-1]["reply"])
    response = StreamingHttpResponse(_ndjson(events), content_type=NDJSON)
    # Proxies must pass each line on at once, not buffer the whole answer.
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _conversation_for(user, data):
    """The user's conversation for this customer; None if the id given belongs
    to another user or customer."""
    customer_id = data["customer_id"]
    conversation_id = data.get("conversation_id")
    if conversation_id:
        conversation, _ = Conversation.objects.get_or_create(
            pk=conversation_id,
            defaults={"owner": user, "customer_id": customer_id},
        )
        if conversation.owner_id != user.pk or conversation.customer_id != customer_id:
            return None
        return conversation
    # Compatibility for clients predating conversation ids, scoped per user.
    conversation = (
        Conversation.objects.filter(owner=user, customer_id=customer_id)
        .order_by("created_at")
        .first()
    )
    return conversation or Conversation.objects.create(
        owner=user, customer_id=customer_id
    )


def _with_conversation_id(events, conversation):
    """Add conversation_id to the final reply so the client can continue it."""
    for e in events:
        if e["type"] == "done":
            e = {**e, "reply": {**e["reply"], "conversation_id": str(conversation.id)}}
        yield e


def _ndjson(events):
    """One JSON line per event; the final "done" (reply and meta) goes out as
    {"type": "reply", "reply"} without the meta."""

    def line(event):
        return json.dumps(event, default=str) + "\n"

    try:
        for e in events:
            if e["type"] == "done":
                yield line({"type": "reply", "reply": e["reply"]})
            else:
                yield line(e)
    except Exception:  # noqa: BLE001 - the status line is already sent
        log.exception("chat stream failed")
        yield line({"type": "error", "error": "The coach stopped unexpectedly."})


def _panel(request, summary):
    """GET ?customer_id= -> {customer_id, as_of, **summary(profile)}."""
    customer_id = request.query_params.get("customer_id")
    if not customer_id:
        return Response(
            {"detail": "customer_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    profile = services.get_profile(customer_id)
    if profile is None:
        return _not_found(customer_id)
    return Response(
        {
            "customer_id": customer_id,
            "as_of": profile.get("today"),
            **summary(profile),
        }
    )


@api_view(["GET"])
def spending(request):
    """GET ?customer_id= lists spending per data category for the Overview."""
    return _panel(request, insights_mod.spending_summary)


@api_view(["GET", "POST"])
def goals(request):
    """GET ?customer_id= lists goals for the Overview; POST creates one (#64)."""
    if request.method == "GET":
        return _panel(request, insights_mod.goal_summary)
    ser = GoalSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    if services.get_profile(ser.validated_data["customer_id"]) is None:
        return _not_found(ser.validated_data["customer_id"])
    goal = ser.save()
    profile = services.refresh_profile(goal.customer_id)
    return Response(
        {"goal": GoalSerializer(goal).data, "profile": profile},
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
def goal_detail(request, goal_id):
    goal = get_object_or_404(Goal, pk=goal_id)
    ser = GoalSerializer(goal, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    goal = ser.save()
    profile = services.refresh_profile(goal.customer_id)
    return Response({"goal": GoalSerializer(goal).data, "profile": profile})


@api_view(["POST"])
def goal_rate(request, goal_id):
    """#54 rate a goal (DB goal id) or a suggested goal type (rec-*/det-* id)."""
    ser = RateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    goal = Goal.objects.filter(pk=goal_id).first() if goal_id.isdigit() else None
    if goal is not None:
        customer_id, goal_type = goal.customer_id, goal.type
    else:
        customer_id = request.data.get("customer_id")
        goal_type = request.data.get("goal_type")
        if not customer_id or not goal_type:
            return Response(
                {"detail": "customer_id and goal_type are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    ctx = ToolContext(customer_id)
    return Response(rate_goal(ctx, goal_type, ser.validated_data["up"]))


@api_view(["POST"])
def loans(request):
    ser = LoanSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    if services.get_profile(data["customer_id"]) is None:
        return _not_found(data["customer_id"])
    LoanDetails.objects.create(**data)
    profile = services.refresh_profile(data["customer_id"])
    return Response(
        {"mortgage": profile.get("mortgage", {})}, status=status.HTTP_201_CREATED
    )


@api_view(["GET"])
def alerts(request, customer_id):
    profile = services.get_profile(customer_id)
    if profile is None:
        return _not_found(customer_id)
    return Response({"alerts": services.active_alerts(customer_id, profile)})


@api_view(["POST"])
def alert_snooze(request, alert_id):
    ser = SnoozeSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    ctx = ToolContext(ser.validated_data["customer_id"])
    return Response(snooze_alert(ctx, alert_id, ser.validated_data["days"]))
