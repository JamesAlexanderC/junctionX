"""Saldo REST API (CLAUDE.md "API", P2.1, P2.5, P2.8)."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import insights as insights_mod
from . import services
from .gemini import loop
from .gemini.tools import ToolContext, rate_goal, snooze_alert
from .models import Goal, LoanDetails
from .serializers import (
    ChatRequest,
    GoalSerializer,
    LoanSerializer,
    RateSerializer,
    SnoozeSerializer,
)


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
    req = ChatRequest(data=request.data)
    req.is_valid(raise_exception=True)
    data = req.validated_data
    try:
        reply, _meta = loop.chat(
            data["customer_id"],
            data["message"],
            history=data.get("history"),
            depth=data.get("depth"),
        )
    except LookupError:
        return _not_found(data["customer_id"])
    except loop.GeminiNotConfigured as exc:
        return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(reply)


@api_view(["POST"])
def goals(request):
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
