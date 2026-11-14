"""P1.6: prebuild cached profiles (they are otherwise built on first use)."""

import time

from django.core.management.base import BaseCommand, CommandError

from coach import services
from coach.models import Customer


class Command(BaseCommand):
    help = "Build and cache profiles for --customers ids or --all customers."

    def add_arguments(self, parser):
        parser.add_argument("--customers", help="Comma-separated ids")
        parser.add_argument("--all", action="store_true", help="Every customer")

    def handle(self, *args, **opts):
        if opts["all"]:
            ids = list(Customer.objects.values_list("customer_id", flat=True))
        elif opts["customers"]:
            ids = [c for c in opts["customers"].split(",") if c]
        else:
            raise CommandError("Pass --customers ID,ID or --all.")
        started = time.monotonic()
        for n, cid in enumerate(ids, 1):
            services.invalidate(cid)
            if services.get_profile(cid) is None:
                self.stderr.write(f"{cid}: unknown customer, skipped")
                continue
            if n % 100 == 0 or len(ids) <= 20:
                self.stdout.write(f"{n}/{len(ids)} {cid}")
        took = time.monotonic() - started
        self.stdout.write(
            self.style.SUCCESS(f"Built {len(ids)} profiles in {took:.0f}s")
        )
