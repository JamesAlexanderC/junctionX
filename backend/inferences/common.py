"""Shared definitions used by every inference (context.md "Shared definitions").

- Inflow = tx_amount_eur > 0, outflow = tx_amount_eur < 0.
- Spend = absolute value of outflows, excluding transfers to own accounts.
- B = latest balance_after_eur. Month = calendar month ("YYYY-MM").
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

import pandas as pd

from . import thresholds as th

COLUMNS = [
    "tx_id",
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
]


# --- Small value helpers ---------------------------------------------------------


# Fixed English names: user-facing text must not depend on the server locale.
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def r2(x):
    """Round to 2 dp as a plain float; None, NaN and inf become None."""
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, 2)


def safe_div(a, b, default=0.0):
    """a / b, or default when b is 0 or missing."""
    if b is None or b == 0 or pd.isna(b):
        return default
    return a / b


def iso(d):
    """date / Timestamp -> 'YYYY-MM-DD' (None stays None)."""
    if d is None or (not isinstance(d, date) and pd.isna(d)):
        return None
    return pd.Timestamp(d).date().isoformat()


def to_date(d) -> date:
    """Anything date-like -> datetime.date."""
    return pd.Timestamp(d).date()


# --- Months ---------------------------------------------------------------------


def month_key(d) -> str:
    return pd.Timestamp(d).strftime("%Y-%m")


def month_name(month: str) -> str:
    """English name of a 'YYYY-MM' key: '2026-10' -> 'October'."""
    return MONTH_NAMES[int(month[5:7]) - 1]


def add_months(month: str, n: int) -> str:
    p = pd.Period(month, freq="M") + n
    return str(p)


def full_months(today, n: int, df: pd.DataFrame | None = None) -> list[str]:
    """The last n full calendar months before today's month, oldest first.

    With df, months before the first transaction's month are dropped, and so is
    the first month when the data starts after its first day (not a full month).
    """
    current = month_key(today)
    months = [add_months(current, -k) for k in range(n, 0, -1)]
    if df is not None and len(df):
        first = pd.Timestamp(df["tx_date"].min())
        first_full = (
            month_key(first) if first.day == 1 else add_months(month_key(first), 1)
        )
        months = [m for m in months if m >= first_full]
    return months


def last_complete_month(today) -> str:
    """'YYYY-MM' of the latest complete calendar month as of ``today``: the
    current month when today is its last day, otherwise the month before.
    One rule for "last month" in chat and the Overview (F8: with data ending
    30 Sep, "last month" said August)."""
    today = to_date(today)
    current = month_key(today)
    if today.day == days_in_month(current):
        return current
    return add_months(current, -1)


def days_in_month(month: str) -> int:
    return pd.Period(month, freq="M").days_in_month


def months_spanned(df: pd.DataFrame, today) -> float:
    """Length of the data history up to today in months (at least 1)."""
    if not len(df):
        return 1.0
    days = (pd.Timestamp(today) - pd.Timestamp(df["tx_date"].min())).days + 1
    return max(1.0, days / 30.44)


# --- Frames ---------------------------------------------------------------------


def prepare(df: pd.DataFrame, today=None) -> pd.DataFrame:
    """Copy with proper dtypes, sorted by timestamp, cut at today (inclusive)."""
    out = df.copy()
    if "tx_id" not in out.columns:
        out["tx_id"] = [f"t-{i}" for i in range(len(out))]
    out["tx_date"] = pd.to_datetime(out["tx_date"]).dt.normalize()
    if "tx_timestamp" in out.columns:
        out["tx_timestamp"] = pd.to_datetime(out["tx_timestamp"])
    else:
        out["tx_timestamp"] = out["tx_date"]
    out["tx_amount_eur"] = out["tx_amount_eur"].astype(float)
    for col in ("category", "transaction_type", "merchant_id", "mcc_code"):
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)
    out["category"] = out["category"].str.lower()
    out["merchant_id"] = fill_pseudo_merchants(out)
    if "bank_account_id" not in out.columns:
        out["bank_account_id"] = "A1"
    if today is not None:
        out = out[out["tx_date"] <= pd.Timestamp(today)]
    out = out.sort_values(["tx_timestamp", "tx_id"], kind="stable")
    out["month"] = out["tx_date"].dt.strftime("%Y-%m")
    return out.reset_index(drop=True)


def fill_pseudo_merchants(df: pd.DataFrame) -> pd.Series:
    """merchant_id with "type:<transaction_type>" where it is empty.

    Salary, housing and utilities rows carry no merchant_id in the S-Bank data
    (docs/vocabulary.md); without a key they would all group under "" and
    payday (#1) and bill detection (#4) would mix them up.
    """
    merchant = df["merchant_id"].fillna("").astype(str)
    ttype = df["transaction_type"].fillna("").astype(str).str.lower()
    empty = (merchant == "") & ttype.isin(list(th.PSEUDO_MERCHANT_NAMES))
    return merchant.where(~empty, th.PSEUDO_MERCHANT_PREFIX + ttype)


def merchant_name(df: pd.DataFrame, merchant_id: str) -> str:
    """Display name: optional merchant_name column, else the merchant id."""
    merchant_id = str(merchant_id)
    if merchant_id.startswith(th.PSEUDO_MERCHANT_PREFIX):
        ttype = merchant_id[len(th.PSEUDO_MERCHANT_PREFIX) :]
        return th.PSEUDO_MERCHANT_NAMES.get(ttype, ttype.replace("_", " ").title())
    if "merchant_name" in df.columns:
        names = df.loc[df["merchant_id"] == merchant_id, "merchant_name"].dropna()
        if len(names):
            return str(names.iloc[-1])
    coded = re.fullmatch(th.MERCHANT_ID_RE, merchant_id)
    if coded:  # never show a raw "MRC-GRO-0016" to the user (#24, F11)
        return th.MERCHANT_CODE_NAMES.get(coded.group(1), th.UNKNOWN_MERCHANT_NAME)
    return str(merchant_id)


def own_transfer_mask(df: pd.DataFrame) -> pd.Series:
    """Rows whose transaction_type marks a transfer between own accounts."""
    return df["transaction_type"].str.lower().isin(th.OWN_TRANSFER_TYPES)


def matched_own_transfers(df: pd.DataFrame) -> set:
    """#41: tx_ids of own-account transfer pairs found by matching.

    An outflow and an inflow with the same absolute amount within 1 day, on
    different accounts of the same customer, are a transfer between the
    customer's own accounts (model 5 matching).
    """
    if df["bank_account_id"].nunique() < 2:
        return set()
    outs = df[df["tx_amount_eur"] < 0]
    ins = df[df["tx_amount_eur"] > 0]
    matched: set = set()
    used_in: set = set()
    window = pd.Timedelta(days=th.OWN_TRANSFER_MATCH_DAYS)
    for _, o in outs.iterrows():
        cand = ins[
            (ins["customer_id"] == o["customer_id"])
            & (ins["bank_account_id"] != o["bank_account_id"])
            & ((ins["tx_amount_eur"] + o["tx_amount_eur"]).abs() < 0.005)
            & ((ins["tx_date"] - o["tx_date"]).abs() <= window)
            & (~ins["tx_id"].isin(used_in))
        ]
        if len(cand):
            i = cand.iloc[0]
            matched.update({o["tx_id"], i["tx_id"]})
            used_in.add(i["tx_id"])
    return matched


def internal_mask(df: pd.DataFrame) -> pd.Series:
    """Own transfers by type or by #41 matching."""
    return own_transfer_mask(df) | df["tx_id"].isin(matched_own_transfers(df))


def income_inflows(df: pd.DataFrame) -> pd.DataFrame:
    """Inflows excluding own-account transfers (#2, #41)."""
    return df[(df["tx_amount_eur"] > 0) & ~internal_mask(df)]


def outflows(df: pd.DataFrame) -> pd.DataFrame:
    """All outflows (incl. own transfers) with a positive `amount` column."""
    out = df[df["tx_amount_eur"] < 0].copy()
    out["amount"] = -out["tx_amount_eur"]
    return out


def spend(df: pd.DataFrame) -> pd.DataFrame:
    """Spend: outflows excluding transfers to own accounts, `amount` > 0."""
    out = outflows(df)
    return out[~internal_mask(df).loc[out.index]]


def monthly_totals(frame: pd.DataFrame, months: list[str], col="amount") -> dict:
    """{month: sum of col} for the given months, zero-filled."""
    sums = frame.groupby("month")[col].sum() if len(frame) else pd.Series(dtype=float)
    return {m: float(sums.get(m, 0.0)) for m in months}


def latest_balance(df: pd.DataFrame):
    """B = latest balance_after_eur (#17)."""
    if not len(df) or "balance_after_eur" not in df.columns:
        return None
    vals = df["balance_after_eur"].dropna()
    return float(vals.iloc[-1]) if len(vals) else None


def lowest_balance(df: pd.DataFrame, today, days=30):
    """Lowest balance_after_eur in the last `days` days (#30)."""
    start = pd.Timestamp(today) - pd.Timedelta(days=days)
    win = df[(df["tx_date"] >= start) & (df["tx_date"] <= pd.Timestamp(today))]
    vals = win["balance_after_eur"].dropna() if len(win) else win
    if not len(vals):
        return latest_balance(df)
    return float(vals.min())


def buffer_amount(monthly_essentials) -> float:
    """buffer = max(EUR 50, 10% of monthly essentials)."""
    me = monthly_essentials or 0.0
    return max(th.BUFFER_MIN_EUR, th.BUFFER_ESSENTIALS_SHARE * me)


def is_essential(cat: str, mcc: str = "") -> bool:
    """#7: always-essential category, or an essential MCC in a split category."""
    cat = str(cat).lower()
    if cat in th.ESSENTIAL_CATEGORIES:
        return True
    allowed = th.ESSENTIAL_MCCS_BY_CATEGORY.get(cat)
    return allowed is not None and str(mcc or "") in allowed


def essential_mask(df: pd.DataFrame) -> pd.Series:
    """Rows that are Essentials (#7), with transportation split by MCC."""
    cats = df["category"].astype(str).str.lower()
    mask = cats.isin(th.ESSENTIAL_CATEGORIES)
    mccs = df["mcc_code"].fillna("").astype(str)
    for cat, allowed in th.ESSENTIAL_MCCS_BY_CATEGORY.items():
        mask = mask | ((cats == cat) & mccs.isin(allowed))
    return mask


def _type_in(df: pd.DataFrame, types) -> pd.Series:
    return df["transaction_type"].astype(str).str.lower().isin(types)


def saver_mask(df: pd.DataFrame) -> pd.Series:
    """Saver flows (#75): investment deposits and withdrawals."""
    return _type_in(df, th.SAVER_TYPES)


def neutral_mask(df: pd.DataFrame) -> pd.Series:
    """Neutral own transfers (salary_sweep): neither spending nor Saver."""
    return _type_in(df, th.NEUTRAL_TRANSFER_TYPES)


def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
