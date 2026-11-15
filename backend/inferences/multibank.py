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
from .common import (
    full_months,
    latest_balance,
    matched_own_transfers,
    monthly_totals,
    neutral_mask,
    prepare,
    r2,
)
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


def coverage(prepared: pd.DataFrame, today, linked: dict | None = None) -> dict:
    """#112: how much of the money we see, from S-Bank data alone.

    The share of salary that leaves as a salary sweep and is not matched (#41)
    to a linked account. Above COVERAGE_PARTIAL_SHARE the view is "partial";
    with linked banks and little unmatched it is "full"; else "sbank_only".
    """
    months = full_months(today, th.INCOME_MEDIAN_MONTHS, prepared)
    matched = own_transfer_ids(prepared) if linked else set()
    sweeps = prepared[neutral_mask(prepared) & ~prepared["tx_id"].isin(matched)]
    sweeps = sweeps.assign(amount=-sweeps["tx_amount_eur"])
    ttype = prepared["transaction_type"].str.lower()
    salary = prepared[ttype.isin(th.SALARY_TYPES)]
    salary_total = sum(monthly_totals(salary, months, "tx_amount_eur").values())
    swept = sum(monthly_totals(sweeps, months).values()) if months else 0.0
    share = swept / salary_total if salary_total > 0 else 0.0
    if share > th.COVERAGE_PARTIAL_SHARE:
        level = "partial"
    else:
        level = "full" if (linked or {}).get("accounts") else "sbank_only"
    return {"coverage": level, "unmatched_share": r2(share)}


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


def _summary(prepared: pd.DataFrame, today, linked: dict | None) -> dict:
    cov = coverage(prepared, today, linked)
    return {
        **_linked_summary(prepared, linked),
        "coverage": cov["coverage"],
        "unmatched_share": cov["unmatched_share"],
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
            **_summary(prepared, today, linked),
        }
    home = prepared[prepared["bank"] == HOME_BANK]
    other = prepared[prepared["bank"] != HOME_BANK]
    hidden = _hidden_loans(other, today)
    return {
        "accounts": _accounts(prepared),
        # #41: union of all accounts, own-account transfers removed by matching.
        "true_income": r2(monthly_income(prepared, today)),
        "home_bank_income": r2(monthly_income(home, today)) if len(home) else 0.0,
        "hidden_loans": hidden,
        "hidden_loans_monthly": r2(sum(h["amount"] for h in hidden)),
        "duplicate_subscriptions": _duplicate_subscriptions(prepared, today),
        **_summary(prepared, today, linked),
        **_liquid(home, linked),
    }


def _accounts(prepared: pd.DataFrame) -> list[dict]:
    return [
        {
            "bank_account_id": str(acc),
            "bank": str(g["bank"].iloc[0]),
            "synthetic": bool(g["synthetic"].any()) if "synthetic" in g else False,
        }
        for acc, g in prepared.groupby("bank_account_id")
    ]


def _evidence(rows: pd.DataFrame, n: int = 3) -> list[dict]:
    """Latest rows as {date, amount, bank, name}: never raw IDs (#42)."""
    out = []
    for _, r in rows.sort_values("tx_date").tail(n).iterrows():
        name = r.get("merchant_name")
        out.append(
            {
                "date": r["tx_date"].date().isoformat(),
                "amount": r2(r["tx_amount_eur"]),
                "bank": str(r["bank"]),
                "name": str(name) if isinstance(name, str) and name else "Unknown",
            }
        )
    return out


def _next_on_day(today, day: int) -> str:
    """Next date after today on this day of the month (clamped to month end)."""
    start = pd.Timestamp(today) + pd.Timedelta(days=1)
    for months in (0, 1):
        month = (start + pd.DateOffset(months=months)).to_period("M")
        candidate = month.start_time + pd.Timedelta(
            days=min(day, month.days_in_month) - 1
        )
        if candidate >= start:
            return candidate.date().isoformat()
    return (start + pd.DateOffset(months=1)).date().isoformat()


def _hidden_loans(other: pd.DataFrame, today) -> list[dict]:
    """#42: #4 on the other banks' outflows, kept when loan category / MCC."""
    hidden = []
    if not len(other):
        return hidden
    for b in regular_bills(other, today):
        if not _is_loan(b):
            continue
        rows = other[other["merchant_id"] == b["merchant_id"]]
        day = int(rows["tx_date"].dt.day.mode().iloc[0])
        hidden.append(
            {
                "merchant_id": b["merchant_id"],
                "name": b["name"],
                "bank": str(rows["bank"].iloc[0]),
                "amount": b["amount"],
                "day_of_month": day,
                # The day it is actually paid, not #4's last + median gap.
                "next_date": _next_on_day(today, day),
                "evidence": _evidence(rows),
            }
        )
    return hidden


def _subscriptions_by_account(prepared: pd.DataFrame, today) -> list[dict]:
    """#5 per account, with the account's bank."""
    found = []
    for acc, g in prepared.groupby("bank_account_id"):
        bank = str(g["bank"].iloc[0])
        for sub in subscriptions(regular_bills(g, today)):
            found.append({**sub, "account": str(acc), "bank": bank})
    return found


def _dup_entry(key: str, subs: list[dict]) -> dict:
    monthly = [float(x["amount"]) for x in subs]
    return {
        "merchant_id": key,
        "name": " and ".join(dict.fromkeys(x["name"] for x in subs)),
        "accounts": [x["account"] for x in subs],
        "mcc": subs[0].get("mcc_code") or None,
        "services": [
            {"name": x["name"], "bank": x["bank"], "monthly": r2(x["amount"])}
            for x in subs
        ],
        "monthly_total": r2(sum(monthly)),
        # What paying twice costs: everything but the dearest one, a year.
        "yearly_cost": r2((sum(monthly) - max(monthly)) * 12),
    }


def _duplicate_subscriptions(prepared: pd.DataFrame, today) -> list[dict]:
    """#43: the same merchant as a subscription in two or more accounts, or
    subscriptions with the same MCC at two or more banks (#92)."""
    subs = _subscriptions_by_account(prepared, today)
    dups, used = [], set()
    by_merchant: dict[str, list] = {}
    for x in subs:
        by_merchant.setdefault(x["merchant_id"], []).append(x)
    for merchant, group in by_merchant.items():
        if len({x["account"] for x in group}) >= 2:
            dups.append(_dup_entry(merchant, group))
            used.update(id(x) for x in group)
    by_mcc: dict[str, list] = {}
    for x in subs:
        if id(x) not in used and x.get("mcc_code"):
            by_mcc.setdefault(x["mcc_code"], []).append(x)
    for mcc, group in by_mcc.items():
        if len({x["bank"] for x in group}) >= 2:
            dups.append(_dup_entry(f"mcc-{mcc}", group))
    return dups


def external_liquid(linked: dict | None) -> float:
    """#113: linked current and savings balances (cards and loans excluded)."""
    accounts = (linked or {}).get("accounts") or []
    return r2(
        sum(
            float(a.get("balance_eur") or 0.0)
            for a in accounts
            if a.get("type") in th.LIQUID_ACCOUNT_TYPES
        )
    )


def _liquid(home: pd.DataFrame, linked: dict | None) -> dict:
    """#113: what is liquid across S-Bank and linked accounts."""
    sbank = latest_balance(home) if len(home) else None
    extra = external_liquid(linked)
    return {
        "external_liquid": extra,
        "total_liquid_balance": r2((sbank or 0.0) + extra),
    }


def external_loan_payments(bills: list[dict]) -> float:
    """#42: monthly loan bills paid at other banks (ledger ids start EXT:)."""
    return r2(
        sum(
            float(b["amount"])
            for b in bills
            if str(b["merchant_id"]).startswith("EXT:") and _is_loan(b)
        )
    )


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
