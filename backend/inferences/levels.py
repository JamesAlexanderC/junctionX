"""Levels (context.md #28 to #33).

The current level is the highest level reached with every level below it
reached too; level 0 means not even "Getting started" yet.
"""

from __future__ import annotations

import pandas as pd

from . import models
from . import thresholds as th
from .common import (
    days_in_month,
    full_months,
    income_inflows,
    lowest_balance,
    month_key,
    monthly_totals,
    prepare,
    r2,
    safe_div,
    spend,
    to_date,
)


def _level_2(df, today, income_monthly):
    """#29: income - total spend >= 0 for the last full month. Progress = days
    of this month with spend on track (cumulative spend <= income pro rata) /
    days in the month."""
    months = full_months(today, 1, df)
    s = spend(df)
    inc = income_inflows(df)
    reached = False
    gap = None
    last = None
    if months:
        m = months[-1]
        spent = monthly_totals(s, [m])[m]
        earned = monthly_totals(inc, [m], col="tx_amount_eur")[m]
        # Needs income in that month: no data is not "in control".
        reached = earned > 0 and earned - spent >= 0
        gap = max(0.0, spent - earned) if earned > 0 else None
        last = {"month": m, "spent": r2(spent), "earned": r2(earned)}
    current = month_key(today)
    dim = days_in_month(current)
    cur = s[s["month"] == current]
    daily = cur.groupby(cur["tx_date"].dt.day)["amount"].sum()
    on_track, cum = 0, 0.0
    for day in range(1, to_date(today).day + 1):
        cum += float(daily.get(day, 0.0))
        if cum <= (income_monthly or 0.0) * day / dim:
            on_track += 1
    return reached, on_track / dim, gap, last


def _wealth_saver_months(df, today, baskets, income_monthly):
    """Level 6 part: of the last 3 full months, how many had Saver >= 10% of
    income. Returns (months ok, months needed)."""
    hist = {h["month"]: h["totals"] for h in baskets.get("history", [])}
    months = full_months(today, th.WEALTH_SAVER_MONTHS, df)
    if len(months) < th.WEALTH_SAVER_MONTHS or not income_monthly:
        return 0, th.WEALTH_SAVER_MONTHS
    ok = sum(
        hist.get(m, {}).get("saver", 0.0) >= th.WEALTH_SAVER_SHARE * income_monthly
        for m in months
    )
    return ok, th.WEALTH_SAVER_MONTHS


def _eur(v):
    return f"EUR {v:,.0f}"


def _requirement(lv, f):
    """What level ``lv`` needs (#28 to #32, level 6) and which parts are met.

    f: the facts compute_levels measured. Returns {text, checks: [{text,
    met}]}; every number in it is the customer's own.
    """
    if lv == 1:  # #28
        bills = (
            {"text": "Bills are paid from another bank", "met": True}
            if f.get("partial_view") and not f["bills"]
            else {"text": "A regular bill found", "met": f["bills"]}
        )
        return {
            "text": "Get your salary paid into this account and have at least "
            "one regular bill paid from it.",
            "checks": [{"text": "Payday found", "met": f["payday"]}, bills],
        }
    if lv == 2:  # #29
        last = f["last_month"]
        if last is None:
            check = {"text": "Needs one full month of data", "met": False}
        elif last["earned"] <= 0:
            check = {"text": f"No income found in {last['month']}", "met": False}
        else:
            check = {
                "text": f"In {last['month']} you spent {_eur(last['spent'])} and "
                f"earned {_eur(last['earned'])}",
                "met": last["earned"] >= last["spent"],
            }
        return {
            "text": "Spend no more than you earn in a full month.",
            "checks": [check],
        }
    if lv == 3:  # #30
        need = f["essentials"] * th.SAFETY_NET_MONTHS
        return {
            "text": f"Keep at least {th.SAFETY_NET_MONTHS:g} month of essential "
            "spending in the account, even at its lowest point.",
            "checks": [
                {
                    "text": f"Lowest balance in the last 30 days: {_eur(f['low'])} "
                    f"of {_eur(need)} needed",
                    "met": f["l3"],
                }
            ],
        }
    if lv == 4:  # #31
        n, ok = f["goals_active"], f["goals_on_track"]
        text = (
            "No active goal yet"
            if not n
            else f"{n} active goal{'s' if n != 1 else ''}, {ok} on track"
        )
        return {
            "text": "Have an active goal that is on track.",
            "checks": [{"text": text, "met": ok > 0}],
        }
    if lv == 5:  # #32
        r = f["readiness"]
        text = "No readiness score yet" if r is None else f"Your score: {r * 100:.0f}%"
        return {
            "text": f"Reach a mortgage readiness score of "
            f"{th.MORTGAGE_READY_SCORE * 100:.0f}% or more.",
            "checks": [{"text": text, "met": f["l5"]}],
        }
    ok, need = f["saver_months"]
    return {
        "text": f"Keep {th.WEALTH_BUFFER_MONTHS:g} months of essentials as a "
        f"buffer and save {th.WEALTH_SAVER_SHARE * 100:.0f}% of income for "
        f"{th.WEALTH_SAVER_MONTHS} months in a row.",
        "checks": [
            {
                "text": f"Buffer: {f['buffer_months']:.1f} of "
                f"{th.WEALTH_BUFFER_MONTHS:g} months",
                "met": f["buffer_months"] >= th.WEALTH_BUFFER_MONTHS,
            },
            {
                "text": f"Saved {th.WEALTH_SAVER_SHARE * 100:.0f}% of income in "
                f"{ok} of the last {need} months",
                "met": ok >= need,
            },
        ],
    }


def compute_levels(
    df: pd.DataFrame,
    today,
    income: dict,
    baskets: dict,
    goals: list[dict] | None = None,
    readiness: float | None = None,
    extra_liquid: float = 0.0,
) -> dict:
    """profile["levels"] (#28 to #33).

    goals: active goal dicts with `on_track` and `paused` (#31, from #52).
    readiness: mortgage readiness score 0..1 (#32, from #35).
    extra_liquid: current and savings balances at linked banks (#113).
    """
    df = prepare(df, today)
    income_monthly = income.get("monthly_income") or 0.0
    essentials = baskets.get("monthly_essentials") or 0.0
    low = lowest_balance(df, today) if len(df) else 0.0
    low = (low or 0.0) + extra_liquid  # #113: buffer across all banks

    # #28 Level 1: payday and at least one regular bill detected. On a partial
    # view the bills are paid from another bank, so a payday alone counts.
    payday = bool(income.get("payday", {}).get("found"))
    bills = bool(income.get("bills"))
    partial_view = bool(income.get("partial_view"))
    l1 = payday and (bills or partial_view)
    # #29 Level 2.
    l2, l2_progress, l2_gap, last_month = _level_2(df, today, income_monthly)
    # #30 Level 3: buffer months = lowest balance (30 days) / monthly essentials.
    buffer_months = safe_div(low, essentials, default=0.0)
    l3 = buffer_months >= th.SAFETY_NET_MONTHS
    # #31 Level 4: an active goal that is on track.
    live = [g for g in goals or [] if not g.get("paused")]
    l4 = any(g.get("on_track") for g in live)
    # #32 Level 5: readiness >= 0.75.
    l5 = readiness is not None and readiness >= th.MORTGAGE_READY_SCORE
    # Level 6: buffer >= 3 months and Saver >= 10% of income 3 months running.
    saver_months = _wealth_saver_months(df, today, baskets, income_monthly)
    l6 = buffer_months >= th.WEALTH_BUFFER_MONTHS and saver_months[0] >= saver_months[1]
    reached = {1: l1, 2: l2, 3: l3, 4: l4, 5: l5, 6: l6}
    progress = {
        1: 1.0 if l1 else 0.0,
        2: 1.0 if l2 else l2_progress,
        3: min(1.0, buffer_months / th.SAFETY_NET_MONTHS),
        4: 1.0 if l4 else 0.0,
        5: min(1.0, (readiness or 0.0) / th.MORTGAGE_READY_SCORE),
        6: min(1.0, buffer_months / th.WEALTH_BUFFER_MONTHS),
    }
    gaps = {
        1: None,
        2: l2_gap,
        3: max(0.0, essentials * th.SAFETY_NET_MONTHS - low),
        4: None,
        5: None,
        6: max(0.0, essentials * th.WEALTH_BUFFER_MONTHS - low),
    }

    current = 0
    while current < 6 and reached[current + 1]:
        current += 1
    nxt = current + 1 if current < 6 else None
    gap = gaps.get(nxt) if nxt else None

    # #33 Easiest next step over the leaky categories.
    leaky = {
        c["category"]: c["monthly_total"] for c in baskets.get("leaky_categories", [])
    }
    step = models.easiest_cut(gap, leaky) if gap else None
    if step:
        step = {
            "category": step["category"],
            "cut_pct": step["cut_pct"],
            "monthly_saving": r2(step["monthly_saving"]),
            "months": step["months"],
            "text": (
                f"Cut {step['category']} by {round(step['cut_pct'] * 100)}% "
                f"(about EUR {step['monthly_saving']:.0f} a month)"
            ),
        }

    facts = {
        "payday": payday,
        "bills": bills,
        "partial_view": partial_view,
        "last_month": last_month,
        "essentials": essentials,
        "low": low,
        "l3": l3,
        "goals_active": len(live),
        "goals_on_track": sum(1 for g in live if g.get("on_track")),
        "readiness": readiness,
        "l5": l5,
        "buffer_months": buffer_months,
        "saver_months": saver_months,
    }

    ladder = []
    for lv in range(1, 7):
        entry = {"level": lv, "name": th.LEVEL_NAMES[lv], "reached": bool(reached[lv])}
        if not reached[lv]:
            entry["progress"] = r2(progress[lv])
        ladder.append(entry)
    return {
        "current": current,
        "current_name": th.LEVEL_NAMES.get(current, "Not started"),
        "next": nxt,
        "next_name": th.LEVEL_NAMES.get(nxt) if nxt else None,
        "progress": r2(progress[nxt]) if nxt else 1.0,
        "euros_to_go": r2(gap) if gap is not None else None,
        "buffer_months": r2(buffer_months),
        "lowest_balance_30d": r2(low),
        "easiest_next_step": step,
        # What the next level needs and which parts are met (#28 to #32).
        "next_requirement": _requirement(nxt, facts) if nxt else None,
        "ladder": ladder,
    }
