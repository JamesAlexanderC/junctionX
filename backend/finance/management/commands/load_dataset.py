"""Load the S-Pankki CSV dataset into Postgres.

Idempotent: every run truncates the finance tables and reloads them. Each CSV
is streamed with ``COPY ... FROM STDIN`` into an all-text staging table (so the
3.6M-row transactions file never sits in Python memory) and then converted
with a single ``INSERT ... SELECT``.
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

CHUNK_BYTES = 8 * 1024 * 1024
BOM = b"\xef\xbb\xbf"
# Dataset timestamps look like 03OCT24:09:04:04.
TS_FORMAT = "DDMONYY:HH24:MI:SS"

FILES = {
    "customers": "tx_customers_junction.csv",
    "transactions": "tx_junction_transactions.csv",
    "applications": "mtg_tx_customer_link_and_final_mtg_infio.csv",
    "events": "mtg_negotiation_history.csv",
}

STAGING_COLUMNS = {
    "customers": ["customer_id", "customer_postal_code", "customer_age"],
    "transactions": [
        "customer_id",
        "bank_account_id",
        "tx_date",
        "tx_timestamp",
        "category",
        "tx_amount_eur",
        "balance_after_eur",
        "transaction_type",
        "merchant_id",
        "mcc_code",
    ],
    "applications": [
        "mortgage_customer_id",
        "customer_id",
        "final_decision",
        "rejection_reason",
        "final_property_price_eur",
        "final_requested_loan_eur",
        "final_equity_amount_eur",
        "final_collateral_value_eur",
        "required_monthly_income_eur",
        "lfinal_loan_to_value",
    ],
    "events": [
        "mortgage_customer_id",
        "timestamp",
        "event_type",
        "property_id",
        "property_type",
        "property_price_estimate",
        "loan_amount",
        "equity_amount",
        "collateral_type",
        "collateral_value",
        "collateral_status",
        "decision",
        "rejection_reason",
        "expense_type",
        "expense_amount",
        "note",
    ],
}

INSERTS = {
    "customers": """
        INSERT INTO finance_customer
            (customer_id, customer_postal_code, customer_age)
        SELECT customer_id, customer_postal_code, NULLIF(customer_age, '')::int
        FROM stg_customers
    """,
    "transactions": f"""
        INSERT INTO finance_transaction (
            customer_id, bank_account_id, tx_date, tx_timestamp, category,
            tx_amount_eur, balance_after_eur, transaction_type, merchant_id,
            mcc_code
        )
        SELECT customer_id, bank_account_id, tx_date::date,
            to_timestamp(tx_timestamp, '{TS_FORMAT}'), category,
            tx_amount_eur::numeric, balance_after_eur::numeric,
            transaction_type, NULLIF(merchant_id, ''), NULLIF(mcc_code, '')
        FROM stg_transactions
    """,
    "applications": """
        INSERT INTO finance_mortgageapplication (
            mortgage_customer_id, customer_id, final_decision, rejection_reason,
            final_property_price_eur, final_requested_loan_eur,
            final_equity_amount_eur, final_collateral_value_eur,
            required_monthly_income_eur, final_loan_to_value
        )
        SELECT mortgage_customer_id, customer_id, final_decision,
            COALESCE(rejection_reason, ''),
            NULLIF(final_property_price_eur, '')::float,
            NULLIF(final_requested_loan_eur, '')::float,
            NULLIF(final_equity_amount_eur, '')::float,
            NULLIF(final_collateral_value_eur, '')::float,
            NULLIF(required_monthly_income_eur, '')::float,
            NULLIF(lfinal_loan_to_value, '')::float
        FROM stg_applications
    """,
    "events": f"""
        INSERT INTO finance_mortgageevent (
            mortgage_customer_id, timestamp, event_type, property_id,
            property_type,
            property_price_estimate, loan_amount, equity_amount,
            collateral_type, collateral_value, collateral_status, decision,
            rejection_reason, expense_type, expense_amount, note
        )
        SELECT mortgage_customer_id, to_timestamp(timestamp, '{TS_FORMAT}'),
            event_type, COALESCE(property_id, ''), COALESCE(property_type, ''),
            NULLIF(property_price_estimate, '')::float,
            NULLIF(loan_amount, '')::float, NULLIF(equity_amount, '')::float,
            COALESCE(collateral_type, ''), NULLIF(collateral_value, '')::float,
            COALESCE(collateral_status, ''), COALESCE(decision, ''),
            COALESCE(rejection_reason, ''), COALESCE(expense_type, ''),
            NULLIF(expense_amount, '')::float, COALESCE(note, '')
        FROM stg_events
    """,
}


class Command(BaseCommand):
    help = "Truncate and reload the finance tables from the dataset CSVs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-dir",
            default=str(settings.DATASET_DIR),
            help="Directory with the S-Pankki CSV files (default: DATASET_DIR).",
        )

    def handle(self, *args, **options):
        base = Path(options["dataset_dir"])
        for name in FILES.values():
            if not (base / name).is_file():
                raise CommandError(f"Missing {base / name}")

        started = time.monotonic()
        with transaction.atomic(), connection.cursor() as wrapper:
            cur = wrapper.cursor  # the raw psycopg cursor (for COPY)
            cur.execute("SET LOCAL synchronous_commit = off")
            self._log("Truncating finance tables")
            cur.execute(
                "TRUNCATE finance_customerprofile, finance_mortgageevent, "
                "finance_mortgageapplication, finance_transaction, "
                "finance_customer RESTART IDENTITY"
            )
            for key in ("customers", "transactions", "applications", "events"):
                self._load(cur, key, base / FILES[key])
            self._log("Analyzing tables")
        with connection.cursor() as cur:
            for table in ("customer", "transaction", "mortgageapplication"):
                cur.execute(f"ANALYZE finance_{table}")
        self._log(f"Done in {time.monotonic() - started:.0f}s")

    def _load(self, cur, key, path):
        """COPY one CSV into a temp staging table and convert it."""
        t0 = time.monotonic()
        cols = STAGING_COLUMNS[key]
        stg = f"stg_{key}"
        cur.execute(
            f"CREATE TEMP TABLE {stg} ({', '.join(c + ' text' for c in cols)})"
            " ON COMMIT DROP"
        )
        total = path.stat().st_size
        sent = 0
        next_report = 0.1
        copy_sql = (
            f"COPY {stg} ({', '.join(cols)}) FROM STDIN WITH (FORMAT csv, HEADER)"
        )
        with path.open("rb") as fh, cur.copy(copy_sql) as copy:
            first = True
            while chunk := fh.read(CHUNK_BYTES):
                if first and chunk.startswith(BOM):
                    chunk = chunk[len(BOM) :]
                first = False
                copy.write(chunk)
                sent += len(chunk)
                if total > 10 * CHUNK_BYTES and sent / total >= next_report:
                    self._log(f"  {path.name}: {sent / total:.0%} streamed")
                    next_report += 0.1
        cur.execute(INSERTS[key])
        rows = cur.rowcount
        self._log(f"Loaded {rows:,} {key} in {time.monotonic() - t0:.1f}s")

    def _log(self, msg):
        self.stdout.write(msg)
        self.stdout.flush()
