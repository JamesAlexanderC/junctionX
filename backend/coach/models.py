"""Database models for Saldo (context.md "The data", #54, #63-#64, #72, P2.8)."""

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
    # Demo events injected by `inject_demo_events`, never in the S-Bank CSVs.
    is_synthetic = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["customer", "tx_date"])]


class MortgageOutcome(models.Model):
    """One row of mtg_tx_customer_link_and_final_mtg_infio.csv."""

    mortgage_customer_id = models.CharField(max_length=64, primary_key=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mortgage_outcomes",
    )
    outcome = models.CharField(max_length=64, blank=True, default="")
    raw = models.JSONField(default=dict)


class MortgageEvent(models.Model):
    """One row of mtg_negotiation_history.csv (columns kept raw)."""

    mortgage_customer_id = models.CharField(max_length=64, db_index=True)
    raw = models.JSONField(default=dict)


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


class Profile(models.Model):
    customer_id = models.CharField(max_length=64, primary_key=True)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)


class AlertSnooze(models.Model):
    customer_id = models.CharField(max_length=64, db_index=True)
    alert_id = models.CharField(max_length=128)
    until = models.DateField()


class ChatTurn(models.Model):
    """One user message and the reply, kept for history and confirmations.

    ``pending`` holds a proposal (create_goal args or accept_plan actions) that
    the next user turn must confirm before it is executed.
    """

    customer_id = models.CharField(max_length=64, db_index=True)
    message = models.TextField()
    reply = models.JSONField(default=dict)
    pending = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class DemoCache(models.Model):
    """Cached send_reply per customer and normalised question (P2.6)."""

    customer_id = models.CharField(max_length=64)
    question = models.CharField(max_length=500)
    reply = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("customer_id", "question")]
