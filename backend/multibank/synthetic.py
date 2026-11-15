"""Synthetic other-bank data for scenarios A-E (MULTIBANK_PLAN.md MB-2).

Pure: generate(seed, sweeps) returns Berlin Group NextGenPSD2-shaped accounts
and transactions per customer and bank. The S-Bank data is never changed;
scenario B only mirrors the customer's real S-Bank salary sweeps as inflows
(same amount, same day or the next) so #41 can pair them.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from . import scenarios as sc

END = date(2026, 9, 30)  # the S-Bank data ends here
MONTHS = 12


def _month_starts(end=END, n=MONTHS):
    starts, y, m = [], end.year, end.month
    for _ in range(n):
        starts.append(date(y, m, 1))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return starts[::-1]


def _iban(rng):
    return f"FI•• •••• •••• {rng.randint(1000, 9999)}"


class _Account:
    """Builds one account's transactions and closing balance."""

    def __init__(self, rng, key, name, cash_type, opening):
        self.rng, self.key, self.name, self.cash_type = rng, key, name, cash_type
        self.iban = _iban(rng)
        self.opening, self.rows = opening, []

    def add(self, day, amount, party, code, mcc=None, remittance=""):
        side = "creditor" if amount < 0 else "debtor"
        self.rows.append(
            {
                "transactionId": f"{self.key}-{len(self.rows) + 1:04d}",
                "bookingDate": day.isoformat(),
                "valueDate": day.isoformat(),
                "transactionAmount": {"amount": f"{amount:.2f}", "currency": "EUR"},
                f"{side}Name": party,
                f"{side}Account": {"iban": _iban(self.rng)},
                "remittanceInformationUnstructured": remittance or party,
                "merchantCategoryCode": mcc,
                "proprietaryBankTransactionCode": code,
            }
        )

    def as_dict(self, balance=None):
        rows = sorted(self.rows, key=lambda r: (r["bookingDate"], r["transactionId"]))
        total = sum(float(r["transactionAmount"]["amount"]) for r in rows)
        return {
            "resourceId": self.key,
            "iban": self.iban,
            "name": self.name,
            "cashAccountType": self.cash_type,
            "currency": "EUR",
            "balance": round(self.opening + total if balance is None else balance, 2),
            "balanceDate": END.isoformat(),
            "isSynthetic": True,
            "transactions": rows,
        }


def _hero(rng):
    """A: a car loan paid on the 3rd, before the 15th payday."""
    payment = -float(rng.randint(250, 350))
    # Kept just topped up for the instalments: only a small balance is left.
    leftover = round(rng.uniform(50, 120), 2)
    opening = -payment * len(_month_starts()) + leftover
    acc = _Account(rng, "NDEA-A-CUR", "Car loan account", "CACC", opening=opening)
    for start in _month_starts():
        acc.add(
            start.replace(day=3),
            payment,
            "Autorahoitus Oy",
            "LOAN",
            "6141",
            "Car loan instalment",
        )
    return {"NDEAFIHH": {"accounts": [acc.as_dict()]}}


def _salary_elsewhere(rng, sweeps):
    """B: receives every S-Bank salary sweep; everyday spending happens here."""
    acc = _Account(rng, "OKOY-B-CUR", "Everyday account", "CACC", opening=1500.0)
    for day, amount in sweeps:
        # Same day or the next, never past the end of the S-Bank data.
        when = min(day + timedelta(days=rng.choice([0, 1])), END)
        if START <= day <= END:
            acc.add(
                when,
                round(amount, 2),
                "Own account at S-Bank",
                "TRANSFER",
                remittance="Transfer from own account",
            )
    for start in _month_starts():
        for _ in range(4):
            acc.add(
                start.replace(day=rng.randint(1, 28)),
                -round(rng.uniform(35, 95), 2),
                "Lähikauppa",
                "PURCHASE",
                "5411",
            )
        for _ in range(2):
            acc.add(
                start.replace(day=rng.randint(1, 28)),
                -round(rng.uniform(12, 40), 2),
                "Lounasravintola",
                "PURCHASE",
                "5812",
            )
    return {"OKOYFIHH": {"accounts": [acc.as_dict()]}}


def _duplicate_subs(rng):
    """C: a music service at each of two banks (same MCC 5815)."""
    out = {}
    for bank, key, service, day in (
        ("DABAFIHH", "DABA-C-CUR", "StreamTone Music", 7),
        ("HELSFIHH", "HELS-C-CUR", "Melodia Plus", 21),
    ):
        acc = _Account(rng, key, "Everyday account", "CACC", opening=600.0)
        for start in _month_starts():
            acc.add(start.replace(day=day), -11.99, service, "SUBSCRIPTION", "5815")
        out[bank] = {"accounts": [acc.as_dict()]}
    return out


def _credit_card(rng):
    """D: a card balance (debt) and a monthly repayment from a current account.
    Card purchases stay on the card statement, so spend is never counted twice."""
    cur = _Account(rng, "DABA-D-CUR", "Everyday account", "CACC", opening=2000.0)
    repayment = -float(rng.randint(120, 180))
    for start in _month_starts():
        cur.add(
            start.replace(day=20), repayment, "Card repayment", "CARD_REPAYMENT", "6012"
        )
    card = _Account(rng, "DABA-D-CARD", "Credit card", "CARD", opening=0.0)
    balance = -round(rng.uniform(900, 1600), 2)
    return {"DABAFIHH": {"accounts": [cur.as_dict(), card.as_dict(balance=balance)]}}


def _savings(rng):
    """E: savings held elsewhere (balance only)."""
    acc = _Account(rng, "AABA-E-SAV", "Savings account", "SVGS", opening=0.0)
    balance = round(rng.uniform(2800, 3400), 2)
    return {"AABAFI22": {"accounts": [acc.as_dict(balance=balance)]}}


START = _month_starts()[0]


def generate(seed: int = 42, sweeps: dict | None = None) -> dict:
    """All scenarios; `sweeps` = {customer_id: [(date, amount out), ...]}."""
    rng = random.Random(seed)
    sweeps = sweeps or {}
    return {
        "seed": seed,
        "is_synthetic": True,
        "banks": sc.BANKS,
        "customers": {
            sc.HERO: _hero(rng),
            sc.SALARY_ELSEWHERE: _salary_elsewhere(
                rng, sweeps.get(sc.SALARY_ELSEWHERE, [])
            ),
            sc.DUPLICATE_SUBS: _duplicate_subs(rng),
            sc.CREDIT_CARD: _credit_card(rng),
            sc.SAVINGS_ELSEWHERE: _savings(rng),
        },
    }
