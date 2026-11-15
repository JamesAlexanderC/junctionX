"""Active consents -> the `linked` input of build_profile (MB-4).

External rows join the S-Bank ledger in the CLAUDE.md columns, plus bank,
merchant_name and synthetic. They have no balance_after_eur (see
inferences/multibank.py). Never raw IDs as names: merchant_name is the
creditor or debtor name the other bank gives.
"""

from __future__ import annotations

import re

import pandas as pd

from . import mapping
from .models import BankConsent, ExternalTransaction, LinkedAccount

EXT_ACCOUNT = "EXT-{}"
EXT_TX = "EXT-{}"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "unknown").lower()).strip("-")


def _row(t: ExternalTransaction, customer_id: str, bank: str) -> dict:
    name = t.creditor_name if t.amount_eur < 0 else t.debtor_name
    day = pd.Timestamp(t.booking_date)
    return {
        "tx_id": EXT_TX.format(t.id),
        "customer_id": customer_id,
        "bank_account_id": EXT_ACCOUNT.format(t.linked_account_id),
        "tx_date": day,
        "tx_timestamp": day + pd.Timedelta(hours=12),
        "category": t.category,
        "tx_amount_eur": t.amount_eur,
        "balance_after_eur": float("nan"),
        "transaction_type": mapping.transaction_type(t.category),
        "merchant_id": "EXT:" + _slug(name),
        "mcc_code": t.mcc or "",
        "merchant_name": name or "Unknown",
        "bank": bank,
        "synthetic": True,
    }


def _account(a: LinkedAccount) -> dict:
    return {
        "bank": a.consent.bank_name,
        "bank_code": a.consent.bank_code,
        "consent_id": a.consent_id,
        "name": a.name,
        "type": a.type,
        "iban_masked": a.iban_masked,
        "balance_eur": a.balance_eur,
        "balance_date": a.balance_date.isoformat(),
        "simulated": True,
    }


def linked_context(customer_id: str) -> dict | None:
    """{transactions, accounts, consents} for active consents, else None."""
    consents = list(
        BankConsent.objects.filter(customer_id=customer_id, status="active")
    )
    if not consents:
        return None
    accounts = list(
        LinkedAccount.objects.filter(consent__in=consents).select_related("consent")
    )
    txs = ExternalTransaction.objects.filter(
        linked_account__in=accounts
    ).select_related("linked_account__consent")
    rows = [_row(t, customer_id, t.linked_account.consent.bank_name) for t in txs]
    return {
        "transactions": pd.DataFrame(rows) if rows else None,
        "accounts": [_account(a) for a in accounts],
        "consents": [
            {
                "consent_id": c.id,
                "bank": c.bank_name,
                "expires_at": c.expires_at.date().isoformat(),
            }
            for c in consents
        ],
    }


def mark_own_transfers(customer_id: str, sbank_df) -> int:
    """#41: flag external rows that pair with a transfer on another account."""
    from inferences.common import prepare
    from inferences.multibank import merged_transactions, own_transfer_ids

    linked = linked_context(customer_id)
    if not linked or linked["transactions"] is None or sbank_df is None:
        return 0
    merged = prepare(merged_transactions(sbank_df, linked["transactions"]))
    ids = {
        int(t[len("EXT-") :])
        for t in own_transfer_ids(merged)
        if str(t).startswith("EXT-")
    }
    ExternalTransaction.objects.filter(
        linked_account__consent__customer_id=customer_id
    ).update(own_transfer=False)
    return ExternalTransaction.objects.filter(id__in=ids).update(own_transfer=True)
