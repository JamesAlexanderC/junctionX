"""Consent API and mock ASPSP (MULTIBANK_PLAN.md MB-3).

Same auth as the rest of the API. No endpoint takes a credential: any field
besides customer_id and bank_code is refused.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from coach import services
from coach.models import Account, Transaction

from . import aspsp
from .models import BankConsent, LinkedAccount
from .scenarios import BANKS

CONSENT_FIELDS = {"customer_id", "bank_code"}
NO_CREDENTIALS = (
    "Saldo never asks for bank credentials: connecting only uses the consent " "screen."
)


def _consent_json(consent, **extra):
    return {
        "consent_id": consent.id,
        "customer_id": consent.customer_id,
        "bank_code": consent.bank_code,
        "bank_name": consent.bank_name,
        "status": consent.status,
        "scopes": consent.scopes,
        "expires_at": consent.expires_at.isoformat(),
        "simulated": True,
        **extra,
    }


@api_view(["GET"])
def banks(request):
    """Connectable banks: plain text names only."""
    return Response([{"code": c, "name": n} for c, n in BANKS.items()])


@api_view(["POST"])
def consents(request):
    """POST {customer_id, bank_code} -> a pending consent."""
    extra = set(request.data) - CONSENT_FIELDS
    if extra:
        return Response({"detail": NO_CREDENTIALS}, status=status.HTTP_400_BAD_REQUEST)
    customer_id = request.data.get("customer_id")
    bank_code = request.data.get("bank_code")
    if bank_code not in BANKS:
        return Response({"detail": "Unknown bank."}, status=status.HTTP_400_BAD_REQUEST)
    if not customer_id or not services.customer_exists(customer_id):
        return Response({"detail": f"Unknown customer {customer_id}"}, status=404)
    consent = BankConsent.objects.create(
        customer_id=customer_id, bank_code=bank_code, bank_name=BANKS[bank_code]
    )
    return Response(_consent_json(consent), status=status.HTTP_201_CREATED)


@api_view(["POST"])
def authorise(request, consent_id):
    """The user tapped Allow: link the bank's accounts, rebuild the profile."""
    consent = get_object_or_404(BankConsent, pk=consent_id)
    found = aspsp.authorise(consent)
    services.refresh_profile(consent.customer_id)
    extra = {"accounts_found": found}
    if not found:
        extra["message"] = aspsp.NO_ACCOUNTS
    return Response(_consent_json(consent, **extra))


@api_view(["DELETE"])
def consent_detail(request, consent_id):
    """Revoke: delete everything read through this consent, rebuild."""
    consent = get_object_or_404(BankConsent, pk=consent_id)
    aspsp.revoke(consent)
    services.refresh_profile(consent.customer_id)
    return Response(_consent_json(consent))


def _sbank_accounts(customer_id):
    out = []
    for account in Account.objects.filter(customer_id=customer_id):
        last = (
            Transaction.objects.filter(account=account)
            .order_by("-tx_timestamp", "-tx_id")
            .values("balance_after_eur", "tx_date")
            .first()
        ) or {}
        out.append(
            {
                "bank": "S-Bank",
                "name": "S-Bank account",
                "type": "current",
                "balance_eur": last.get("balance_after_eur"),
                "balance_date": last.get("tx_date"),
                "simulated": False,
            }
        )
    return out


@api_view(["GET"])
def accounts(request, customer_id):
    """S-Bank and linked accounts with balances, source bank and expiry."""
    if not services.customer_exists(customer_id):
        return Response({"detail": f"Unknown customer {customer_id}"}, status=404)
    linked = LinkedAccount.objects.filter(
        consent__customer_id=customer_id, consent__status="active"
    ).select_related("consent")
    rows = _sbank_accounts(customer_id) + [
        {
            "bank": a.consent.bank_name,
            "consent_id": a.consent_id,
            "name": a.name,
            "type": a.type,
            "iban_masked": a.iban_masked,
            "balance_eur": a.balance_eur,
            "balance_date": a.balance_date,
            "consent_expires_at": a.consent.expires_at.isoformat(),
            "simulated": True,
        }
        for a in linked
    ]
    return Response({"customer_id": customer_id, "accounts": rows})


# --- mock ASPSP (internal; Berlin Group NextGenPSD2 AIS shape) ---------------


def _active_consent(request, bank_code):
    consent_id = request.headers.get("Consent-ID", "")
    if not consent_id.isdigit():
        return None
    return BankConsent.objects.filter(
        pk=int(consent_id), bank_code=bank_code, status="active"
    ).first()


def _forbidden():
    return Response({"detail": "No active consent."}, status=403)


@api_view(["GET"])
def aspsp_accounts(request, bank_code):
    consent = _active_consent(request, bank_code)
    if consent is None:
        return _forbidden()
    return Response(
        {"accounts": [aspsp.account_view(a) for a in aspsp.berlin_accounts(consent)]}
    )


def _account(request, bank_code, resource_id):
    consent = _active_consent(request, bank_code)
    if consent is None:
        return None
    return next(
        (a for a in aspsp.berlin_accounts(consent) if a["resourceId"] == resource_id),
        None,
    )


@api_view(["GET"])
def aspsp_balances(request, bank_code, resource_id):
    account = _account(request, bank_code, resource_id)
    return Response(aspsp.balances_view(account)) if account else _forbidden()


@api_view(["GET"])
def aspsp_transactions(request, bank_code, resource_id):
    account = _account(request, bank_code, resource_id)
    return Response(aspsp.transactions_view(account)) if account else _forbidden()
