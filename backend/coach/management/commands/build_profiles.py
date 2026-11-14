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
            "--today", help="YYYY-MM-DD (default: last transaction date)"
        )

    def handle(self, *args, **opts):
        try:
            from inferences.profile import build_profile
        except ImportError as exc:
            raise CommandError(f"inferences.profile is not available: {exc}") from exc

        ids = opts["customer"] or list(
            Customer.objects.filter(transactions__isnull=False)
            .distinct()
            .values_list("customer_id", flat=True)
        )
        if not ids:
            raise CommandError("No customers with transactions. Run load_data first.")
        for cid in ids:
            df = services.transactions_df(cid)
            if df is None:
                self.stderr.write(f"{cid}: no transactions, skipped")
                continue
            today = (
                date.fromisoformat(opts["today"])
                if opts["today"]
                else df["tx_date"].max().date()
            )
            cust = Customer.objects.get(customer_id=cid)
            data = build_profile(
                df,
                {
                    "customer_id": cid,
                    "age": cust.age,
                    "postal_code": cust.postal_code,
                },
                today,
                goals=services.goal_dicts(cid),
                loans=services.latest_loan(cid),
            )
            services.save_profile(cid, data, write_file=True)
            self.stdout.write(self.style.SUCCESS(f"{cid}: profile saved ({today})"))
