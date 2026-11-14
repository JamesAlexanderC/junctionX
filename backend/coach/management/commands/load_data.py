"""P1.2: load the S-Bank CSVs (all customers, or a subset) into the database.

On Postgres the transactions go in with COPY (about 3.6M rows in minutes); on
SQLite (tests) with bulk_create. Afterwards the dataset-wide artifacts (peer
table #36/#37, mortgage readiness model #34) are rebuilt unless
``--skip-artifacts`` is given.
"""

import io
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from coach.management import csvdata
from coach.models import (
    Account,
    ComputedArtifact,
    Customer,
    MortgageEvent,
    MortgageOutcome,
    Profile,
    Transaction,
)

TX_TABLE_COLUMNS = [
    "tx_id",
    "customer_id",
    "account_id",
    "tx_date",
    "tx_timestamp",
    "category",
    "tx_amount_eur",
    "balance_after_eur",
    "transaction_type",
    "merchant_id",
    "mcc_code",
]


class Command(BaseCommand):
    help = "Load the S-Bank CSVs from DATA_DIR into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--customers", help="Comma-separated ids (default: every customer)"
        )
        parser.add_argument("--data-dir", help="Folder with the CSVs")
        parser.add_argument(
            "--replace", action="store_true", help="Delete loaded data first"
        )
        parser.add_argument(
            "--skip-artifacts",
            action="store_true",
            help="Don't rebuild the peer table and mortgage model",
        )

    def handle(self, *args, **opts):
        from pathlib import Path

        started = time.monotonic()
        data_dir = Path(opts["data_dir"]) if opts["data_dir"] else None
        ids = (
            {c for c in opts["customers"].split(",") if c}
            if opts["customers"]
            else None
        )
        if not opts["replace"] and Transaction.objects.exists():
            raise CommandError(
                "Transactions are already loaded. Pass --replace to reload."
            )
        with transaction.atomic():
            if opts["replace"]:
                self._purge()
            n_cust = self._customers(ids, data_dir)
            n_tx = self._transactions(ids, data_dir)
            n_mtg = self._mortgages(ids, data_dir)
        Profile.objects.all().delete()  # cached profiles are now stale
        took = time.monotonic() - started
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {n_cust} customers, {n_tx} transactions, {n_mtg} mortgage "
                f"applications in {took:.0f}s"
            )
        )
        if not opts["skip_artifacts"]:
            call_command("build_artifacts", stdout=self.stdout, stderr=self.stderr)

    def _purge(self):
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                # Fire deferred FK checks first; TRUNCATE refuses to run while
                # rows inserted earlier in this transaction have pending ones.
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
                cur.execute(
                    "TRUNCATE coach_transaction, coach_account, "
                    "coach_mortgageevent, coach_mortgageoutcome, "
                    "coach_computedartifact, coach_profile, coach_customer CASCADE"
                )
        else:
            for model in (
                Transaction,
                Account,
                MortgageEvent,
                MortgageOutcome,
                ComputedArtifact,
                Profile,
                Customer,
            ):
                model.objects.all().delete()

    def _customers(self, ids, data_dir):
        df = csvdata.read_small(csvdata.CUSTOMERS_FILE, data_dir)
        df["customer_id"] = df["customer_id"].astype(str)
        if ids is not None:
            df = df[df["customer_id"].isin(ids)]
        Customer.objects.bulk_create(
            [
                Customer(
                    customer_id=r.customer_id,
                    postal_code=str(r.customer_postal_code).zfill(5),
                    age=(
                        int(r.customer_age)
                        if r.customer_age == r.customer_age
                        else None
                    ),
                )
                for r in df.itertuples()
            ],
            batch_size=5000,
            ignore_conflicts=True,
        )
        return len(df)

    def _transactions(self, ids, data_dir):
        known_customers = set(Customer.objects.values_list("customer_id", flat=True))
        known_accounts = set(Account.objects.values_list("bank_account_id", flat=True))
        total = 0
        for chunk in csvdata.iter_transactions(data_dir, ids):
            chunk = chunk[chunk["customer_id"].isin(known_customers)]
            accounts = chunk[["bank_account_id", "customer_id"]].drop_duplicates(
                "bank_account_id"
            )
            new = accounts[~accounts["bank_account_id"].isin(known_accounts)]
            Account.objects.bulk_create(
                [
                    Account(bank_account_id=a, customer_id=c)
                    for a, c in new.itertuples(index=False)
                ],
                batch_size=5000,
            )
            known_accounts.update(new["bank_account_id"])
            if connection.vendor == "postgresql":
                self._copy(chunk)
            else:
                self._bulk(chunk)
            total += len(chunk)
            self.stdout.write(f"  {total} transactions...")
        return total

    def _frame(self, chunk):
        out = chunk.rename(columns={"bank_account_id": "account_id"})[
            TX_TABLE_COLUMNS
        ].copy()
        out["tx_date"] = out["tx_date"].dt.strftime("%Y-%m-%d")
        # Naive local times stored as UTC; services.transactions_df strips tz.
        out["tx_timestamp"] = out["tx_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S+00")
        return out

    def _copy(self, chunk):
        buf = io.StringIO()
        self._frame(chunk).to_csv(buf, index=False, header=False)
        cols = ", ".join(TX_TABLE_COLUMNS)
        with connection.cursor() as cur:
            raw = cur.cursor  # the psycopg cursor under Django's wrapper
            with raw.copy(
                f"COPY coach_transaction ({cols}) FROM STDIN WITH (FORMAT csv, "
                "FORCE_NOT_NULL (category, transaction_type, merchant_id, mcc_code))"
            ) as copy:
                copy.write(buf.getvalue())

    def _bulk(self, chunk):
        from datetime import timezone as tz

        objs = [
            Transaction(
                tx_id=r.tx_id,
                customer_id=r.customer_id,
                account_id=r.bank_account_id,
                tx_date=r.tx_date.date(),
                tx_timestamp=r.tx_timestamp.to_pydatetime().replace(tzinfo=tz.utc),
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
        Transaction.objects.bulk_create(objs, batch_size=5000)

    def _mortgages(self, ids, data_dir):
        try:
            link = csvdata.read_small(csvdata.MTG_LINK_FILE, data_dir)
            history = csvdata.read_small(csvdata.MTG_HISTORY_FILE, data_dir)
        except CommandError as exc:
            self.stderr.write(f"Skipping mortgage files: {exc}")
            return 0
        known = set(Customer.objects.values_list("customer_id", flat=True))
        link["customer_id"] = link["customer_id"].astype(str)
        if ids is not None:
            link = link[link["customer_id"].isin(ids)]
        # The CSV header spells this column "lfinal_loan_to_value".
        ltv = next((c for c in link.columns if c.endswith("loan_to_value")), None)
        MortgageOutcome.objects.bulk_create(
            [
                MortgageOutcome(
                    mortgage_customer_id=str(r["mortgage_customer_id"]),
                    customer_id=r["customer_id"] if r["customer_id"] in known else None,
                    final_decision=_text(r.get("final_decision")),
                    rejection_reason=_text(r.get("rejection_reason")),
                    final_property_price_eur=_num(r.get("final_property_price_eur")),
                    final_requested_loan_eur=_num(r.get("final_requested_loan_eur")),
                    final_equity_amount_eur=_num(r.get("final_equity_amount_eur")),
                    final_collateral_value_eur=_num(
                        r.get("final_collateral_value_eur")
                    ),
                    required_monthly_income_eur=_num(
                        r.get("required_monthly_income_eur")
                    ),
                    final_loan_to_value=_num(r.get(ltv)) if ltv else None,
                )
                for r in link.to_dict("records")
            ],
            ignore_conflicts=True,
        )
        keep = set(link["mortgage_customer_id"].astype(str))
        history["mortgage_customer_id"] = history["mortgage_customer_id"].astype(str)
        history = history[history["mortgage_customer_id"].isin(keep)]
        stamps = csvdata.parse_timestamps(history["timestamp"], column="timestamp")
        events = []
        for (_, r), ts in zip(history.iterrows(), stamps):
            events.append(
                MortgageEvent(
                    mortgage_customer_id=r["mortgage_customer_id"],
                    timestamp=_aware(ts),
                    event_type=_text(r.get("event_type")),
                    property_id=_text(r.get("property_id")),
                    property_type=_text(r.get("property_type")),
                    property_price_estimate=_num(r.get("property_price_estimate")),
                    loan_amount=_num(r.get("loan_amount")),
                    equity_amount=_num(r.get("equity_amount")),
                    collateral_type=_text(r.get("collateral_type")),
                    collateral_value=_num(r.get("collateral_value")),
                    collateral_status=_text(r.get("collateral_status")),
                    decision=_text(r.get("decision")),
                    rejection_reason=_text(r.get("rejection_reason")),
                    expense_type=_text(r.get("expense_type")),
                    expense_amount=_num(r.get("expense_amount")),
                    note=_text(r.get("note")),
                )
            )
        MortgageEvent.objects.bulk_create(events, batch_size=5000)
        return len(link)


def _text(value):
    if value is None or value != value:  # NaN
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _aware(ts):
    from datetime import timezone as tz

    if ts is None or ts != ts:
        return None
    return ts.to_pydatetime().replace(tzinfo=tz.utc)
