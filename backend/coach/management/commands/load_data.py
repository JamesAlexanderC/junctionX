"""P1.2: load the S-Bank CSVs for the demo customers into the database."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from coach.management import csvdata
from coach.models import (
    Account,
    Customer,
    MortgageEvent,
    MortgageOutcome,
    Transaction,
)


class Command(BaseCommand):
    help = "Load CSVs from data/, keeping only settings.DEMO_CUSTOMERS."

    def add_arguments(self, parser):
        parser.add_argument("--customers", help="Comma-separated ids (overrides)")
        parser.add_argument("--data-dir", help="Folder with the CSVs")
        parser.add_argument("--replace", action="store_true", help="Delete first")

    def handle(self, *args, **opts):
        from pathlib import Path

        data_dir = Path(opts["data_dir"]) if opts["data_dir"] else None
        ids = (
            [c for c in opts["customers"].split(",") if c]
            if opts["customers"]
            else list(settings.DEMO_CUSTOMERS)
        )
        if not ids:
            raise CommandError(
                "No customers: set DEMO_CUSTOMERS in .env or pass --customers. "
                "Run `manage.py rank_demo_customers` for suggestions."
            )
        with transaction.atomic():
            if opts["replace"]:
                Customer.objects.filter(customer_id__in=ids).delete()
            self._customers(ids, data_dir)
            n = self._transactions(ids, data_dir)
            self._mortgages(ids, data_dir)
        self.stdout.write(self.style.SUCCESS(f"Loaded {n} transactions for {ids}"))

    def _customers(self, ids, data_dir):
        df = csvdata.read_small(csvdata.CUSTOMERS_FILE, data_dir)
        df["customer_id"] = df["customer_id"].astype(str)
        df = df[df["customer_id"].isin(ids)]
        for row in df.itertuples():
            Customer.objects.update_or_create(
                customer_id=row.customer_id,
                defaults={
                    "postal_code": str(getattr(row, "customer_postal_code", "")),
                    "age": (
                        int(row.customer_age)
                        if row.customer_age == row.customer_age
                        else None
                    ),
                },
            )
        for cid in set(ids) - set(df["customer_id"]):
            Customer.objects.get_or_create(customer_id=cid)

    def _transactions(self, ids, data_dir):
        total = 0
        known_accounts = set(
            Account.objects.filter(customer_id__in=ids).values_list(
                "bank_account_id", flat=True
            )
        )
        for chunk in csvdata.iter_transactions(data_dir, ids):
            for cid, acc in (
                chunk[["customer_id", "bank_account_id"]].drop_duplicates().values
            ):
                if acc not in known_accounts:
                    Account.objects.get_or_create(
                        bank_account_id=acc, defaults={"customer_id": cid}
                    )
                    known_accounts.add(acc)
            objs = [
                Transaction(
                    tx_id=r.tx_id,
                    customer_id=r.customer_id,
                    account_id=r.bank_account_id,
                    tx_date=r.tx_date.date(),
                    tx_timestamp=r.tx_timestamp.to_pydatetime(),
                    category=r.category,
                    tx_amount_eur=float(r.tx_amount_eur),
                    balance_after_eur=(
                        None
                        if r.balance_after_eur != r.balance_after_eur
                        else float(r.balance_after_eur)
                    ),
                    transaction_type=r.transaction_type,
                    merchant_id=r.merchant_id,
                    mcc_code=r.mcc_code,
                )
                for r in chunk.itertuples()
            ]
            Transaction.objects.bulk_create(
                objs, ignore_conflicts=True, batch_size=5000
            )
            total += len(objs)
            self.stdout.write(f"  {total} transactions...")
        return total

    def _mortgages(self, ids, data_dir):
        try:
            link = csvdata.read_small(csvdata.MTG_LINK_FILE, data_dir)
            history = csvdata.read_small(csvdata.MTG_HISTORY_FILE, data_dir)
        except CommandError as exc:
            self.stderr.write(f"Skipping mortgage files: {exc}")
            return
        outcome_col = next(
            (
                c
                for c in link.columns
                if any(k in c.lower() for k in ("outcome", "status", "final", "approv"))
            ),
            None,
        )
        for row in link.to_dict("records"):
            mid = str(row.get("mortgage_customer_id"))
            cid = str(row.get("customer_id"))
            Customer.objects.get_or_create(customer_id=cid)
            MortgageOutcome.objects.update_or_create(
                mortgage_customer_id=mid,
                defaults={
                    "customer_id": cid,
                    "outcome": str(row.get(outcome_col, "")) if outcome_col else "",
                    "raw": {k: _json(v) for k, v in row.items()},
                },
            )
        MortgageEvent.objects.all().delete()
        MortgageEvent.objects.bulk_create(
            [
                MortgageEvent(
                    mortgage_customer_id=str(r.get("mortgage_customer_id")),
                    raw={k: _json(v) for k, v in r.items()},
                )
                for r in history.to_dict("records")
            ],
            batch_size=5000,
        )


def _json(value):
    if value != value:  # NaN
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
