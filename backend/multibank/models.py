"""Simulated PSD2 account access (MULTIBANK_PLAN.md MB-1, context.md #41-#43).

Nothing here comes from a real bank: rows are created from synthetic data
(generate_external_banks --seed 42) when a consent is authorised, and every
row says is_synthetic=True. No credentials are ever stored.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

CONSENT_DAYS = 180  # PSD2 access must be renewed every 180 days
DEFAULT_SCOPES = ("accounts", "balances", "transactions")


def default_scopes():
    return list(DEFAULT_SCOPES)


class BankConsent(models.Model):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("active", "active"),
        ("revoked", "revoked"),
        ("expired", "expired"),
    ]

    customer_id = models.CharField(max_length=64, db_index=True)
    bank_code = models.CharField(max_length=16)
    bank_name = models.CharField(max_length=64)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    scopes = models.JSONField(default=default_scopes)
    granted_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True)
    is_synthetic = models.BooleanField(default=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.granted_at + timedelta(days=CONSENT_DAYS)
        super().save(*args, **kwargs)

    def delete_linked_data(self):
        """Revoking removes everything read through this consent."""
        LinkedAccount.objects.filter(consent=self).delete()

    def __str__(self):
        return f"{self.customer_id} -> {self.bank_name} ({self.status})"


class LinkedAccount(models.Model):
    TYPE_CHOICES = [
        ("current", "current"),
        ("savings", "savings"),
        ("credit", "credit"),
        ("loan", "loan"),
    ]

    consent = models.ForeignKey(
        BankConsent, on_delete=models.CASCADE, related_name="accounts"
    )
    iban_masked = models.CharField(max_length=40)
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    currency = models.CharField(max_length=3, default="EUR")
    balance_eur = models.FloatField()
    balance_date = models.DateField()
    is_synthetic = models.BooleanField(default=True, editable=False)

    def __str__(self):
        return f"{self.consent.bank_name} {self.iban_masked} ({self.type})"


class ExternalTransaction(models.Model):
    linked_account = models.ForeignKey(
        LinkedAccount, on_delete=models.CASCADE, related_name="transactions"
    )
    booking_date = models.DateField()
    amount_eur = models.FloatField()  # signed: inflow > 0
    creditor_name = models.CharField(max_length=120, blank=True, default="")
    debtor_name = models.CharField(max_length=120, blank=True, default="")
    counterparty_iban_masked = models.CharField(max_length=40, blank=True, default="")
    remittance_info = models.CharField(max_length=200, blank=True, default="")
    mcc = models.CharField(max_length=8, blank=True, null=True)
    category = models.CharField(max_length=128, blank=True, default="")
    own_transfer = models.BooleanField(default=False)  # set by #41 matching
    is_synthetic = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ["booking_date", "id"]
