"""Build the landing page customer index and demo picks.

Works out every customer's spender type (#16) with only the steps it needs
(coach/customer_index.py, ~0.15 s each, in parallel), adds their income
level, and picks one demo customer per spender type (inferences/demo.py).
Run after load_data; ~2 min for 5,100 customers on 8 cores.
"""

import time

from django.core.management.base import BaseCommand, CommandError

from coach import services
from coach.models import Customer


class Command(BaseCommand):
    help = "Build the landing page customer index and demo picks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--workers", type=int, default=None, help="processes (default: CPUs)"
        )

    def handle(self, *args, **opts):
        if not Customer.objects.exists():
            raise CommandError("No customers loaded. Run load_data first.")
        started = time.monotonic()

        def progress(n, total):
            took = time.monotonic() - started
            self.stdout.write(f"{n}/{total} profiles ({took:.0f}s)")

        index, demos = services.build_customer_index(
            workers=opts["workers"], progress=progress
        )
        errors = sum(1 for c in index if c["spender_type"] is None)
        for d in demos:
            self.stdout.write(
                f"Demo {d['demo']}: {d['customer_id']} {d['income_label']}, "
                f"{d['spender_type']} (clarity {d['clarity']})"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Indexed {len(index)} customers, {len(demos)} demos, "
                f"{errors} without a spender type "
                f"({time.monotonic() - started:.0f}s)"
            )
        )
