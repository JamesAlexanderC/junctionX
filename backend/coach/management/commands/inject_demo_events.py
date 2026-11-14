"""Inject the synthetic demo events (handoff step 4) into loaded customers.

Secret saver: EUR 5,000 one-off bonus. Payday splurger: one overdraft episode
with a EUR 5 fee. Rows are flagged is_synthetic=True. Re-running first removes
earlier synthetic rows and their balance shifts, so it is idempotent.
"""

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from coach import demo_events, services
from coach.models import Transaction

EVENTS = {"saver": demo_events.inject_bonus, "splurger": demo_events.inject_overdraft}


def _frame(cid):
    df = services.transactions_df(cid)
    if df is None:
        raise CommandError(f"{cid}: no transactions loaded. Run load_data first.")
    synthetic = set(
        Transaction.objects.filter(customer_id=cid, is_synthetic=True).values_list(
            "tx_id", flat=True
        )
    )
    return df.assign(is_synthetic=df["tx_id"].isin(synthetic))


def _write(cid, df):
    Transaction.objects.filter(customer_id=cid, is_synthetic=True).delete()
    real = df[~df["is_synthetic"]].set_index("tx_id")["balance_after_eur"]
    rows = list(Transaction.objects.filter(customer_id=cid, tx_id__in=real.index))
    for row in rows:
        row.balance_after_eur = float(real[row.tx_id])
    Transaction.objects.bulk_update(rows, ["balance_after_eur"], batch_size=1000)
    Transaction.objects.bulk_create(
        [
            Transaction(
                tx_id=r.tx_id,
                customer_id=cid,
                account_id=r.bank_account_id,
                tx_date=r.tx_date.date(),
                tx_timestamp=pd.Timestamp(r.tx_timestamp).tz_localize("UTC"),
                category=r.category,
                tx_amount_eur=float(r.tx_amount_eur),
                balance_after_eur=float(r.balance_after_eur),
                transaction_type=r.transaction_type,
                merchant_id=r.merchant_id or "",
                mcc_code=r.mcc_code or "",
                is_synthetic=True,
            )
            for r in df[df["is_synthetic"]].itertuples()
        ]
    )


class Command(BaseCommand):
    help = "Inject the EUR 5,000 bonus and the overdraft + EUR 5 fee demo events."

    def add_arguments(self, parser):
        parser.add_argument("--saver", required=True, help="Gets the bonus")
        parser.add_argument("--splurger", required=True, help="Gets the overdraft")

    def handle(self, *args, **opts):
        ref = services.today()
        plan = {}
        for role, inject in EVENTS.items():
            plan.setdefault(opts[role], []).append(inject)
        with transaction.atomic():
            for cid, injects in plan.items():
                df = demo_events.remove_synthetic(_frame(cid))
                for inject in injects:
                    try:
                        df = inject(df, ref)
                    except ValueError as exc:
                        raise CommandError(f"{cid}: {exc}") from exc
                _write(cid, df)
                added = int(df["is_synthetic"].sum())
                self.stdout.write(
                    self.style.SUCCESS(f"{cid}: {added} synthetic rows (ref {ref})")
                )
