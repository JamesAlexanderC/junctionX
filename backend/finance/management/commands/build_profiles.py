"""Precompute ``CustomerProfile`` rows for every customer.

Transactions are streamed from Postgres in customer-id order with a
server-side cursor, so only one customer's rows are in memory at a time.
"""

import time
from itertools import groupby

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from finance.analytics import PERSONAS
from finance.models import Customer, CustomerProfile, MortgageApplication
from finance.services import TX_FIELDS, profile_for, row_to_tx

BATCH = 500


class Command(BaseCommand):
    help = "Compute persona and summary numbers for every customer."

    def handle(self, *args, **options):
        started = time.monotonic()
        apps = {
            a["customer_id"]: a
            for a in MortgageApplication.objects.values("customer_id", "final_decision")
        }
        total = Customer.objects.count()
        profiles = []
        seen = set()
        cols = ", ".join(TX_FIELDS)
        with transaction.atomic(), connection.cursor() as wrapper:
            cur = wrapper.connection.cursor(name="profile_stream")
            cur.itersize = 20000
            cur.execute(
                f"SELECT customer_id, {cols} FROM finance_transaction "
                "ORDER BY customer_id, tx_date, tx_timestamp"
            )
            for customer_id, rows in groupby(cur, key=lambda r: r[0]):
                txns = [row_to_tx(r[1:]) for r in rows]
                profiles.append(profile_for(customer_id, txns, apps.get(customer_id)))
                seen.add(customer_id)
                if len(profiles) % BATCH == 0:
                    self.stdout.write(f"  {len(profiles):,}/{total:,} customers")
            cur.close()
        # Customers without any transactions still get an (empty) profile.
        for customer_id in Customer.objects.exclude(pk__in=seen).values_list(
            "pk", flat=True
        ):
            profiles.append(profile_for(customer_id, [], apps.get(customer_id)))

        with transaction.atomic():
            CustomerProfile.objects.all().delete()
            CustomerProfile.objects.bulk_create(profiles, batch_size=1000)

        counts = {}
        for p in profiles:
            counts[p.persona_key] = counts.get(p.persona_key, 0) + 1
        self.stdout.write(f"Built {len(profiles):,} profiles:")
        for key in PERSONAS:
            n = counts.get(key, 0)
            share = n / max(len(profiles), 1)
            self.stdout.write(f"  {PERSONAS[key]['label']:<22} {n:>5} ({share:.0%})")
        self.stdout.write(f"Done in {time.monotonic() - started:.0f}s")
