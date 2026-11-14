"""Forecasts (context.md #17 to #23), built on model 6 (cash-flow projection)."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from . import models
from . import thresholds as th
from .common import (
    add_months,
    buffer_amount,
    iso,
    latest_balance,
    month_key,
    months_spanned,
    prepare,
    r2,
    spend,
    to_date,
)


def scheduled_bills(bills: list[dict], start, end) -> list[dict]:
    """#21 helper: every expected bill date in (start, end], repeating each bill
    by its median gap. Next date = last payment + median gap; amount = median."""
    start, end = to_date(start), to_date(end)
    out = []
    for b in bills:
        gap = max(1, round(b["median_gap_days"] or 30))
        d = to_date(b["next_date"])
        while d <= start:
            d += timedelta(days=gap)
        while d <= end:
            out.append(
                {
                    "date": iso(d),
                    "name": b["name"],
                    "merchant_id": b["merchant_id"],
                    "amount": r2(b["amount"]),
                }
            )
            d += timedelta(days=gap)
    return sorted(out, key=lambda x: (x["date"], x["merchant_id"]))


def upcoming_bills(bills: list[dict], today) -> list[dict]:
    """#21: bills in the next 30 days, sorted by date."""
    end = to_date(today) + timedelta(days=th.UPCOMING_BILLS_DAYS)
    return scheduled_bills(bills, to_date(today) - timedelta(days=1), end)


def discretionary_stats(df: pd.DataFrame, today, bills: list[dict]):
    """#19: d = daily discretionary spend over the last 60 days and sigma =
    its standard deviation. Discretionary = spend that is not a scheduled bill
    (days with no spend count as 0).

    Calibration (docs/calibration.md): the doc says median, but on the real
    S-Bank data most days have no spend, so the median is EUR 0 for many
    customers and the forecast never moves. We use the mean, which matches
    the real month-on-month spend; set FORECAST_DAILY_STAT = "median" in
    thresholds.py to go back to the doc's choice."""
    s = spend(df)
    bill_merchants = {b["merchant_id"] for b in bills}
    s = s[~s["merchant_id"].isin(bill_merchants)]
    end = pd.Timestamp(today)
    start = end - pd.Timedelta(days=th.DISCRETIONARY_DAYS - 1)
    days = pd.date_range(start, end)
    daily = s.groupby("tx_date")["amount"].sum().reindex(days, fill_value=0.0)
    centre = np.median if th.FORECAST_DAILY_STAT == "median" else np.mean
    return float(centre(daily.values)), float(np.std(daily.values, ddof=0))


def _scheduled(income: dict, bills: list[dict], today, end):
    """Signed scheduled flows (date, amount) in (today, end]."""
    flows = [(b["date"], -b["amount"]) for b in scheduled_bills(bills, today, end)]
    payday = income.get("payday") or {}
    if payday.get("found"):
        # P1.1: the salary_sweep leaves the day after payday, so project only
        # the retained part of each salary (#17).
        swept = (income.get("monthly_income") or 0.0) - income.get(
            "retained_income", income.get("monthly_income") or 0.0
        )
        amount = max(0.0, payday["amount"] - swept)
        d = to_date(payday["next_payday"])
        while d <= to_date(end):
            flows.append((iso(d), amount))
            d = to_date(pd.Timestamp(d) + pd.DateOffset(months=1))
    return flows


def safe_to_spend_week(
    balance, bills_before_payday, monthly_saving, buffer, days_to_payday, cycle_days
):
    """#17 Safe to spend this week (context.md "Forecasts").

    Available = B - bills due before payday - monthly saving x share of the
    pay cycle left - buffer; safe this week = Available x min(7, D) / D,
    floored at 0. Only the saving still due this cycle is held back (not the
    whole month's), as context.md specifies and Will confirmed (FC-5).
    """
    days = max(1, days_to_payday)
    cycle_left = min(1.0, days / max(1, cycle_days))
    available = balance - bills_before_payday - monthly_saving * cycle_left - buffer
    return max(0.0, available * min(7, days) / days)


def month_end_target(today):
    """#19 target date: this month's last day, or next month's when fewer
    than MONTH_END_ROLLOVER_DAYS are left (FC-1: on the data's as-of date,
    30 Sep, the old horizon was 0 days and the band collapsed)."""
    month = month_key(today)
    end = to_date(pd.Period(month, freq="M").end_time)
    if (end - today).days < th.MONTH_END_ROLLOVER_DAYS:
        end = to_date(pd.Period(add_months(month, 1), freq="M").end_time)
    return end


def compute_forecast(df: pd.DataFrame, today, income: dict, baskets: dict) -> dict:
    """profile["forecast"] (#17 to #23)."""
    df = prepare(df, today)
    today = to_date(today)
    bills = income.get("bills", [])
    b0 = latest_balance(df) or 0.0
    buf = buffer_amount(baskets.get("monthly_essentials"))
    d, sigma = discretionary_stats(df, today, bills) if len(df) else (0.0, 0.0)
    payday = income.get("payday") or {}
    found = bool(payday.get("found"))
    days_to_payday = max(1, payday["days_to_payday"]) if found else None

    # #19 End-of-month balance with an 80% band.
    month_end = month_end_target(today)
    horizon_days = max(
        (month_end - today).days,
        days_to_payday or th.NO_PAYDAY_HORIZON_DAYS,
    )
    horizon = today + timedelta(days=horizon_days)
    flows = _scheduled(income, bills, today, horizon)
    path = models.project_balance(b0, today, horizon, d, sigma, flows)
    days_left = (month_end - today).days
    if days_left > 0:
        eom = path[days_left - 1]
        end_of_month = {
            "date": iso(month_end),
            "expected": r2(eom["expected"]),
            "low": r2(eom["low"]),
            "high": r2(eom["high"]),
        }
    else:
        end_of_month = {
            "date": iso(month_end),
            "expected": r2(b0),
            "low": r2(b0),
            "high": r2(b0),
        }

    # #20 Danger days: days before the next payday whose low bound < EUR 50.
    to_payday = days_to_payday or th.NO_PAYDAY_HORIZON_DAYS
    cycle = path[: max(0, to_payday - 1)] if found else path[:to_payday]
    danger = [iso(p["date"]) for p in cycle if p["low"] < th.DANGER_BALANCE_EUR]

    # #17 Safe to spend this week.
    if found:
        payday_date = to_date(payday["next_payday"])
        due = sum(
            b["amount"]
            for b in scheduled_bills(bills, today, payday_date - timedelta(days=1))
        )
        last = payday.get("last_payday")
        cycle_days = (
            (payday_date - to_date(last)).days if last else th.DEFAULT_CYCLE_DAYS
        )
        safe_week = safe_to_spend_week(
            b0,
            due,
            baskets.get("monthly_saving") or 0.0,
            buf,
            days_to_payday,
            cycle_days,
        )
    else:
        # No payday found: fall back to balance - buffer (edge-case test).
        safe_week = max(0.0, b0 - buf)

    # #18 Safe to save today: lowest low bound before next payday - buffer.
    lows = [p["low"] for p in cycle] or [b0]
    safe_save = max(0.0, min(lows) - buf)

    return {
        "balance": r2(b0),
        "buffer": r2(buf),
        "daily_discretionary": {
            "stat": th.FORECAST_DAILY_STAT,
            "value": r2(d),
            "std": r2(sigma),
        },
        "safe_to_spend_week": r2(safe_week),
        "safe_to_save_today": r2(safe_save),
        "end_of_month": end_of_month,
        "daily_path": [
            {
                "date": iso(p["date"]),
                "expected": r2(p["expected"]),
                "low": r2(p["low"]),
                "high": r2(p["high"]),
            }
            for p in path
        ],
        "danger_days": danger,
        "upcoming_bills": upcoming_bills(bills, today),
        "surprise_fund_monthly": r2(surprise_fund(df, today, baskets)),
        "seasonal": seasonal(df, today),
    }


def surprise_fund(df: pd.DataFrame, today, baskets: dict) -> float:
    """#22: Surprises over the last 12 months / 12, scaled up when there is
    less than 12 months of data (sum / months of data)."""
    from .baskets import classify

    cls = classify(df, today)
    start = pd.Timestamp(today) - pd.DateOffset(months=12)
    s = cls[(cls["basket"] == "surprise") & (cls["tx_date"] > start)]["amount"].sum()
    months = min(12.0, months_spanned(df, today))
    return float(s) / months


def seasonal(df: pd.DataFrame, today) -> dict:
    """#23: ratio = spend in next month last year / mean monthly spend last
    year; warn when > 1.25 with a pot of (ratio - 1) x mean monthly spend."""
    current = month_key(today)
    next_month = add_months(current, 1)
    last_year = [add_months(current, -k) for k in range(12, 0, -1)]
    empty = {"next_month": next_month, "ratio": None, "warn": False, "pot": 0.0}
    if not len(df) or month_key(df["tx_date"].min()) > last_year[0]:
        return empty  # needs a full year of history
    s = spend(df)
    by_month = s.groupby("month")["amount"].sum()
    totals = [float(by_month.get(m, 0.0)) for m in last_year]
    mean = float(np.mean(totals))
    ratio = models.seasonal_index(
        float(by_month.get(add_months(next_month, -12), 0.0)), mean
    )
    if ratio is None:
        return empty
    warn = ratio > th.SEASONAL_WARN_RATIO
    return {
        "next_month": next_month,
        "ratio": r2(ratio),
        "warn": bool(warn),
        "pot": r2((ratio - 1) * mean) if warn else 0.0,
    }
