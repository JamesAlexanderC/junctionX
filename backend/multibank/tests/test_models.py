"""MB-1: consent, linked account and external transaction tables."""

from datetime import datetime, timedelta, timezone

import pytest

from multibank.models import BankConsent, ExternalTransaction, LinkedAccount

pytestmark = pytest.mark.django_db

GRANTED = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


def _consent(**extra):
    return BankConsent.objects.create(
        customer_id="CUST03369", bank_code="NDEAFIHH", bank_name="Nordea", **extra
    )


def test_consent_expires_after_180_days_and_is_synthetic():
    consent = _consent(granted_at=GRANTED)
    assert consent.expires_at == GRANTED + timedelta(days=180)
    assert consent.is_synthetic is True
    assert consent.status == "pending"
    assert consent.scopes == ["accounts", "balances", "transactions"]


def test_revoking_deletes_accounts_and_transactions():
    consent = _consent(granted_at=GRANTED, status="active")
    account = LinkedAccount.objects.create(
        consent=consent,
        iban_masked="FI•• •••• •••• 1234",
        name="Car loan account",
        type="current",
        balance_eur=820.0,
        balance_date="2026-09-30",
    )
    ExternalTransaction.objects.create(
        linked_account=account,
        booking_date="2026-09-03",
        amount_eur=-310.0,
        creditor_name="Auto Finance Oy",
        category="loan_payment",
    )
    assert account.is_synthetic and ExternalTransaction.objects.get().is_synthetic
    consent.delete_linked_data()
    assert LinkedAccount.objects.count() == 0
    assert ExternalTransaction.objects.count() == 0
