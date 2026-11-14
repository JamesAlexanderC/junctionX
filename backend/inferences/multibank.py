"""Multi-bank view under PSD2, mocked (context.md #41 to #43).

S-Bank gives no other-bank data, so for the demo one account is relabelled as
"Nordea" (relabel_account_as_mock_bank), or a few transactions are moved into
a fake account (mock_second_account). Both are clearly marked synthetic via a
`synthetic` column. A `bank` column names each account's bank; rows without
one are S-Bank.
"""

from __future__ import annotations

import pandas as pd

from . import thresholds as th
from .common import prepare, r2
from .income import monthly_income, regular_bills, subscriptions

HOME_BANK = "S-Bank"
MOCK_BANK = "Nordea"
MOCK_ACCOUNT = "NORDEA-MOCK"


def _bank_col(df: pd.DataFrame) -> pd.Series:
    if "bank" in df.columns:
        return df["bank"].fillna(HOME_BANK).astype(str)
    return pd.Series(HOME_BANK, index=df.index)


def relabel_account_as_mock_bank(df, account_id, bank: str = MOCK_BANK):
    """Mark one bank_account_id as another bank (synthetic, for the demo)."""
    out = df.copy()
    out["bank"] = _bank_col(out)
    if "synthetic" not in out.columns:
        out["synthetic"] = False
    mask = out["bank_account_id"].astype(str) == str(account_id)
    out.loc[mask, "bank"] = bank
    out.loc[mask, "synthetic"] = True
    return out


def mock_second_account(df, merchant_ids, account_id=MOCK_ACCOUNT, bank=MOCK_BANK):
    """Move every transaction of the given merchants (e.g. a car loan, one
    subscription) into a fake other-bank account, labelled synthetic.

    The moved rows get their own running balance starting at 0, and the home
    account's balances are left as they were (good enough for the demo).
    """
    out = df.copy()
    out["bank"] = _bank_col(out)
    if "synthetic" not in out.columns:
        out["synthetic"] = False
    mask = out["merchant_id"].isin(list(merchant_ids))
    out.loc[mask, "bank_account_id"] = account_id
    out.loc[mask, "bank"] = bank
    out.loc[mask, "synthetic"] = True
    moved = out[mask].sort_values("tx_timestamp")
    out.loc[moved.index, "balance_after_eur"] = moved["tx_amount_eur"].cumsum()
    return out


def _is_loan(bill: dict) -> bool:
    return (
        str(bill.get("category", "")).lower() in th.LOAN_CATEGORIES
        or str(bill.get("mcc_code", "")) in th.LOAN_MCCS
    )


def compute_multibank(df: pd.DataFrame, today) -> dict:
    """profile["multibank"]: accounts, true income (#41), hidden loans (#42),
    cross-bank duplicate subscriptions (#43)."""
    raw = df.copy()
    raw["bank"] = _bank_col(raw)
    prepared = prepare(raw, today)
    if not len(prepared):
        return {
            "accounts": [],
            "true_income": 0.0,
            "home_bank_income": 0.0,
            "hidden_loans": [],
            "duplicate_subscriptions": [],
        }
    accounts = []
    for acc, g in prepared.groupby("bank_account_id"):
        accounts.append(
            {
                "bank_account_id": str(acc),
                "bank": str(g["bank"].iloc[0]),
                "synthetic": (
                    bool(g["synthetic"].any()) if "synthetic" in g.columns else False
                ),
            }
        )
    home = prepared[prepared["bank"] == HOME_BANK]
    other = prepared[prepared["bank"] != HOME_BANK]

    # #42 hidden loans: #4 on the other bank's outflows, loan category / MCC.
    hidden = []
    if len(other):
        for b in regular_bills(other, today):
            if _is_loan(b):
                hidden.append(
                    {
                        "merchant_id": b["merchant_id"],
                        "name": b["name"],
                        "bank": str(
                            other.loc[
                                other["merchant_id"] == b["merchant_id"], "bank"
                            ].iloc[0]
                        ),
                        "amount": b["amount"],
                        "next_date": b["next_date"],
                    }
                )

    # #43 same merchant as a subscription (#5) in two or more accounts.
    seen: dict[str, dict] = {}
    for acc, g in prepared.groupby("bank_account_id"):
        for s in subscriptions(regular_bills(g, today)):
            entry = seen.setdefault(
                s["merchant_id"], {"name": s["name"], "accounts": [], "amount": 0.0}
            )
            entry["accounts"].append(str(acc))
            entry["amount"] += s["amount"]
    dups = [
        {
            "merchant_id": m,
            "name": e["name"],
            "accounts": e["accounts"],
            "monthly_total": r2(e["amount"]),
        }
        for m, e in seen.items()
        if len(e["accounts"]) >= 2
    ]
    return {
        "accounts": accounts,
        # #41: union of all accounts, own-account transfers removed by matching.
        "true_income": r2(monthly_income(prepared, today)),
        "home_bank_income": r2(monthly_income(home, today)) if len(home) else 0.0,
        "hidden_loans": hidden,
        "hidden_loans_monthly": r2(sum(h["amount"] for h in hidden)),
        "duplicate_subscriptions": dups,
    }
