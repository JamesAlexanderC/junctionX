from django.contrib import admin

from .models import BankConsent, ExternalTransaction, LinkedAccount


@admin.register(BankConsent)
class BankConsentAdmin(admin.ModelAdmin):
    list_display = ("customer_id", "bank_name", "status", "granted_at", "expires_at")
    list_filter = ("status", "bank_name")
    search_fields = ("customer_id",)


@admin.register(LinkedAccount)
class LinkedAccountAdmin(admin.ModelAdmin):
    list_display = ("consent", "iban_masked", "type", "balance_eur", "balance_date")


@admin.register(ExternalTransaction)
class ExternalTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "linked_account",
        "booking_date",
        "amount_eur",
        "creditor_name",
        "category",
        "own_transfer",
    )
    list_filter = ("own_transfer", "category")
