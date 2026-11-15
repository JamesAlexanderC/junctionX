"""Before the demo (MULTIBANK_PLAN.md §10): disconnect the scenario customers
so the beat starts from the S-Bank-only view again.

Revoking deletes the linked rows read through each consent and rebuilds
the profile. S-Bank data is never touched.
"""

from django.core.management.base import BaseCommand

from coach import services
from multibank import aspsp
from multibank import scenarios as sc
from multibank.models import BankConsent

SCENARIO_CUSTOMERS = (
    sc.HERO,
    sc.SALARY_ELSEWHERE,
    sc.DUPLICATE_SUBS,
    sc.CREDIT_CARD,
    sc.SAVINGS_ELSEWHERE,
)


class Command(BaseCommand):
    help = "Disconnect the multibank demo customers (start from S-Bank only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Revoke every active consent, not only the scenario customers.",
        )

    def handle(self, *args, all=False, **options):
        consents = BankConsent.objects.filter(status__in=["active", "pending"])
        if not all:
            consents = consents.filter(customer_id__in=SCENARIO_CUSTOMERS)
        customers, revoked = set(), 0
        for consent in list(consents):
            aspsp.revoke(consent)
            customers.add(consent.customer_id)
            revoked += 1
        for customer_id in sorted(customers):
            services.refresh_profile(customer_id)
            coverage = services.get_profile(customer_id)["multibank"]["coverage"]
            self.stdout.write(f"{customer_id}: disconnected ({coverage})")
        self.stdout.write(f"Revoked {revoked} consent(s).")
