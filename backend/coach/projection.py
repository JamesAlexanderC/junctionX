"""Dated cash-flow changes and summaries for alert-coach simulations."""

import copy
import math
from datetime import timedelta

from inferences import models, thresholds as th
from inferences.common import buffer_amount, to_date
from inferences.forecast import scheduled_flows


def prepare(profile):
    """Keep an immutable baseline and an unrounded working path per scenario."""
    if "_projection" in profile:
        return
    today = to_date(profile["today"])
    fc = profile.setdefault("forecast", {})
    balance = float(profile.get("balance") or 0)
    payday = profile.get("income", {}).get("payday", {})
    end = today.replace(day=28) + timedelta(days=4)
    end = end.replace(day=1) - timedelta(days=1)
    horizon = max(
        end,
        today
        + timedelta(
            days=(
                max(1, payday.get("days_to_payday") or 1)
                if payday.get("found")
                else th.NO_PAYDAY_HORIZON_DAYS
            )
        ),
    )
    path = copy.deepcopy(fc.get("daily_path") or [])
    stats = fc.get("daily_discretionary") or {}
    daily = stats.get("value")
    sigma = stats.get("std", 0)
    # Old stored profiles may lack stats or a complete path. Recover their
    # first-day drift and band before rebuilding the same scheduled projection.
    if daily is None and path:
        first = path[0]
        days = max(1, (to_date(first["date"]) - today).days)
        flows = scheduled_flows(
            profile.get("income", {}),
            profile.get("income", {}).get("bills", []),
            today,
            first["date"],
        )
        daily = (balance + sum(v for _, v in flows) - first["expected"]) / days
        sigma = (first["high"] - first["expected"]) / (th.BAND_Z * math.sqrt(days))
    daily = max(0.0, float(daily or 0))
    if not path or to_date(path[-1]["date"]) < horizon:
        flows = scheduled_flows(
            profile.get("income", {}),
            profile.get("income", {}).get("bills", []),
            today,
            horizon,
        )
        path = models.project_balance(balance, today, horizon, daily, sigma, flows)
        path = [{**p, "date": p["date"].isoformat()} for p in path]
    profile["_projection"] = {
        "baseline": copy.deepcopy(path),
        "path": path,
        "balance": balance,
        "weekly": fc.get("safe_to_spend_week", 0),
        "daily": daily,
    }


def _cycle(profile, path):
    today = to_date(profile["today"])
    payday = profile.get("income", {}).get("payday", {})
    found = payday.get("found") and payday.get("next_payday")
    end = (
        to_date(payday["next_payday"])
        if found
        else today + timedelta(days=th.NO_PAYDAY_HORIZON_DAYS + 1)
    )
    return [p for p in path if today < to_date(p["date"]) < end]


def summarise(profile):
    """Derive all changed forecast values from the same dated daily path.

    Keep #17's original allowance as the baseline. Any increase comes only
    from additional pre-payday capacity in the path, prorated over that cycle.
    """
    state = profile["_projection"]
    path = state["path"]
    fc = profile["forecast"]
    today = to_date(profile["today"])
    balance = float(profile.get("balance") or 0)
    buffer = fc.get(
        "buffer", buffer_amount(profile.get("baskets", {}).get("monthly_essentials"))
    )
    cycle = _cycle(profile, path)
    lowest = min([balance, *[p["low"] for p in cycle]])
    baseline_low = min(
        [state["balance"], *[p["low"] for p in _cycle(profile, state["baseline"])]]
    )
    available = max(0.0, lowest - buffer)
    gain = available - max(0.0, baseline_low - buffer)
    payday = profile.get("income", {}).get("payday", {})
    days = (
        max(1, (to_date(payday["next_payday"]) - today).days)
        if (payday.get("found") and payday.get("next_payday"))
        else th.NO_PAYDAY_HORIZON_DAYS
    )
    fc["balance"] = round(balance, 2)
    fc["safe_to_save_today"] = round(available, 2)
    fc["safe_to_spend_week"] = round(
        min(
            max(0, balance - buffer),
            max(0, state["weekly"] + gain * min(7, days) / days),
        ),
        2,
    )
    fc["danger_days"] = [p["date"] for p in cycle if p["low"] < th.DANGER_BALANCE_EUR]
    fc["daily_path"] = [
        {"date": p["date"], **{k: round(p[k], 2) for k in ("expected", "low", "high")}}
        for p in path
    ]
    eom = next(
        (
            p
            for p in path
            if to_date(p["date"]).month == today.month
            and (to_date(p["date"]) + timedelta(days=1)).month != today.month
        ),
        None,
    )
    fc["end_of_month"] = {
        k: round(eom[k] if eom else balance, 2) for k in ("expected", "low", "high")
    }


def shift(profile, amount, on=None, daily=False):
    """Apply a dated one-off flow or a recurring daily reduction in spending."""
    today = to_date(profile["today"])
    for point in profile["_projection"]["path"]:
        when = to_date(point["date"])
        delta = (
            amount * (when - today).days
            if daily
            else (amount if on is None or when >= to_date(on) else 0)
        )
        for key in ("expected", "low", "high"):
            point[key] += delta
