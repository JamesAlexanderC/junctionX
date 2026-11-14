"""P1.6: build one profile JSON per loaded customer."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from coach import services
from coach.models import Customer


class Command(BaseCommand):
    help = "Run every inference and save Profile rows + backend/profiles/<id>.json."

    def add_arguments(self, parser):
        parser.add_argument("--customer", action="append", help="Only these ids")
        parser.add_argument(
            "--today", help="YYYY-MM-DD (default: reference date, max tx_date)"
        )

    def handle(self, *args, **opts):
        ids = opts["customer"] or list(
            Customer.objects.filter(transactions__isnull=False)
            .distinct()
            .values_list("customer_id", flat=True)
        )
        if not ids:
            raise CommandError("No customers with transactions. Run load_data first.")
        # P1.1: one reference date (max tx_date) for every customer.
        today = date.fromisoformat(opts["today"]) if opts["today"] else services.today()
        for cid in ids:
            df = services.transactions_df(cid)
            if df is None:
                self.stderr.write(f"{cid}: no transactions, skipped")
                continue
            data = services.build_customer_profile(cid, df, today)
            services.save_profile(cid, data, write_file=True)
            self.stdout.write(self.style.SUCCESS(f"{cid}: profile saved ({today})"))
