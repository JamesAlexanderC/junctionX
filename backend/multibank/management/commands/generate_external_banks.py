"""Write synthetic other-bank data for scenarios A-E (MULTIBANK_PLAN.md MB-2).

Only adds a file under data/synthetic/; S-Bank rows are read, never changed.
"""

import json

from django.core.management.base import BaseCommand

from coach.models import Transaction
from multibank import scenarios as sc
from multibank.data import EXTERNAL_BANKS_FILE
from multibank.synthetic import START, generate


def _sweeps(customer_id):
    rows = Transaction.objects.filter(
        customer_id=customer_id,
        transaction_type="salary_sweep",
        tx_date__gte=START,
    ).values_list("tx_date", "tx_amount_eur")
    return [(day, round(-amount, 2)) for day, amount in rows]


class Command(BaseCommand):
    help = "Generate synthetic other-bank accounts (simulated PSD2 data)."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, seed, **options):
        sweeps = {sc.SALARY_ELSEWHERE: _sweeps(sc.SALARY_ELSEWHERE)}
        data = generate(seed=seed, sweeps=sweeps)
        EXTERNAL_BANKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXTERNAL_BANKS_FILE.write_text(json.dumps(data, indent=1, sort_keys=True))
        for customer, banks in data["customers"].items():
            for bank, held in banks.items():
                n = sum(len(a["transactions"]) for a in held["accounts"])
                self.stdout.write(
                    f"{customer} @ {sc.BANKS[bank]}: {len(held['accounts'])} "
                    f"account(s), {n} transactions"
                )
        self.stdout.write(f"Wrote {EXTERNAL_BANKS_FILE} (seed {seed})")
