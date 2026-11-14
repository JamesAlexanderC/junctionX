"""Income and bills (context.md #1 to #6)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import models
from . import thresholds as th
from .common import (
    add_months,
    days_in_month,
    full_months,
    income_inflows,
    internal_mask,
    iso,
    merchant_name,
    month_key,
    monthly_totals,
    outflows,
    prepare,
    r2,
    to_date,
)


def _previous_weekday(d: date) -> date:
    """Move a weekend date back to Friday (#1)."""
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _payday_in_month(month: str, day: int) -> date:
    p = pd.Period(month, freq="M")
    return _previous_weekday(date(p.year, p.month, min(day, days_in_month(month))))


def detect_payday(df: pd.DataFrame, today) -> dict:
    """#1 Payday.

    Group inflows by merchant_id; keep groups seen in >= 3 of the last 4 months
    with amount CV < 0.15. The largest group is salary. Payday = median day of
    month; next payday = that day (moved to the previous weekday on weekends),
    this month if salary has not arrived yet, otherwise next month.
    """
    today = to_date(today)
    inflows = income_inflows(df)
    current = month_key(today)
    window = {add_months(current, -k) for k in range(th.RECURRENCE_WINDOW_MONTHS)}
    best = None
    for merchant, g in inflows.groupby("merchant_id"):
        months_seen = set(g["month"]) & window
        if len(months_seen) < th.RECURRENCE_MIN_MONTHS:
            continue
        if models.cv(g["tx_amount_eur"]) >= th.SALARY_CV_MAX:
            continue
        monthly = g.groupby("month")["tx_amount_eur"].sum().median()
        if best is None or monthly > best[1]:
            best = (merchant, monthly, g)
    if best is None:
        return {
            "found": False,
            "day_of_month": None,
            "next_payday": None,
            "days_to_payday": None,
            "merchant_id": None,
            "amount": None,
        }
    merchant, _, g = best
    day = int(np.median(g["tx_date"].dt.day))
    paid_this_month = (g["month"] == current).any()
    candidate = _payday_in_month(current, day)
    if paid_this_month or candidate < today:
        # Late salary this month is alert #100's job; we look to next month.
        candidate = _payday_in_month(add_months(current, 1), day)
    return {
        "found": True,
        "day_of_month": day,
        "next_payday": iso(candidate),
        "days_to_payday": (candidate - today).days,
        "merchant_id": str(merchant),
        "amount": r2(g["tx_amount_eur"].median()),
        "last_payday": iso(g["tx_date"].max()),
        "payday_dates": [iso(d) for d in sorted(g["tx_date"].unique())],
    }


def monthly_income_series(df: pd.DataFrame, today) -> list[dict]:
    """#2 per month: sum of inflows excluding own-account transfers (#41)."""
    if not len(df):
        return []
    first = month_key(df["tx_date"].min())
    current = month_key(today)
    months, m = [], first
    while m <= current:
        months.append(m)
        m = add_months(m, 1)
    totals = monthly_totals(income_inflows(df), months, col="tx_amount_eur")
    return [{"month": k, "value": r2(v)} for k, v in totals.items()]


def monthly_income(df: pd.DataFrame, today) -> float:
    """#2: median of the last 3 full months' income."""
    months = full_months(today, th.INCOME_MEDIAN_MONTHS, df)
    if not months:
        return 0.0
    totals = monthly_totals(income_inflows(df), months, col="tx_amount_eur")
    return float(np.median(list(totals.values())))


def income_stability(df: pd.DataFrame, today) -> dict:
    """#3: CV of the last 6 monthly incomes (full months with data)."""
    months = full_months(today, th.STABILITY_MONTHS, df)
    if not len(df) or len(months) < 2:
        return {"cv": None, "label": None}
    totals = monthly_totals(income_inflows(df), months, col="tx_amount_eur")
    value = models.cv(totals.values())
    if value < th.STABILITY_STEADY_CV:
        label = "Steady"
    elif value <= th.STABILITY_VARIES_CV:
        label = "Varies"
    else:
        label = "Irregular"
    return {"cv": r2(value), "label": label}


def regular_bills(df: pd.DataFrame, today) -> list[dict]:
    """#4 Regular bills (model 1).

    Outflows (excluding own transfers) by merchant seen in >= 3 of the last 4
    months, median gap 25 to 35 days, amount CV < 0.20. Expected amount =
    median; next date = last date + median gap. #5 marks subscriptions.
    """
    outs = outflows(df)
    outs = outs[~internal_mask(df).loc[outs.index]]
    bills = []
    for merchant, g in outs.groupby("merchant_id"):
        rec = models.recurrence(g["tx_date"], g["amount"], today, cv_max=th.BILL_CV_MAX)
        if rec is None:
            continue
        is_sub = (
            rec["median_amount"] < th.SUBSCRIPTION_MAX_EUR
            and rec["cv"] < th.SUBSCRIPTION_CV_MAX
        )
        bills.append(
            {
                "merchant_id": str(merchant),
                "name": merchant_name(df, merchant),
                "category": str(g["category"].mode().iloc[0]),
                "mcc_code": str(g["mcc_code"].mode().iloc[0]),
                "amount": r2(rec["median_amount"]),
                "amount_cv": r2(rec["cv"]),
                "median_gap_days": r2(rec["median_gap_days"]),
                "last_date": iso(rec["last_date"]),
                "next_date": iso(rec["next_date"]),
                "is_subscription": bool(is_sub),
                "tx_ids": [str(t) for t in g["tx_id"]],
            }
        )
    return sorted(bills, key=lambda b: b["next_date"])


def subscriptions(bills: list[dict]) -> list[dict]:
    """#5: bills with median amount < EUR 30 and amount CV < 0.02."""
    keys = ("merchant_id", "name", "amount", "mcc_code", "median_gap_days")
    return [{k: b[k] for k in keys} for b in bills if b["is_subscription"]]


def possibly_unused(
    df: pd.DataFrame, today, subs: list[dict], opened_in_chat=None
) -> list[dict]:
    """#6 Possibly unused subscription ("check this", never fact).

    No other activity at the merchant or in its MCC within 90 days, and either
    the amount rose or the user never opened it in chat. Chat opens are not
    tracked yet, so by default every subscription counts as never opened.
    """
    opened = set(opened_in_chat or [])
    start = pd.Timestamp(today) - pd.Timedelta(days=th.UNUSED_SUBSCRIPTION_DAYS)
    recent = df[(df["tx_date"] >= start) & (df["tx_amount_eur"] < 0)]
    out = []
    for s in subs:
        own = recent["merchant_id"] == s["merchant_id"]
        same_mcc = (recent["mcc_code"] == s["mcc_code"]) & ~own
        own_other = own & ((recent["tx_amount_eur"].abs() - s["amount"]).abs() > 0.005)
        if same_mcc.any() or own_other.any():
            continue
        history = df[df["merchant_id"] == s["merchant_id"]]["tx_amount_eur"].abs()
        rose = len(history) >= 2 and history.iloc[-1] > history.iloc[:-1].median()
        if rose or s["merchant_id"] not in opened:
            out.append(
                {
                    "merchant_id": s["merchant_id"],
                    "name": s["name"],
                    "amount": s["amount"],
                    "reason": "no other activity in 90 days",
                }
            )
    return out


def compute_income(df: pd.DataFrame, today, opened_in_chat=None) -> dict:
    """profile["income"] (#1 to #6)."""
    df = prepare(df, today)
    bills = regular_bills(df, today) if len(df) else []
    subs = subscriptions(bills)
    return {
        "payday": detect_payday(df, today),
        "monthly_income": r2(monthly_income(df, today)) if len(df) else 0.0,
        "monthly_income_series": monthly_income_series(df, today),
        "stability": income_stability(df, today),
        "bills": bills,
        "subscriptions": subs,
        "possibly_unused": possibly_unused(df, today, subs, opened_in_chat),
    }
