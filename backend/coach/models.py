"""Database models for Saldo (context.md "The data", #54, #63-#64, #72, P2.8)."""

import uuid

from django.conf import settings
from django.db import models


class Customer(models.Model):
    customer_id = models.CharField(max_length=64, primary_key=True)
    postal_code = models.CharField(max_length=16, blank=True, default="")
    age = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.customer_id


class Account(models.Model):
    bank_account_id = models.CharField(max_length=64, primary_key=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="accounts"
    )
    # Multi-bank bonus (#41-#43): a mocked second bank is relabelled here.
    bank = models.CharField(max_length=32, default="S-Bank")
    synthetic = models.BooleanField(default=False)


class Transaction(models.Model):
    tx_id = models.CharField(max_length=64, primary_key=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="transactions"
    )
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transactions"
    )
    tx_date = models.DateField()
    tx_timestamp = models.DateTimeField()
    category = models.CharField(max_length=128, blank=True, default="")
    tx_amount_eur = models.FloatField()
    balance_after_eur = models.FloatField(null=True, blank=True)
    transaction_type = models.CharField(max_length=64, blank=True, default="")
    merchant_id = models.CharField(max_length=64, blank=True, default="")
    mcc_code = models.CharField(max_length=8, blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["customer", "tx_date"])]


class MortgageOutcome(models.Model):
    """One row of mtg_tx_customer_link_and_final_mtg_infio.csv (#34)."""

    mortgage_customer_id = models.CharField(max_length=64, primary_key=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mortgage_outcomes",
    )
    final_decision = models.CharField(max_length=32, blank=True, default="")
    rejection_reason = models.CharField(max_length=64, blank=True, default="")
    final_property_price_eur = models.FloatField(null=True, blank=True)
    final_requested_loan_eur = models.FloatField(null=True, blank=True)
    final_equity_amount_eur = models.FloatField(null=True, blank=True)
    final_collateral_value_eur = models.FloatField(null=True, blank=True)
    required_monthly_income_eur = models.FloatField(null=True, blank=True)
    final_loan_to_value = models.FloatField(null=True, blank=True)

    @property
    def approved(self):
        return self.final_decision.lower() == "approved"


class MortgageEvent(models.Model):
    """One row of mtg_negotiation_history.csv."""

    mortgage_customer_id = models.CharField(max_length=64, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    event_type = models.CharField(max_length=64, blank=True, default="")
    property_id = models.CharField(max_length=64, blank=True, default="")
    property_type = models.CharField(max_length=64, blank=True, default="")
    property_price_estimate = models.FloatField(null=True, blank=True)
    loan_amount = models.FloatField(null=True, blank=True)
    equity_amount = models.FloatField(null=True, blank=True)
    collateral_type = models.CharField(max_length=64, blank=True, default="")
    collateral_value = models.FloatField(null=True, blank=True)
    collateral_status = models.CharField(max_length=64, blank=True, default="")
    decision = models.CharField(max_length=32, blank=True, default="")
    rejection_reason = models.CharField(max_length=64, blank=True, default="")
    expense_type = models.CharField(max_length=64, blank=True, default="")
    expense_amount = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True, default="")


class ComputedArtifact(models.Model):
    """Dataset-wide results computed once: the #36/#37 peer table (JSON) and
    the fitted #34 mortgage readiness model (pickled)."""

    key = models.CharField(max_length=64, primary_key=True)
    data = models.JSONField(default=dict, blank=True)
    blob = models.BinaryField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class Goal(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("abandoned", "Abandoned"),
    ]
    PRIORITY_CHOICES = [("high", "High"), ("medium", "Medium"), ("low", "Low")]

    customer_id = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=120)
    emoji = models.CharField(max_length=8, blank=True, default="")
    type = models.CharField(max_length=32, default="custom")
    target = models.FloatField()
    saved = models.FloatField(default=0)
    start_date = models.DateField()
    target_date = models.DateField()
    priority = models.CharField(
        max_length=8, choices=PRIORITY_CHOICES, default="medium"
    )
    paused = models.BooleanField(default=False)
    paused_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    milestones_hit = models.JSONField(default=list)
    # Alert-coach plans saved by accept_plan are goals with a checklist.
    checklist = models.JSONField(default=list, blank=True)
    created_by_user = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "type": self.type,
            "target": self.target,
            "saved": self.saved,
            "start_date": self.start_date.isoformat(),
            "target_date": self.target_date.isoformat(),
            "priority": self.priority,
            "paused": self.paused,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "status": self.status,
            "milestones_hit": self.milestones_hit,
            "checklist": self.checklist,
            "created_by_user": self.created_by_user,
        }


class GoalRating(models.Model):
    """Thumbs up/down per goal type (#54)."""

    customer_id = models.CharField(max_length=64, db_index=True)
    goal_type = models.CharField(max_length=32)
    up = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)


class LoanDetails(models.Model):
    """User-entered loan details used by #77 and #82 (P2.8)."""

    customer_id = models.CharField(max_length=64, db_index=True)
    balance = models.FloatField()
    interest_rate = models.FloatField(help_text="Percent per year, 0-20")
    years_left = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def as_dict(self):
        return {
            "balance": self.balance,
            "interest_rate": self.interest_rate,
            "years_left": self.years_left,
        }


class DismissedSuggestion(models.Model):
    """A detected-goal suggestion (#56 to #62) the user hid; never shown again."""

    customer_id = models.CharField(max_length=64, db_index=True)
    suggestion_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("customer_id", "suggestion_id")]


class Profile(models.Model):
    """Cached build_profile output; rebuilt when the inference code changes."""

    customer_id = models.CharField(max_length=64, primary_key=True)
    data = models.JSONField()
    built_with = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class AlertSnooze(models.Model):
    customer_id = models.CharField(max_length=64, db_index=True)
    alert_id = models.CharField(max_length=128)
    until = models.DateField()


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    customer_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ChatTurn(models.Model):
    """One user message and the reply, kept for history and confirmations.

    ``pending`` holds a proposal (create_goal args or accept_plan actions) that
    the next user turn must confirm before it is executed.
    """

    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.CASCADE
    )
    customer_id = models.CharField(max_length=64, db_index=True)
    message = models.TextField()
    reply = models.JSONField(default=dict)
    pending = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class DemoCache(models.Model):
    """Cached real Gemini send_reply per customer and normalised question (P2.6).

    Only filled from live Gemini answers; never pre-seeded.
    """

    customer_id = models.CharField(max_length=64)
    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.CASCADE
    )
    question = models.CharField(max_length=500)
    reply = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("conversation", "customer_id", "question")]
