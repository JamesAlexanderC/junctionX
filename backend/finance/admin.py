from django.contrib import admin

from .models import Customer, CustomerProfile, MortgageApplication


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("customer_id", "customer_postal_code", "customer_age")
    search_fields = ("customer_id", "customer_postal_code")


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "persona_label",
        "monthly_income",
        "monthly_spend",
        "savings_rate",
        "balance",
    )
    list_filter = ("persona_key", "has_mortgage_application")


@admin.register(MortgageApplication)
class MortgageApplicationAdmin(admin.ModelAdmin):
    list_display = ("mortgage_customer_id", "customer", "final_decision")
    list_filter = ("final_decision",)
