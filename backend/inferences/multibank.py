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
from .common import matched_own_transfers, prepare, r2
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


def merged_transactions(
    sbank_df: pd.DataFrame, external_df: pd.DataFrame | None
) -> pd.DataFrame:
    """S-Bank rows plus linked other-bank rows (MULTIBANK_PLAN.md §5).

    External rows have no balance_after_eur, so the S-Bank balance (#17 B,
    #30 lowest balance) is unchanged; #113 adds linked balances separately.
    """
    home = sbank_df.copy()
    home["bank"] = _bank_col(home)
    if "synthetic" not in home.columns:
        home["synthetic"] = False
    if external_df is None or not len(external_df):
        return home
    return pd.concat([home, external_df], ignore_index=True, sort=False)


def own_transfer_ids(df: pd.DataFrame) -> set:
    """#41: tx_ids of transfers between the customer's own accounts, matched
    across banks (equal amount within 1 day; common.matched_own_transfers)."""
    return matched_own_transfers(df)


def _linked_summary(prepared: pd.DataFrame, linked: dict | None) -> dict:
    """What the consents added: banks, accounts, consents, #41 matches."""
    linked = linked or {}
    external = set(prepared.loc[prepared["bank"] != HOME_BANK, "tx_id"])
    return {
        "connected_banks": sorted({a["bank"] for a in linked.get("accounts", [])}),
        "linked_accounts": linked.get("accounts", []),
        "consents": linked.get("consents", []),
        "own_transfers_found": len(own_transfer_ids(prepared) & external),
        "simulated": bool(linked.get("accounts")),
    }


def _is_loan(bill: dict) -> bool:
    return (
        str(bill.get("category", "")).lower() in th.LOAN_CATEGORIES
        or str(bill.get("mcc_code", "")) in th.LOAN_MCCS
    )


def compute_multibank(df: pd.DataFrame, today, linked: dict | None = None) -> dict:
    """profile["multibank"]: accounts, true income (#41), hidden loans (#42),
    cross-bank duplicate subscriptions (#43), and what linked banks added."""
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
            **_linked_summary(prepared, linked),
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
        **_linked_summary(prepared, linked),
    }


# Numbers the before/after card compares (MULTIBANK_PLAN.md §5 delta).
DELTA_KEYS = {
    "safe_to_spend": ("forecast", "safe_to_spend_week"),
    "dsti": ("mortgage", "dsti"),
    "buffer_months": ("levels", "buffer_months"),
    "level": ("levels", "current"),
    "monthly_income": ("income", "monthly_income"),
}


def key_metrics(profile: dict) -> dict:
    return {
        k: (profile.get(section) or {}).get(field)
        for k, (section, field) in DELTA_KEYS.items()
    }


def with_delta(combined: dict, sbank_only: dict) -> dict:
    """Attach the S-Bank-only numbers and the before/after delta."""
    before, after = key_metrics(sbank_only), key_metrics(combined)
    combined["multibank"]["sbank_only"] = before
    combined["multibank"]["delta"] = {
        k: {"before": before[k], "after": after[k]} for k in DELTA_KEYS
    }
    return combined
