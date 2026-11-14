"""Models for the S-Pankki hackathon dataset plus precomputed profiles.

The raw tables mirror the CSV files one-to-one (see ``load_dataset``).
``CustomerProfile`` is derived data written by ``build_profiles``.
"""

from django.db import models


class Customer(models.Model):
    customer_id = models.CharField(max_length=16, primary_key=True)
    customer_postal_code = models.CharField(max_length=8, db_index=True)
    customer_age = models.PositiveSmallIntegerField(null=True)

    class Meta:
        ordering = ["customer_id"]

    def __str__(self):
        return self.customer_id


class Transaction(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        db_column="customer_id",
        related_name="transactions",
    )
    bank_account_id = models.CharField(max_length=16)
    tx_date = models.DateField()
    tx_timestamp = models.DateTimeField()
    category = models.CharField(max_length=32)
    # Negative amounts are outflows.
    tx_amount_eur = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after_eur = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=32)
    merchant_id = models.CharField(max_length=16, null=True, blank=True)
    mcc_code = models.CharField(max_length=4, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "tx_date"], name="tx_customer_date"),
        ]

    def __str__(self):
        return f"{self.customer_id} {self.tx_date} {self.tx_amount_eur}"


class MortgageApplication(models.Model):
    mortgage_customer_id = models.CharField(max_length=16, primary_key=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        db_column="customer_id",
        related_name="mortgage_applications",
    )
    final_decision = models.CharField(max_length=16)
    rejection_reason = models.CharField(max_length=64, blank=True, default="")
    final_property_price_eur = models.FloatField(null=True)
    final_requested_loan_eur = models.FloatField(null=True)
    final_equity_amount_eur = models.FloatField(null=True)
    final_collateral_value_eur = models.FloatField(null=True)
    required_monthly_income_eur = models.FloatField(null=True)
    # The CSV column is misspelled ``lfinal_loan_to_value``.
    final_loan_to_value = models.FloatField(null=True)

    def __str__(self):
        return f"{self.mortgage_customer_id} ({self.final_decision})"


class MortgageEvent(models.Model):
    application = models.ForeignKey(
        MortgageApplication,
        on_delete=models.CASCADE,
        db_column="mortgage_customer_id",
        related_name="events",
    )
    timestamp = models.DateTimeField()
    event_type = models.CharField(max_length=40)
    property_id = models.CharField(max_length=16, blank=True, default="")
    property_type = models.CharField(max_length=32, blank=True, default="")
    property_price_estimate = models.FloatField(null=True)
    loan_amount = models.FloatField(null=True)
    equity_amount = models.FloatField(null=True)
    collateral_type = models.CharField(max_length=32, blank=True, default="")
    collateral_value = models.FloatField(null=True)
    collateral_status = models.CharField(max_length=32, blank=True, default="")
    decision = models.CharField(max_length=16, blank=True, default="")
    rejection_reason = models.CharField(max_length=64, blank=True, default="")
    expense_type = models.CharField(max_length=40, blank=True, default="")
    expense_amount = models.FloatField(null=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["application_id", "timestamp"]

    def __str__(self):
        return f"{self.application_id} {self.timestamp:%Y-%m-%d} {self.event_type}"


class CustomerProfile(models.Model):
    """Per-customer summary precomputed by ``manage.py build_profiles``."""

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="customer_id",
        related_name="profile",
    )
    persona_key = models.CharField(max_length=32, db_index=True)
    persona_label = models.CharField(max_length=64)
    monthly_income = models.FloatField()
    monthly_spend = models.FloatField()
    savings_rate = models.FloatField()
    balance = models.FloatField()
    has_mortgage_application = models.BooleanField(default=False)
    mortgage_decision = models.CharField(max_length=16, null=True, blank=True)
    # Extra signals used for persona assignment and featured selection.
    leakage_share = models.FloatField(default=0)
    invest_monthly = models.FloatField(default=0)
    balance_volatility = models.FloatField(default=0)
    min_balance = models.FloatField(default=0)
    tx_count = models.PositiveIntegerField(default=0)
    # How strongly this customer fits their persona (higher = clearer
    # example); used to pick featured customers.
    persona_score = models.FloatField(default=0)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["customer_id"]

    def __str__(self):
        return f"{self.customer_id}: {self.persona_label}"
