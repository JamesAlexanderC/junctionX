"""The 12 shared mathematical models from context.md ("Mathematical models").

Each formula exists once here; the inference modules call these helpers.
Model 10 (logistic regression, #34/#35) lives with mortgage.py.
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd

from . import thresholds as th
from .common import add_months, month_key

# --- 1. Recurrence detection -----------------------------------------------------


def cv(values) -> float:
    """Coefficient of variation = population std / mean (0 for a single value)."""
    arr = np.asarray(list(values), dtype=float)
    if not len(arr) or arr.mean() == 0:
        return 0.0
    return float(arr.std(ddof=0) / abs(arr.mean()))


def recurrence(
    dates,
    amounts,
    today,
    *,
    cv_max: float,
    gap_min: float = th.RECURRENCE_GAP_MIN_DAYS,
    gap_max: float = th.RECURRENCE_GAP_MAX_DAYS,
    min_months: int = th.RECURRENCE_MIN_MONTHS,
    window_months: int = th.RECURRENCE_WINDOW_MONTHS,
):
    """Model 1: is this series of payments monthly-recurring?

    Seen in at least `min_months` of the last `window_months` months (today's
    month included), median gap between payments in [gap_min, gap_max] days and
    amount CV < cv_max. Next date = last date + median gap. None if not.
    """
    s = pd.DataFrame(
        {"d": pd.to_datetime(list(dates)), "a": np.abs(list(amounts))}
    ).sort_values("d")
    if len(s) < 2:
        return None
    current = month_key(today)
    window = {add_months(current, -k) for k in range(window_months)}
    seen = set(s["d"].dt.strftime("%Y-%m")) & window
    if len(seen) < min_months:
        return None
    gaps = s["d"].diff().dt.days.dropna()
    median_gap = float(gaps.median())
    if not (gap_min <= median_gap <= gap_max):
        return None
    amount_cv = cv(s["a"])
    if amount_cv >= cv_max:
        return None
    last = s["d"].iloc[-1]
    return {
        "median_amount": float(s["a"].median()),
        "cv": amount_cv,
        "median_gap_days": median_gap,
        "last_date": last,
        "next_date": last + timedelta(days=round(median_gap)),
        "count": int(len(s)),
        "months_seen": len(seen),
    }


# --- 2. Robust outlier detection -------------------------------------------------


def mad(values) -> float:
    """Median absolute deviation."""
    arr = np.asarray(list(values), dtype=float)
    if not len(arr):
        return 0.0
    return float(np.median(np.abs(arr - np.median(arr))))


def robust_z(x: float, history) -> float | None:
    """Modified z = 0.6745 (x - median) / MAD. None when MAD is 0."""
    m = mad(history)
    if m == 0:
        return None
    return th.ROBUST_Z_CONST * (x - float(np.median(list(history)))) / m


def iqr_upper_fence(history, k: float = th.SURPRISE_IQR_K) -> float:
    """Q3 + k * (Q3 - Q1)."""
    arr = np.asarray(list(history), dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    return float(q3 + k * (q3 - q1))


# --- 3. Shares and ratios --------------------------------------------------------


def share(part: float, total: float) -> float:
    """part / total, 0 when total is 0."""
    return float(part) / float(total) if total else 0.0


# --- 4. Concentration index (HHI) ------------------------------------------------


def hhi(amounts) -> float:
    """HHI = sum of squared shares."""
    arr = np.asarray(list(amounts), dtype=float)
    total = arr.sum()
    if total <= 0:
        return 0.0
    return float(((arr / total) ** 2).sum())


# --- 5. Time-window clustering ---------------------------------------------------


def count_bursts(
    timestamps,
    size: int = th.BURST_SIZE,
    window_minutes: int = th.BURST_WINDOW_MINUTES,
) -> int:
    """Burst at i iff t[i + size - 1] - t[i] <= window. Bursts do not overlap:
    after a burst, counting resumes after the burst's window."""
    ts = sorted(pd.to_datetime(list(timestamps)))
    window = pd.Timedelta(minutes=window_minutes)
    count, i = 0, 0
    while i + size - 1 < len(ts):
        if ts[i + size - 1] - ts[i] <= window:
            count += 1
            end = ts[i] + window
            while i < len(ts) and ts[i] <= end:
                i += 1
        else:
            i += 1
    return count


def duplicate_pairs(
    frame: pd.DataFrame, window_minutes: int = th.DUPLICATE_WINDOW_MINUTES
) -> list[tuple]:
    """Pairs (tx_id_a, tx_id_b) with the same merchant and amount <= window apart.

    frame needs tx_id, merchant_id, tx_amount_eur, tx_timestamp.
    """
    window = pd.Timedelta(minutes=window_minutes)
    pairs = []
    for _, g in frame.groupby(["merchant_id", "tx_amount_eur"]):
        g = g.sort_values("tx_timestamp")
        rows = list(g.itertuples())
        for a, b in zip(rows, rows[1:]):
            if b.tx_timestamp - a.tx_timestamp <= window:
                pairs.append((a.tx_id, b.tx_id))
    return pairs


# --- 6. Cash-flow projection -----------------------------------------------------


def project_balance(b0, start, end, d, sigma, scheduled=None, z=th.BAND_Z):
    """Model 6: random walk with drift, day by day from start+1 to end.

    balance(t) = balance(t-1) - d + income(t) - bills(t); band = +/- z sigma sqrt(t).
    scheduled: iterable of (date, signed amount). Returns list of dicts.
    """
    sched: dict = {}
    for when, amount in scheduled or []:
        key = pd.Timestamp(when).date()
        sched[key] = sched.get(key, 0.0) + float(amount)
    path = []
    bal = float(b0)
    day = pd.Timestamp(start).date()
    end = pd.Timestamp(end).date()
    t = 0
    while day < end:
        day = day + timedelta(days=1)
        t += 1
        bal = bal - d + sched.get(day, 0.0)
        half = z * sigma * math.sqrt(t)
        path.append(
            {
                "date": day,
                "t": t,
                "expected": bal,
                "low": bal - half,
                "high": bal + half,
            }
        )
    return path


# --- 7. Linear trend -------------------------------------------------------------


def linear_slope(ys) -> float:
    """Least-squares slope of ys against 0..n-1."""
    y = np.asarray(list(ys), dtype=float)
    if len(y) < 2:
        return 0.0
    x = np.arange(len(y), dtype=float)
    den = ((x - x.mean()) ** 2).sum()
    return float(((x - x.mean()) * (y - y.mean())).sum() / den)


# --- 8. Seasonal index -----------------------------------------------------------


def seasonal_index(month_spend: float, mean_monthly_spend: float) -> float | None:
    """SI_m = spend in month m last year / mean monthly spend last year."""
    if not mean_monthly_spend:
        return None
    return month_spend / mean_monthly_spend


# --- 9. Savings and loan arithmetic ----------------------------------------------


def months_to_goal(target: float, saved: float, rate: float) -> int | None:
    """n = ceil((T - S) / r); None when r <= 0 (not reachable)."""
    remaining = target - saved
    if remaining <= 0:
        return 0
    if rate is None or rate <= 0:
        return None
    return math.ceil(round(remaining / rate, 9))


def round_up(x: float, step: float = th.GOAL_ROUND_EUR) -> float:
    """Round x up to a multiple of step."""
    return float(step * math.ceil(round(x / step, 9)))


def monthly_needed(target: float, saved: float, months_left: float) -> float:
    """m = 5 * ceil((T - S) / (5 * n_left)) (#65)."""
    remaining = max(0.0, target - saved)
    if months_left <= 0:
        return round_up(remaining)
    return round_up(remaining / months_left)


def expected_progress(t, t0, t_end) -> float:
    """E%(t) = (t - t0) / (t_end - t0), clipped to [0, 1]."""
    total = (pd.Timestamp(t_end) - pd.Timestamp(t0)).days
    if total <= 0:
        return 1.0
    done = (pd.Timestamp(t) - pd.Timestamp(t0)).days
    return min(1.0, max(0.0, done / total))


def on_track(actual: float, expected: float) -> bool:
    """On track iff actual >= 0.9 * expected (#52)."""
    return actual >= th.ON_TRACK_FACTOR * expected


def counts_for_level_4(goal: dict) -> bool:
    """#31: an active goal counts once it is on track AND has money saved. On
    its first day every goal is on track (0% of 0% expected), so without the
    saved part a just-accepted plan reached Level 4 at once."""
    return (
        bool(goal.get("on_track"))
        and not goal.get("paused")
        and (goal.get("progress_pct") or 0.0) > 0
    )


def goal_difficulty(months: int | None) -> str:
    """#49: <= 2 Easy, 3 to 6 Stretch, > 6 Hard (None = not reachable = Hard)."""
    if months is None:
        return "Hard"
    if months <= th.GOAL_EASY_MONTHS:
        return "Easy"
    if months <= th.GOAL_STRETCH_MONTHS:
        return "Stretch"
    return "Hard"


def annuity_payment(principal: float, monthly_rate: float, n_months: int) -> float:
    """P = L i / (1 - (1 + i)^-n)."""
    if monthly_rate == 0:
        return principal / n_months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -n_months)


def stressed_payment(principal: float) -> float:
    """FIN-FSA stress payment: i = 6% / 12, n = 300 months (#77, #82)."""
    return annuity_payment(principal, th.STRESS_ANNUAL_RATE / 12, th.STRESS_MONTHS)


def months_to_payoff(balance: float, monthly_rate: float, payment: float):
    """n(P) = -ln(1 - iL/P) / ln(1 + i). None if the payment never pays it off."""
    if payment <= 0:
        return None
    if monthly_rate == 0:
        return balance / payment
    x = 1 - monthly_rate * balance / payment
    if x <= 0:
        return None
    return -math.log(x) / math.log(1 + monthly_rate)


# --- 11. Bayesian rating ---------------------------------------------------------


def laplace_weight(ups: int, downs: int) -> float:
    """w = (u + 1) / (u + d + 2)."""
    return (ups + 1) / (ups + downs + 2)


# --- 12. Greedy optimisation and proportional split ------------------------------


def easiest_cut(
    gap: float,
    category_means: dict,
    pcts=th.NEXT_STEP_CUTS,
    horizon_months: int = th.NEXT_STEP_MONTHS,
):
    """#33: p* = min p with gap / (p M_c) <= horizon; tie-break largest saving.

    If no single cut closes the gap in time, return the fastest one (largest
    saving). Returns {category, cut_pct, monthly_saving, months} or None.
    """
    if gap is None or gap <= 0 or not category_means:
        return None
    options = [
        (p, c, p * m) for c, m in category_means.items() for p in pcts if m and m > 0
    ]
    if not options:
        return None
    ok = [o for o in options if gap / o[2] <= horizon_months]
    if ok:
        p_min = min(o[0] for o in ok)
        best = max((o for o in ok if o[0] == p_min), key=lambda o: o[2])
    else:
        best = max(options, key=lambda o: (o[2], -o[0]))
    p, c, saving = best
    return {
        "category": c,
        "cut_pct": p,
        "monthly_saving": saving,
        "months": math.ceil(round(gap / saving, 9)),
    }


def greedy_fill(needed: float, category_means: dict, pct: float = 0.20) -> list:
    """#67: 20% cuts from the largest leaky category down until sum >= needed."""
    cuts, total = [], 0.0
    for c, m in sorted(category_means.items(), key=lambda kv: -kv[1]):
        if total >= needed or m <= 0:
            break
        saving = pct * m
        cuts.append({"category": c, "cut_pct": pct, "monthly_saving": saving})
        total += saving
    return cuts


def proportional_split(amount: float, weights: dict) -> dict:
    """a_g = A * w_g / sum w (#69)."""
    total = sum(weights.values())
    if not total:
        return {k: 0.0 for k in weights}
    return {k: amount * w / total for k, w in weights.items()}
