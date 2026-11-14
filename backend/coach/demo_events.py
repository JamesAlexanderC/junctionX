"""Synthetic demo events injected into real customers (handoff step 4).

Pure DataFrame functions; the inject_demo_events command writes the result.
Every injected row has is_synthetic=True and shifts the running balance of all
later rows, so balance_after_eur stays consistent. remove_synthetic undoes it.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

BONUS_EUR = 5000.0
BONUS_DAYS_BEFORE_REF = 10
OVERDRAFT_DIP_EUR = 40.0  # the charge takes the balance to EUR -40
OVERDRAFT_MIN_CHARGE_EUR = 10.0
# A bigger synthetic charge would distort baskets, anomalies and buffers, so
# the splurger must be someone whose balance actually runs low this month.
OVERDRAFT_MAX_CHARGE_EUR = 1500.0
OVERDRAFT_FEE_EUR = 5.0
FEE_MARGIN_DAYS = 2  # leave room for the fee to land before the ref date


def _with_flag(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "is_synthetic" not in out.columns:
        out["is_synthetic"] = False
    out["is_synthetic"] = out["is_synthetic"].fillna(False).astype(bool)
    return out


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["tx_timestamp", "is_synthetic"], kind="stable").reset_index(
        drop=True
    )


def _add_row(df: pd.DataFrame, row: dict) -> pd.DataFrame:
    """Insert one synthetic row and shift every later balance by its amount."""
    out = _with_flag(df)
    ts, amount = pd.Timestamp(row["tx_timestamp"]), float(row["tx_amount_eur"])
    later = out["tx_timestamp"] > ts
    out["balance_after_eur"] = out["balance_after_eur"].where(
        ~later, (out["balance_after_eur"] + amount).round(2)
    )
    before = out[~later]
    prev = float(before["balance_after_eur"].iloc[-1]) if len(before) else 0.0
    template = out.iloc[0].to_dict() if len(out) else {}
    new = {
        **template,
        "merchant_id": "",
        "mcc_code": "",
        **row,
        "tx_timestamp": ts,
        "tx_date": ts.normalize(),
        "balance_after_eur": round(prev + amount, 2),
        "is_synthetic": True,
    }
    return _sorted(pd.concat([out, pd.DataFrame([new])], ignore_index=True))


def remove_synthetic(df: pd.DataFrame) -> pd.DataFrame:
    """Drop synthetic rows and undo their balance shifts."""
    out = _with_flag(df)
    for _, row in out[out["is_synthetic"]].iterrows():
        later = out["tx_timestamp"] > row["tx_timestamp"]
        out.loc[later, "balance_after_eur"] -= row["tx_amount_eur"]
    kept = out[~out["is_synthetic"]].copy()
    kept["balance_after_eur"] = kept["balance_after_eur"].round(2)
    return kept.reset_index(drop=True)


def inject_bonus(df: pd.DataFrame, ref: date) -> pd.DataFrame:
    """Secret saver: one EUR 5,000 one-off bonus, 10 days before ref."""
    ts = pd.Timestamp(ref - timedelta(days=BONUS_DAYS_BEFORE_REF)) + pd.Timedelta(
        hours=9
    )
    cid = df["customer_id"].iloc[0]
    return _add_row(
        df,
        {
            "tx_id": f"{cid}-synth-bonus",
            "tx_timestamp": ts,
            "tx_amount_eur": BONUS_EUR,
            "category": "Other Income",
            "transaction_type": "other_income",
            "merchant_id": "SYNTH-BONUS",
        },
    )


def inject_overdraft(df: pd.DataFrame, ref: date) -> pd.DataFrame:
    """Payday splurger: a charge on this month's lowest-balance day takes the
    balance to EUR -40, then a EUR 5 overdraft fee the next day (#85, #86)."""
    out = _with_flag(df)
    start = pd.Timestamp(ref.replace(day=1))
    end = pd.Timestamp(ref - timedelta(days=FEE_MARGIN_DAYS))
    month = out[(out["tx_date"] >= start) & (out["tx_date"] <= end)]
    if month.empty:
        raise ValueError(f"no transactions between {start:%Y-%m-%d} and {end:%Y-%m-%d}")
    low = month.loc[month["balance_after_eur"].idxmin()]
    charge = max(
        float(low["balance_after_eur"]) + OVERDRAFT_DIP_EUR, OVERDRAFT_MIN_CHARGE_EUR
    )
    if charge > OVERDRAFT_MAX_CHARGE_EUR:
        raise ValueError(
            f"lowest balance this month is EUR {low['balance_after_eur']:.0f}: an "
            f"overdraft needs a charge above EUR {OVERDRAFT_MAX_CHARGE_EUR:.0f}. "
            "Pick a splurger whose balance runs low."
        )
    ts = pd.Timestamp(low["tx_timestamp"]) + pd.Timedelta(minutes=1)
    cid = out["customer_id"].iloc[0]
    out = _add_row(
        out,
        {
            "tx_id": f"{cid}-synth-overdraft",
            "tx_timestamp": ts,
            "tx_amount_eur": -round(charge, 2),
            "category": "Lifestyle",
            "transaction_type": "purchase",
            "merchant_id": "SYNTH-PURCHASE",
            "mcc_code": "5999",
        },
    )
    return _add_row(
        out,
        {
            "tx_id": f"{cid}-synth-fee",
            "tx_timestamp": ts + pd.Timedelta(days=1),
            "tx_amount_eur": -OVERDRAFT_FEE_EUR,
            "category": "fee",
            "transaction_type": "fee",
            "merchant_id": "S-BANK",
        },
    )
