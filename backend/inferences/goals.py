"""Goals (context.md #44 to #74).

Goals come in as plain dicts (as stored by the API), with the fields of
profile_demo.json ``goals.active`` plus ``status`` (active / completed /
abandoned), optional ``paused_at`` and ``created_by_user``. The app never
creates a goal on its own: detected goals (#56 to #62) are suggestions only.

Shared money values:
- r (Saver rate) = baskets.monthly_saving: median monthly Saver (#26, #75).
- safe-to-save per month (#50, #69, #70) = r + forecast.safe_to_save_today,
  i.e. what already goes to savings plus what could safely go this cycle.
"""

from __future__ import annotations

import math

import pandas as pd

from . import models
from . import thresholds as th
from .common import (
    add_months,
    full_months,
    iso,
    month_key,
    prepare,
    r2,
    safe_div,
    spend,
    to_date,
)

GOAL_TYPES = ("spend_less", "safety_net", "surprises", "mortgage", "wealth")


# --- Small helpers


def months_between(start, end) -> float:
    """Months from start to end (days / 30.44), never negative."""
    days = (pd.Timestamp(end) - pd.Timestamp(start)).days
    return max(0.0, days / 30.44)


def safe_to_save_monthly(baskets: dict, forecast: dict) -> float:
    """Average monthly safe-to-save used by #50, #69 and #70 (see module doc)."""
    rate = (baskets or {}).get("monthly_saving") or 0.0
    extra = (forecast or {}).get("safe_to_save_today") or 0.0
    return float(rate) + float(extra)


def _leaky_means(baskets: dict) -> dict:
    return {
        c["category"]: c["monthly_total"]
        for c in (baskets or {}).get("leaky_categories", [])
        if c.get("monthly_total")
    }


def _add_months(today, months: int):
    return iso(pd.Timestamp(to_date(today)) + pd.DateOffset(months=months))


# --- Single goal maths


def difficulty(target, saved, rate) -> dict:
    """#49 via #26: months at the current rate -> Easy / Stretch / Hard."""
    months = models.months_to_goal(target, saved, rate)
    return {"months_needed": months, "difficulty": models.goal_difficulty(months)}


def monthly_needed(target, saved, today, target_date) -> float:
    """#65: (target - saved) / months until the date, rounded up to EUR 5."""
    months_left = math.ceil(round(months_between(today, target_date), 6))
    return models.monthly_needed(target, saved, months_left)


def realism(needed_monthly, target, saved, today, safe_monthly) -> dict:
    """#50 / #66: unrealistic when the monthly need > average safe-to-save.

    Suggests the realistic amount (that average) and the date it implies:
    today + ceil(remaining / realistic monthly) months.
    """
    realistic = needed_monthly <= safe_monthly + 1e-9
    out = {"realistic": bool(realistic)}
    if not realistic:
        remaining = max(0.0, target - saved)
        months = models.months_to_goal(target, saved, safe_monthly)
        out["suggested_monthly"] = r2(safe_monthly)
        out["suggested_date"] = (
            _add_months(today, months) if months is not None else None
        )
        out["remaining"] = r2(remaining)
    return out


def progress(goal: dict, today) -> dict:
    """#51 progress %, #52 expected % and on track, #72 paused never off track."""
    target = float(goal.get("target") or 0.0)
    saved = float(goal.get("saved") or 0.0)
    pct = safe_div(saved, target) * 100
    start = goal.get("start_date") or iso(today)
    end = goal.get("target_date") or iso(today)
    # Pausing freezes the dates: expected progress stops at paused_at.
    as_of = goal.get("paused_at") if goal.get("paused") else today
    expected = models.expected_progress(as_of or today, start, end) * 100
    on = True if goal.get("paused") else models.on_track(pct, expected)
    return {
        "progress_pct": r2(min(pct, 100.0) if target else 0.0),
        "expected_pct": r2(expected),
        "on_track": bool(on),
    }


def coaching_tip(goal_eval: dict, target: float, leaky: dict) -> dict | None:
    """#53: when off track, shortfall = (expected - actual) x target; run #33."""
    if goal_eval.get("on_track"):
        return None
    shortfall = (goal_eval["expected_pct"] - goal_eval["progress_pct"]) / 100 * target
    if shortfall <= 0:
        return None
    cut = models.easiest_cut(shortfall, leaky)
    if not cut:
        return {"shortfall": r2(shortfall), "text": None}
    return {
        "shortfall": r2(shortfall),
        "category": cut["category"],
        "cut_pct": cut["cut_pct"],
        "monthly_saving": r2(cut["monthly_saving"]),
        "months": cut["months"],
        "text": (
            f"Cut {cut['category']} by {round(cut['cut_pct'] * 100)}% to catch up "
            f"(about EUR {cut['monthly_saving']:.0f} a month)"
        ),
    }


def milestones(progress_pct: float, already: list | None) -> dict:
    """#73: celebrate 25, 50, 75 and 100% once each."""
    already = list(already or [])
    crossed = [m for m in th.MILESTONES if progress_pct >= m]
    return {
        "milestones_hit": sorted(set(already) | set(crossed)),
        "new_milestones": [m for m in crossed if m not in already],
    }


def funding_cuts(needed_monthly: float, leaky: dict) -> list[dict]:
    """#67: 20% cuts from the largest leaky category down until >= need."""
    return [
        {
            "category": c["category"],
            "cut_pct": c["cut_pct"],
            "monthly_saving": r2(c["monthly_saving"]),
        }
        for c in models.greedy_fill(needed_monthly, leaky, th.FUNDING_CUT_PCT)
    ]


def counts_towards_level(goal: dict) -> int | None:
    """#71: safety-net goal -> Level 3, any on-track goal -> Level 4."""
    lv = th.GOAL_LEVEL.get(goal.get("type"))
    if lv:
        return lv
    return 4 if goal.get("on_track") else None


def evaluate_goal(goal: dict, today, baskets: dict, forecast: dict) -> dict:
    """One active goal with #26, #49 to #53, #65, #66, #67, #71, #73 filled in."""
    target = float(goal.get("target") or 0.0)
    saved = float(goal.get("saved") or 0.0)
    rate = (baskets or {}).get("monthly_saving") or 0.0
    safe_monthly = safe_to_save_monthly(baskets, forecast)
    leaky = _leaky_means(baskets)
    out = dict(goal)
    out["target"] = r2(target)
    out["saved"] = r2(saved)
    out.setdefault("type", "custom")
    out.setdefault("priority", "medium")
    out["paused"] = bool(goal.get("paused"))
    out.update(progress(goal, today))
    diff = difficulty(target, saved, rate)
    out.update(diff)
    out["projected_date"] = (
        _add_months(today, diff["months_needed"])
        if diff["months_needed"] is not None
        else None
    )
    end = goal.get("target_date")
    need = monthly_needed(target, saved, today, end) if end else 0.0
    out["monthly_needed"] = r2(need)
    out.update(realism(need, target, saved, today, safe_monthly))
    out["tip"] = coaching_tip(out, target, leaky)
    out.update(milestones(out["progress_pct"], goal.get("milestones_hit")))
    out["funding_cuts"] = funding_cuts(need, leaky)
    out["counts_towards_level"] = counts_towards_level(out)
    return out


def evaluate_goals(goals, today, baskets, forecast) -> list[dict]:
    """Every active (not completed or abandoned) goal through evaluate_goal."""
    return [
        evaluate_goal(g, today, baskets, forecast)
        for g in goals or []
        if g.get("status", "active") == "active"
    ]


# --- Ratings and success (#54, #55, #74)


def suggestion_weights(ratings=None, goals=None) -> dict:
    """#54 / #74: w = (ups + 1) / (ups + downs + 2) per goal type.

    ratings: {goal_type: {"up": n, "down": n}} or a list of
    {"goal_type", "rating": "up"|"down"}. Goals the user created themselves
    add +1 up to their type (#74).
    """
    counts: dict[str, dict] = {t: {"up": 0, "down": 0} for t in GOAL_TYPES}
    if isinstance(ratings, dict):
        for t, c in ratings.items():
            counts.setdefault(t, {"up": 0, "down": 0})
            counts[t]["up"] += int(c.get("up", 0))
            counts[t]["down"] += int(c.get("down", 0))
    else:
        for r in ratings or []:
            t = r.get("goal_type")
            counts.setdefault(t, {"up": 0, "down": 0})
            key = "up" if r.get("rating") in ("up", 1, True) else "down"
            counts[t][key] += 1
    for g in goals or []:
        if g.get("created_by_user", g.get("type") == "custom"):
            t = g.get("type") or "custom"
            counts.setdefault(t, {"up": 0, "down": 0})
            counts[t]["up"] += 1
    return {t: r2(models.laplace_weight(c["up"], c["down"])) for t, c in counts.items()}


def success_score(goals) -> float | None:
    """#55: completed / (completed + abandoned); None with no history."""
    done = sum(1 for g in goals or [] if g.get("status") == "completed")
    lost = sum(1 for g in goals or [] if g.get("status") == "abandoned")
    if done + lost == 0:
        return None
    return r2(done / (done + lost))


def _easier(label: str) -> str:
    return {"Hard": "Stretch", "Stretch": "Easy"}.get(label, label)


# --- Recommended goals (#44 to #48)


def recommended_goal(
    levels: dict,
    income: dict,
    baskets: dict,
    forecast: dict,
    mortgage: dict | None = None,
    weights: dict | None = None,
    success: float | None = None,
) -> dict | None:
    """The goal that takes the user from their level to the next one."""
    nxt = (levels or {}).get("next")
    inc = (income or {}).get("monthly_income") or 0.0
    essentials = (baskets or {}).get("monthly_essentials") or 0.0
    rate = (baskets or {}).get("monthly_saving") or 0.0
    leaky = _leaky_means(baskets)
    rec = None
    if nxt == 2:  # #44
        rec = {
            "type": "spend_less",
            "name": "Spend less than you earn for 30 days",
            "target": r2(inc),
            "spending_limit": r2(inc),
            "essentials": r2(essentials),
            "room_left": r2(inc - essentials),
            "monthly_needed": 0.0,
        }
    elif nxt == 3:  # #45
        low = levels.get("lowest_balance_30d") or 0.0
        target = models.round_up(max(0.0, essentials - low), th.SAFETY_NET_ROUND_EUR)
        rec = {"type": "safety_net", "name": "Build a safety net", "target": target}
    elif nxt == 4:  # #46
        monthly = (forecast or {}).get("surprise_fund_monthly") or 0.0
        step = models.easiest_cut(monthly, leaky)
        rec = {
            "type": "surprises",
            "name": "Save for surprises",
            "target": r2(monthly * 12),
            "monthly_needed": r2(models.round_up(monthly)) if monthly else 0.0,
            "funded_by": (
                {
                    "category": step["category"],
                    "cut_pct": step["cut_pct"],
                    "monthly_saving": r2(step["monthly_saving"]),
                }
                if step
                else None
            ),
        }
    elif nxt == 5:  # #47
        gaps = (((mortgage or {}).get("readiness") or {}).get("gaps")) or []
        gap = gaps[0] if gaps else None
        target = 0.0
        if gap and gap["feature"] == "buffer_months":
            target = max(0.0, (gap["approved_median"] - gap["user"]) * essentials)
        rec = {
            "type": "mortgage",
            "name": "Close your mortgage gap",
            "target": r2(models.round_up(target)) if target else 0.0,
            "gap": gap,
        }
    elif nxt == 6:  # #48
        monthly = th.WEALTH_GOAL_INCOME_SHARE * inc
        rec = {
            "type": "wealth",
            "name": "Save 10-15% of income for 3 months in a row",
            "target": r2(monthly * 3),
            "monthly_needed": r2(monthly),
        }
    if rec is None:
        return None
    rec["id"] = f"rec-{rec['type'].replace('_', '-')}"
    rec["for_level"] = nxt
    if "monthly_needed" not in rec:
        safe = safe_to_save_monthly(baskets, forecast)
        months = models.months_to_goal(rec["target"], 0.0, rate) or 1
        rec["monthly_needed"] = r2(
            models.round_up(rec["target"] / max(1, months)) if rec["target"] else 0
        )
        rec["safe_to_save_monthly"] = r2(safe)
    d = difficulty(rec["target"] or 0.0, 0.0, rate)["difficulty"]
    if success is not None and success < th.GOAL_SUCCESS_EASIER_BELOW:
        rec["suggest_easier"] = True  # #55: one difficulty band easier
        d = _easier(d)
    rec["difficulty"] = d
    rec["weight"] = (weights or {}).get(rec["type"], 0.5)
    return rec


# --- Detected goals (#56 to #62): suggestions only


def _detect_saving(cls, today):
    """#56: at least 2 Saver transfers in the last 3 months with CV < 0.3."""
    start = pd.Timestamp(today) - pd.Timedelta(days=th.DETECT_SAVER_DAYS)
    saver = cls[(cls["basket"] == "saver") & (cls["tx_date"] > start)]
    if len(saver) < th.DETECT_SAVER_MIN_TRANSFERS:
        return None
    amounts = saver["amount"].tolist()
    if models.cv(amounts) >= th.DETECT_SAVER_CV_MAX:
        return None
    return {
        "id": "det-56",
        "inference": 56,
        "type": "savings",
        "text": "Looks like you're saving. Name it?",
        "monthly_amount": r2(float(pd.Series(amounts).median())),
        "transfers": len(amounts),
    }


def _detect_purchase(df, cls, today):
    """#57: month-end balance slope > 0 over 3 months while a non-essential
    category fell by more than 20% (last full month vs the one 2 months
    earlier)."""
    months = full_months(today, 3, df)
    if len(months) < 3:
        return None
    ends = df.groupby("month")["balance_after_eur"].last()
    ys = [float(ends.get(m)) for m in months if m in ends.index]
    if len(ys) < 3 or models.linear_slope(ys) <= 0:
        return None
    nonessential = cls[cls["basket"].isin(["leaky", "other"])]
    first = nonessential[nonessential["month"] == months[0]]
    last = nonessential[nonessential["month"] == months[-1]]
    a = first.groupby("category")["amount"].sum()
    b = last.groupby("category")["amount"].sum()
    for cat, before in a.sort_values(ascending=False).items():
        after = float(b.get(cat, 0.0))
        if before > 0 and (before - after) / before > th.DETECT_CATEGORY_DROP:
            return {
                "id": "det-57",
                "inference": 57,
                "type": "purchase",
                "text": "Saving for something?",
                "category": str(cat),
                "drop_pct": r2((before - after) / before * 100),
            }
    return None


def _is_travel_mcc(mcc) -> bool:
    try:
        code = int(str(mcc))
    except ValueError:
        return False
    return any(lo <= code <= hi for lo, hi in th.TRAVEL_MCC_RANGES)


def _detect_travel(s, today):
    """#58: last year's travel spend > EUR 300 -> holiday pot = that amount /
    months until the same season (the month with most travel spend)."""
    start = pd.Timestamp(today) - pd.DateOffset(months=12)
    travel = s[(s["tx_date"] > start) & s["mcc_code"].map(_is_travel_mcc)]
    total = float(travel["amount"].sum()) if len(travel) else 0.0
    if total <= th.TRAVEL_MIN_EUR:
        return None
    peak = travel.groupby(travel["tx_date"].dt.month)["amount"].sum().idxmax()
    months_until = (int(peak) - to_date(today).month) % 12 or 12
    return {
        "id": "det-58",
        "inference": 58,
        "type": "travel",
        "text": "Holiday coming up again? Start a travel pot.",
        "target": r2(total),
        "monthly_amount": r2(total / months_until),
        "months_until": months_until,
    }


def _detect_home(income, customer, mortgage):
    """#59: pays rent, age 25 to 40, readiness > 0.4 -> deposit goal."""
    pays_rent = any(
        str(b.get("category", "")).lower() in ("housing", "rent")
        for b in (income or {}).get("bills", [])
    )
    age = (customer or {}).get("age")
    score = (((mortgage or {}).get("readiness") or {}).get("score")) or 0.0
    if not (pays_rent and age and th.HOME_AGE_MIN <= age <= th.HOME_AGE_MAX):
        return None
    if score <= th.HOME_READINESS_MIN:
        return None
    area = str((customer or {}).get("postal_code") or "")[:2]
    price = th.TYPICAL_HOME_PRICE.get(area, th.TYPICAL_HOME_PRICE_DEFAULT)
    return {
        "id": "det-59",
        "inference": 59,
        "type": "home",
        "text": "Thinking about your own home? Start a deposit goal.",
        "target": r2(th.HOME_DEPOSIT_SHARE * price),
        "typical_price": r2(price),
        "editable": True,
    }


def _detect_debt(income, loans):
    """#60: months saved by paying EUR x more; without a balance show only x."""
    loan_bills = [
        b
        for b in (income or {}).get("bills", [])
        if str(b.get("category", "")).lower() in th.LOAN_CATEGORIES
        or str(b.get("mcc_code", "")) in th.LOAN_MCCS
    ]
    if not loan_bills:
        return None
    bill = max(loan_bills, key=lambda b: b["amount"])
    x = th.DEBT_EXTRA_EUR
    out = {
        "id": "det-60",
        "inference": 60,
        "type": "debt",
        "text": f"Pay EUR {x:.0f} more a month on {bill.get('name')}?",
        "merchant_id": bill.get("merchant_id"),
        "payment": r2(bill["amount"]),
        "extra": x,
        "months_saved": None,
    }
    if loans and loans.get("balance"):
        i = float(loans.get("interest_rate") or 0.0) / 100 / 12
        n0 = models.months_to_payoff(loans["balance"], i, bill["amount"])
        n1 = models.months_to_payoff(loans["balance"], i, bill["amount"] + x)
        if n0 is not None and n1 is not None:
            out["months_saved"] = r2(n0 - n1)
    else:
        out["needs_balance"] = True
    return out


def _detect_seasonal(s, today):
    """#61: December ratio > 1.25 -> pot from September = (ratio - 1) x mean
    monthly spend / 3 per month."""
    year = to_date(today).year
    dec = f"{year - 1}-12"
    months = [add_months(dec, -k) for k in range(11, -1, -1)]
    if not len(s) or month_key(s["tx_date"].min()) > months[0]:
        return None
    by_month = s.groupby("month")["amount"].sum()
    mean = sum(float(by_month.get(m, 0.0)) for m in months) / 12
    ratio = models.seasonal_index(float(by_month.get(dec, 0.0)), mean)
    if ratio is None or ratio <= th.SEASONAL_WARN_RATIO:
        return None
    return {
        "id": "det-61",
        "inference": 61,
        "type": "seasonal",
        "text": "December usually costs more. Start a pot in September?",
        "ratio": r2(ratio),
        "monthly_amount": r2((ratio - 1) * mean / th.SEASONAL_POT_START_MONTHS),
    }


def _detect_life_change(income, today):
    """#62: a new bill in the last 2 months with amount > 10% of income."""
    inc = (income or {}).get("monthly_income") or 0.0
    if not inc:
        return None
    since = pd.Timestamp(today) - pd.Timedelta(days=th.NEW_BILL_DAYS)
    for b in (income or {}).get("bills", []):
        first = b.get("first_date")
        if first is None:
            continue
        if (
            pd.Timestamp(first) >= since
            and b["amount"] > th.NEW_BILL_INCOME_SHARE * inc
        ):
            return {
                "id": "det-62",
                "inference": 62,
                "type": "life_change",
                "text": f"New regular bill: {b.get('name')}. Re-plan your goals?",
                "merchant_id": b.get("merchant_id"),
                "amount": r2(b["amount"]),
            }
    return None


def detected_goals(
    df,
    today,
    income,
    customer=None,
    mortgage=None,
    loans=None,
    dismissed=None,
) -> list[dict]:
    """#56 to #62 as suggestions; ids in `dismissed` are never shown again."""
    from .baskets import classify

    df = prepare(df, today)
    if not len(df):
        return []
    cls = classify(df, today, (income or {}).get("bills"))
    s = spend(df)
    found = [
        _detect_saving(cls, today),
        _detect_purchase(df, cls, today),
        _detect_travel(s, today),
        _detect_home(income, customer, mortgage),
        _detect_debt(income, loans),
        _detect_seasonal(s, today),
        _detect_life_change(income, today),
    ]
    gone = set(dismissed or [])
    return [g for g in found if g and g["id"] not in gone]


# --- Smart default (#68), priority split (#69), clash (#70)


def smart_default_amount(df, today, name: str) -> float | None:
    """#68: "holiday" -> last 12 months' travel spend, etc. None if no match."""
    words = str(name or "").lower()
    kind = next((v for k, v in th.GOAL_KEYWORDS.items() if k in words), None)
    if kind is None:
        return None
    df = prepare(df, today)
    s = spend(df)
    s = s[s["tx_date"] > pd.Timestamp(today) - pd.DateOffset(months=12)]
    if kind == "travel":
        total = s[s["mcc_code"].map(_is_travel_mcc)]["amount"].sum() if len(s) else 0
    else:  # christmas: December spend above the mean month
        by_month = s.groupby(s["tx_date"].dt.month)["amount"].sum()
        total = max(0.0, float(by_month.get(12, 0.0)) - float(by_month.mean() or 0))
    return r2(total) if total else None


def priority_split(goals: list[dict], amount: float) -> list[dict]:
    """#69: split safe-to-save by priority weight (3 / 2 / 1); safety net
    first in the default order."""
    live = [g for g in goals if not g.get("paused")]
    live.sort(key=lambda g: (g.get("type") != "safety_net",))
    weights = {
        str(g.get("id")): th.GOAL_PRIORITY_WEIGHTS.get(g.get("priority"), 2)
        for g in live
    }
    split = models.proportional_split(amount, weights)
    return [
        {
            "goal_id": g.get("id"),
            "name": g.get("name"),
            "amount": r2(split[str(g["id"])]),
        }
        for g in live
    ]


def clash(goals: list[dict], safe_monthly: float) -> dict:
    """#70: warn when the sum of #65 amounts > average monthly safe-to-save."""
    total = sum(g.get("monthly_needed") or 0.0 for g in goals if not g.get("paused"))
    return {
        "clash": bool(total > safe_monthly + 1e-9),
        "total_needed": r2(total),
        "safe_to_save_monthly": r2(safe_monthly),
    }


# --- Section


def compute_goals(
    df,
    today,
    income: dict,
    baskets: dict,
    forecast: dict,
    levels: dict,
    whatif: dict | None = None,
    goals: list[dict] | None = None,
    ratings=None,
    dismissed=None,
    customer: dict | None = None,
    mortgage: dict | None = None,
    loans: dict | None = None,
) -> dict:
    """profile["goals"] (#44 to #74)."""
    active = evaluate_goals(goals, today, baskets, forecast)
    weights = suggestion_weights(ratings, goals)
    success = success_score(goals)
    safe = safe_to_save_monthly(baskets, forecast)
    rec = recommended_goal(
        levels, income, baskets, forecast, mortgage, weights, success
    )
    top = next((g for g in active if not g.get("paused")), None)
    need = top["monthly_needed"] if top else (rec or {}).get("monthly_needed") or 0.0
    return {
        "recommended": rec,
        "active": active,
        "completed": [
            {"id": g.get("id"), "name": g.get("name"), "type": g.get("type")}
            for g in goals or []
            if g.get("status") == "completed"
        ],
        "detected": detected_goals(
            df, today, income, customer, mortgage, loans, dismissed
        ),
        "clash": clash(active, safe),
        "priority_split": priority_split(active, safe),
        "funding_cuts": funding_cuts(need, _leaky_means(baskets)),
        "suggestion_weights": weights,
        "success_score": success,
    }
