"""REST endpoints for the Money Coach dashboard (see docs/design.md)."""

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import Http404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services
from .analytics import PERSONAS
from .models import Customer, CustomerProfile, MortgageApplication, Transaction

MAX_LIMIT = 200


def _int_param(request, name, default, lo, hi):
    try:
        value = int(request.query_params.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


@api_view(["GET"])
def health(request):
    """Service status, LLM provider and dataset size."""
    configured = bool(settings.GEMINI_API_KEY)
    counts = cache.get("finance:counts")
    if counts is None:
        counts = {
            "customers": Customer.objects.count(),
            "transactions": Transaction.objects.count(),
        }
        cache.set("finance:counts", counts, 300)
    return Response(
        {
            "status": "ok",
            "llm": {
                "provider": "gemini" if configured else "offline",
                "model": settings.GEMINI_MODEL if configured else None,
                "configured": configured,
            },
            "data": counts,
        }
    )


@api_view(["GET"])
def customer_list(request):
    """Paginated customers, searchable by id or postal code."""
    qs = Customer.objects.select_related("profile").order_by("customer_id")
    search = request.query_params.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(customer_id__icontains=search)
            | Q(customer_postal_code__startswith=search)
        )
    persona = request.query_params.get("persona", "").strip()
    if persona:
        qs = qs.filter(profile__persona_key=persona)
    limit = _int_param(request, "limit", 50, 1, MAX_LIMIT)
    offset = _int_param(request, "offset", 0, 0, 10**9)
    page = qs[offset : offset + limit]
    return Response(
        {
            "count": qs.count(),
            "results": [services.customer_summary(c) for c in page],
        }
    )


def featured_customers():
    """One clear example per persona plus an approved and a rejected mortgage.

    Picks are the strongest persona fit among "ordinary" customers: income
    in a typical range and most spending visible in this account (customers
    whose salary is swept elsewhere show very little spend). Persona slots
    skip mortgage applicants, who get their own two slots.
    """
    picked = []
    typical = CustomerProfile.objects.select_related("customer").filter(
        monthly_income__gte=1800,
        monthly_income__lte=7000,
        monthly_spend__gte=1000,
    )
    base = typical.filter(has_mortgage_application=False)
    for key in PERSONAS:
        profile = (
            base.filter(persona_key=key)
            .order_by("-persona_score", "customer_id")
            .first()
        )
        if profile:
            picked.append(profile)
    for decision in ("approved", "rejected"):
        customer_ids = MortgageApplication.objects.filter(
            final_decision=decision
        ).values("customer_id")
        profile = (
            typical.filter(customer_id__in=customer_ids).order_by("customer_id").first()
        )
        if profile:
            picked.append(profile)
    return [services.customer_summary(p.customer, p) for p in picked]


@api_view(["GET"])
def customer_featured(request):
    return Response(featured_customers())


@api_view(["GET"])
def customer_overview(request, customer_id):
    """Everything the customer home screen needs, in one call."""
    try:
        data = services.load_customer(customer_id)
    except Customer.DoesNotExist:
        raise Http404(f"Unknown customer {customer_id}")
    return Response(services.overview(data))
