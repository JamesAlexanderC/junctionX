"""Alert coach planner (context.md "Alert coach", P2.7).

Greedy weighted set cover: each candidate action is applied to a copy of the
profile, every alert rule is re-run on the simulated profile, and the alerts
that turn off are the set the action clears. Score = priority cleared / effort.
"""

import copy
from datetime import date, timedelta

from . import services

MAX_STEPS = 3
CUT_EFFORT = {0.1: 1, 0.2: 2, 0.3: 3}
DANGER_EUR = 50.0
TIGHT_DAYS = 20  # alert inference number: balance may drop low (#20)
NOTHING_TO_CHANGE = (
    "There is nothing the coach can change for this: no everyday spending to "
    "cut, no subscription to drop, no goal to pause and no savings to move."
)
GENERAL_OPTIONS = ["Snooze it if it looks fine", "Talk to an S-Bank advisor"]


def default_alert_runner(df, profile, today):
    from inferences.alerts import run_all_alerts

    return run_all_alerts(df, profile, today)


# --- candidate actions ---------------------------------------------------


def _leaky_categories(profile):
    means = profile.get("whatif", {}).get("category_means", {})
    cats = profile.get("baskets", {}).get("leaky_categories", [])
    out = {}
    for c in cats:
        out[c["category"]] = float(means.get(c["category"], c["monthly_total"]))
    return out


def _flagged_subscriptions(profile, alerts):
    subs = profile.get("income", {}).get("subscriptions", [])
    by_id = {s["merchant_id"]: s for s in subs}
    flagged = {}
    for s in profile.get("income", {}).get("possibly_unused", []):
        if s["merchant_id"] in by_id:
            flagged[s["merchant_id"]] = by_id[s["merchant_id"]]
    by_mcc = {}
    for s in subs:
        by_mcc.setdefault(s.get("mcc_code"), []).append(s)
    for group in by_mcc.values():
        if len(group) >= 2:
            for s in group:
                flagged[s["merchant_id"]] = s
    return list(flagged.values())


def candidate_actions(profile, alerts):
    """Build actions from the data; Saver-to-buffer only with a red alert."""
    actions = []
    for cat, mean in _leaky_categories(profile).items():
        for pct, effort in CUT_EFFORT.items():
            actions.append(
                {
                    "type": "cut_category",
                    "category": cat,
                    "pct": pct,
                    "effort": effort,
                    "monthly_impact": round(pct * mean, 2),
                    "text": f"Cut {cat} by {int(pct * 100)}%",
                }
            )
    for s in _flagged_subscriptions(profile, alerts):
        gap = float(s.get("median_gap_days") or 30.44)
        monthly = float(s["amount"]) * 30.44 / gap
        actions.append(
            {
                "type": "cancel_subscription",
                "merchant_id": s["merchant_id"],
                "effort": 1,
                "monthly_impact": round(monthly, 2),
                "text": f"Cancel {s.get('name', s['merchant_id'])}",
            }
        )
    for g in profile.get("goals", {}).get("active", []):
        if g.get("paused"):
            continue
        monthly = float(g.get("monthly_needed") or 0)
        actions.append(
            {
                "type": "pause_goal",
                "goal_id": g["id"],
                "effort": 2,
                "monthly_impact": round(monthly, 2),
                "text": f"Pause the goal '{g['name']}'",
            }
        )
        actions.append(
            {
                "type": "resize_goal",
                "goal_id": g["id"],
                "factor": 0.5,
                "effort": 2,
                "monthly_impact": round(monthly / 2, 2),
                "text": f"Halve the monthly amount for '{g['name']}'",
            }
        )
    if any(a.get("severity") == "red" for a in alerts):
        saver = float(profile.get("baskets", {}).get("monthly_saving") or 0)
        if saver > 0:
            actions.append(
                {
                    "type": "move_saver_to_buffer",
                    "amount": saver,
                    "effort": 2,
                    "monthly_impact": round(saver, 2),
                    "text": f"Move EUR {saver:.0f} from savings to your buffer",
                }
            )
    return actions


# --- what-if engine --------------------------------------------------------


def _free_money(p, monthly):
    """Spread a monthly saving over the forecast numbers."""
    fc = p.setdefault("forecast", {})
    days_to_payday = p.get("income", {}).get("payday", {}).get("days_to_payday")
    days = days_to_payday or 30
    daily = monthly / 30.44
    if "safe_to_spend_week" in fc:
        fc["safe_to_spend_week"] = round(fc["safe_to_spend_week"] + daily * 7, 2)
    if "safe_to_save_today" in fc:
        fc["safe_to_save_today"] = round(fc["safe_to_save_today"] + daily * days, 2)
    eom = fc.get("end_of_month")
    if eom:
        for k in ("expected", "low", "high"):
            if k in eom:
                eom[k] = round(eom[k] + daily * days, 2)
    path = fc.get("daily_path") or []
    for t, day in enumerate(path, start=1):
        for k in ("expected", "low", "high"):
            if k in day:
                day[k] = round(day[k] + daily * t, 2)
    if path:
        fc["danger_days"] = [d["date"] for d in path if d.get("low", 1e9) < DANGER_EUR]
    # Extra saving speeds goals up (#26, #52).
    for g in p.get("goals", {}).get("active", []):
        g["extra_monthly"] = round(g.get("extra_monthly", 0) + monthly, 2)


def apply_action(profile, action):
    """Return a simulated copy of ``profile`` with ``action`` applied."""
    p = copy.deepcopy(profile)
    kind = action["type"]
    p.setdefault("simulated_actions", []).append(action)
    baskets = p.setdefault("baskets", {})
    totals = baskets.setdefault("totals", {})
    if kind == "cut_category":
        cat, pct = action["category"], action["pct"]
        saving = action["monthly_impact"]
        means = p.setdefault("whatif", {}).setdefault("category_means", {})
        if cat in means:
            means[cat] = round(means[cat] * (1 - pct), 2)
        for c in baskets.get("leaky_categories", []):
            if c["category"] == cat:
                c["monthly_total"] = round(c["monthly_total"] * (1 - pct), 2)
        if "leaky" in totals:
            totals["leaky"] = round(totals["leaky"] - saving, 2)
        _free_money(p, saving)
    elif kind == "cancel_subscription":
        mid = action["merchant_id"]
        inc = p.setdefault("income", {})
        for key in ("subscriptions", "bills", "possibly_unused"):
            inc[key] = [s for s in inc.get(key, []) if s.get("merchant_id") != mid]
        fc = p.get("forecast", {})
        fc["upcoming_bills"] = [
            b for b in fc.get("upcoming_bills", []) if b.get("merchant_id") != mid
        ]
        _free_money(p, action["monthly_impact"])
    elif kind in ("pause_goal", "resize_goal"):
        for g in p.get("goals", {}).get("active", []):
            if g["id"] != action["goal_id"]:
                continue
            if kind == "pause_goal":
                g["paused"] = True
                g["on_track"] = True
                g["monthly_needed"] = 0
            else:
                g["monthly_needed"] = round(
                    (g.get("monthly_needed") or 0) * action["factor"], 2
                )
                g["resized"] = True
        clash = p.get("goals", {}).get("clash")
        if clash:
            total = sum(
                g.get("monthly_needed") or 0 for g in p["goals"].get("active", [])
            )
            clash["total_needed"] = total
            safe = clash.get("safe_to_save_monthly")
            clash["clash"] = safe is not None and total > safe
    elif kind == "move_saver_to_buffer":
        amount = action["amount"]
        p["balance"] = round(float(p.get("balance") or 0) + amount, 2)
        if "saver" in totals:
            totals["saver"] = round(totals["saver"] - amount, 2)
        lv = p.get("levels", {})
        essentials = float(baskets.get("monthly_essentials") or 0)
        if essentials and "buffer_months" in lv:
            lv["buffer_months"] = round(lv["buffer_months"] + amount / essentials, 2)
        fc = p.setdefault("forecast", {})
        for day in fc.get("daily_path") or []:
            for k in ("expected", "low", "high"):
                if k in day:
                    day[k] = round(day[k] + amount, 2)
        if fc.get("daily_path"):
            fc["danger_days"] = [
                d["date"] for d in fc["daily_path"] if d.get("low", 1e9) < DANGER_EUR
            ]
        if "safe_to_spend_week" in fc:
            fc["safe_to_spend_week"] = round(fc["safe_to_spend_week"] + amount, 2)
    else:
        raise ValueError(f"Unknown action type: {kind}")
    return p


def apply_actions(profile, actions):
    for a in actions:
        profile = apply_action(profile, a)
    return profile


# --- planner ---------------------------------------------------------------


def _with_priority(alerts, on):
    out = []
    for a in alerts:
        a = dict(a)
        if a.get("priority") is None:
            a["priority"] = services.alert_priority(a, on)
        out.append(a)
    return out


def _same_target(a, b):
    keys = ("category", "merchant_id", "goal_id")
    return a["type"] == b["type"] and all(a.get(k) == b.get(k) for k in keys)


def suggest_fixes(
    profile, open_alerts, df=None, run_alerts=None, today=None, max_steps=MAX_STEPS
):
    """Greedy plan of at most ``max_steps`` actions with what each clears."""
    run_alerts = run_alerts or default_alert_runner
    today = today or services.profile_today(profile)
    df = df if df is not None else services.empty_df()
    open_alerts = _with_priority(open_alerts, today)
    priority = {a["id"]: a["priority"] for a in open_alerts}
    remaining = set(priority)
    current = profile
    steps = []
    candidates = candidate_actions(profile, open_alerts)
    while remaining and len(steps) < max_steps:
        best = None
        for action in candidates:
            if any(_same_target(action, s["action"]) for s in steps):
                continue
            sim = apply_action(current, action)
            still = {a["id"] for a in run_alerts(df, sim, today)}
            cleared = remaining - still
            if not cleared:
                continue
            score = sum(priority[i] for i in cleared) / action["effort"]
            key = (score, action["monthly_impact"])
            if best is None or key > best[0]:
                best = (key, action, cleared, sim)
        if best is None:
            break
        (score, _), action, cleared, sim = best
        steps.append(
            {
                "action": action,
                "text": action["text"],
                "monthly_impact": action["monthly_impact"],
                "effort": action["effort"],
                "score": round(score, 4),
                "clears": sorted(cleared),
            }
        )
        remaining -= cleared
        current = sim
    by_id = {a["id"]: a for a in open_alerts}
    unclearable = [
        explain_unclearable(profile, by_id[i], candidates) for i in sorted(remaining)
    ]
    return {
        "steps": steps,
        "still_open": sorted(remaining),
        "unclearable": unclearable,
    }


# --- F4: why an alert cannot be cleared ------------------------------------------


def _bills_until(profile, impact_date):
    """Upcoming bills due on or before the alert's impact date."""
    if not impact_date:
        return []
    cutoff = str(impact_date)[:10]
    bills = profile.get("forecast", {}).get("upcoming_bills") or []
    return [b for b in bills if str(b.get("date", ""))[:10] <= cutoff]


def explain_unclearable(profile, alert, candidates):
    """Why none of the candidate actions clears ``alert``, from the data,
    with what the user can do instead (never the fallback; F4)."""
    if candidates:
        # #24: plain words; no planner internals like "none of the 9 changes".
        biggest = max(c["monthly_impact"] for c in candidates)
        why = (
            "Nothing the coach can suggest (cutting everyday spending, dropping a "
            "subscription, pausing a goal or moving savings) clears this; the "
            f"most any of them saves is EUR {biggest:,.2f} a month."
        )
    else:
        why = NOTHING_TO_CHANGE
    options = list(GENERAL_OPTIONS)
    bills = _bills_until(profile, alert.get("impact_date"))
    if alert.get("inference") == TIGHT_DAYS and bills:
        bill = max(bills, key=lambda b: b["amount"])
        lead = f"{bill['name']} of EUR {bill['amount']:,.2f} is due on {bill['date']}"
        if profile.get("balance") is not None:
            lead += f", against a balance of EUR {profile['balance']:,.2f}"
        why = f"{lead}. {why}"
        options = [
            f"Keep money aside for the {bill['name']} bill",
            "Ask whether the due date can move",
            "Talk to an S-Bank advisor",
        ]
    return {
        "id": alert["id"],
        "title": alert.get("title"),
        "why": why,
        "options": options,
    }


def _goal_date(profile, on):
    goals = profile.get("goals", {}).get("active", [])
    if not goals:
        return None
    g = goals[0]
    rate = float(profile.get("baskets", {}).get("monthly_saving") or 0)
    rate += float(g.get("extra_monthly") or 0)
    remaining = float(g["target"]) - float(g["saved"])
    if rate <= 0:
        return None
    months = -(-remaining // rate)
    return (on + timedelta(days=int(months * 30.44))).isoformat()


def _snapshot(profile, on):
    return {
        "safe_to_spend": profile.get("forecast", {}).get("safe_to_spend_week"),
        "buffer_months": profile.get("levels", {}).get("buffer_months"),
        "goal_date": _goal_date(profile, on),
    }


def simulate_plan(profile, actions, open_alerts, df=None, run_alerts=None, today=None):
    """Before/after numbers and the alerts still open after ``actions``."""
    run_alerts = run_alerts or default_alert_runner
    today = today or services.profile_today(profile)
    df = df if df is not None else services.empty_df()
    sim = apply_actions(profile, actions)
    open_ids = {a["id"] for a in open_alerts}
    after_ids = {a["id"] for a in run_alerts(df, sim, today)}
    return {
        "before": _snapshot(profile, today),
        "after": _snapshot(sim, today),
        "cleared": sorted(open_ids - after_ids),
        "still_open": sorted(open_ids & after_ids),
    }


def as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))
