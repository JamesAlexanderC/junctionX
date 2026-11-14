"""Only the insights the customer's real data supports (GET /api/insights/).

Each insight is {key, inference, title, value, unit, text, section}. An
insight is left out when its inference found nothing, is None or zero, or is
not supported by the S-Bank data (no loans, subscriptions, fees, ATM,
gambling or second accounts). ``profile["availability"]`` from the inference
engine is respected when present; every builder also checks its own numbers.
``text`` is built only from the numbers in the profile.
"""

from datetime import date

BASKET_NAMES = {
    "essential": "Essentials",
    "surprise": "Surprises",
    "leaky": "Leaky",
    "saver": "Saver",
    "other": "Other",
}
SEVERITY_ORDER = {"red": 0, "amber": 1, "blue": 2}


def _available(profile, key):
    """The inference engine's availability flag (inferences/availability.py).

    Profiles always carry the flags; without them (hand-made test profiles)
    the builders' own None / zero checks decide.
    """
    if not profile.get("availability"):
        return True
    from inferences.availability import available

    return available(profile, key)


def _eur(value):
    value = float(value)
    if abs(value) >= 100:
        return f"EUR {value:,.0f}"
    return f"EUR {value:,.2f}"


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _item(key, inference, title, value, unit, text, section):
    return {
        "key": key,
        "inference": inference,
        "title": title,
        "value": value,
        "unit": unit,
        "text": text,
        "section": section,
    }


def _nice_date(raw):
    try:
        d = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return str(raw)
    return f"{d.day} {d.strftime('%b %Y')}"


# --- builders, one per insight ---------------------------------------------


def safe_to_spend(p):
    fc = p.get("forecast") or {}
    value = fc.get("safe_to_spend_week")
    if not _available(p, "forecast.safe_to_spend_week") or not _num(value):
        return []
    payday = (p.get("income") or {}).get("payday") or {}
    text = f"You can spend about {_eur(value)} this week"
    if payday.get("found") and payday.get("next_payday"):
        text += f" before payday on {_nice_date(payday['next_payday'])}"
    text += ", after bills due before payday"
    if _num(fc.get("buffer")):
        text += f" and a {_eur(fc['buffer'])} buffer"
    text += "."
    return [
        _item(
            "safe_to_spend",
            17,
            "Safe to spend this week",
            value,
            "EUR",
            text,
            "forecast",
        )
    ]


def payday(p):
    pay = (p.get("income") or {}).get("payday") or {}
    if not _available(p, "income.payday") or not pay.get("found"):
        return []
    if not pay.get("next_payday"):
        return []
    text = f"Your salary usually arrives on day {pay.get('day_of_month')}"
    if _num(pay.get("amount")):
        text += f" (about {_eur(pay['amount'])})"
    text += f". Next payday: {_nice_date(pay['next_payday'])}"
    if _num(pay.get("days_to_payday")):
        text += f", in {pay['days_to_payday']} days"
    return [
        _item(
            "payday", 1, "Next payday", pay["next_payday"], "date", text + ".", "income"
        )
    ]


def income(p):
    inc = p.get("income") or {}
    value = inc.get("monthly_income")
    if not _available(p, "income.monthly_income") or not _num(value) or value <= 0:
        return []
    text = f"Your typical monthly income is {_eur(value)}"
    stab = inc.get("stability") or {}
    if _available(p, "income.stability") and stab.get("label"):
        text += f", and it is {stab['label'].lower()}"
        if _num(stab.get("cv")):
            text += f" (varies {stab['cv'] * 100:.0f}% month to month)"
    return [
        _item("monthly_income", 2, "Monthly income", value, "EUR", text + ".", "income")
    ]


def _basket_month(p):
    """The latest month with spending: this month, else the last full month."""
    b = p.get("baskets") or {}
    if any((b.get("totals") or {}).values()):
        return b.get("month"), b["totals"]
    for entry in reversed(b.get("history") or []):
        if any((entry.get("totals") or {}).values()):
            return entry.get("month"), entry["totals"]
    return None, {}


def baskets(p):
    month, totals = _basket_month(p)
    total = sum(v for v in totals.values() if _num(v))
    if not month or total <= 0:
        return []
    shares = {
        k: round(v / total * 100, 1) for k, v in totals.items() if _num(v) and v > 0
    }
    parts = [
        f"{BASKET_NAMES.get(k, k)} {s:.0f}%"
        for k, s in sorted(shares.items(), key=lambda kv: -kv[1])
    ]
    text = f"In {month} you spent {_eur(total)}: " + ", ".join(parts) + "."
    value = {k: round(v, 2) for k, v in totals.items() if _num(v) and v > 0}
    return [
        _item(
            "baskets",
            10,
            f"Where the money went ({month})",
            value,
            "EUR",
            text,
            "baskets",
        )
    ]


def saver(p):
    b = p.get("baskets") or {}
    value = b.get("monthly_saving")
    if not _available(p, "baskets.saver") or not _num(value) or value <= 0:
        return []
    text = f"You move about {_eur(value)} a month into savings or investments."
    inc = (p.get("income") or {}).get("monthly_income")
    if _num(inc) and inc > 0:
        text = text[:-1] + f", {value / inc * 100:.0f}% of your income."
    return [_item("saver", 75, "Monthly saving", value, "EUR", text, "baskets")]


def leaky(p):
    rows = [
        r
        for r in (p.get("baskets") or {}).get("leaky_categories") or []
        if _num(r.get("monthly_total")) and r["monthly_total"] > 0
    ][:3]
    if not rows:
        return []
    parts = [f"{r['category']} {_eur(r['monthly_total'])}" for r in rows]
    text = "Small everyday purchases that add up each month: " + ", ".join(parts) + "."
    value = {r["category"]: r["monthly_total"] for r in rows}
    return [_item("leaky", 9, "Leaky spending", value, "EUR", text, "baskets")]


def spender_type(p):
    st = (p.get("habits") or {}).get("spender_type") or {}
    if not _available(p, "habits.spender_type") or not st.get("label"):
        return []
    return [
        _item(
            "spender_type",
            16,
            "Spender type",
            st["label"],
            None,
            f"Your spending pattern: {st['label']}.",
            "habits",
        )
    ]


HABIT_FLAGS = {
    "weekend": (11, "Weekend spender", "{pct}% of your spending is on weekends."),
    "night": (12, "Night spending", "{pct}% of your spending is late at night."),
    "impulse": (13, "Impulse bursts", "{n} bursts of quick purchases a month."),
    "payday_splurge": (
        14,
        "Payday splurge",
        "You spend {x}x more a day in the 3 days after payday.",
    ),
}


def habits(p):
    h = p.get("habits") or {}
    out = []
    for key, (inference, title, template) in HABIT_FLAGS.items():
        entry = h.get(key) or {}
        if not entry.get("flag") or not _available(p, f"habits.{key}"):
            continue
        text = template.format(
            pct=round((entry.get("share") or 0) * 100),
            n=entry.get("bursts_per_month"),
            x=entry.get("ratio"),
        )
        value = entry.get("share", entry.get("bursts_per_month", entry.get("ratio")))
        out.append(_item(f"habit_{key}", inference, title, value, None, text, "habits"))
    return out


def end_of_month(p):
    eom = (p.get("forecast") or {}).get("end_of_month") or {}
    if not _available(p, "forecast.end_of_month") or not _num(eom.get("expected")):
        return []
    low, high = eom.get("low"), eom.get("high")
    if _num(low) and _num(high) and low == high:
        return []  # no days left this month: nothing to forecast
    when = f"on {_nice_date(eom['date'])}" if eom.get("date") else "at month end"
    text = f"Expected balance {when}: {_eur(eom['expected'])}"
    if _num(low) and _num(high):
        text += f" (likely between {_eur(low)} and {_eur(high)})"
    return [
        _item(
            "end_of_month",
            19,
            "End-of-month balance",
            eom["expected"],
            "EUR",
            text + ".",
            "forecast",
        )
    ]


def danger_days(p):
    days = (p.get("forecast") or {}).get("danger_days") or []
    if not days or not _available(p, "forecast.danger_days"):
        return []
    first = days[0].get("date") if isinstance(days[0], dict) else days[0]
    text = (
        f"Your balance could drop below EUR 50 on {len(days)} day(s) before "
        f"payday, first on {_nice_date(first)}."
    )
    return [
        _item("danger_days", 20, "Danger days", len(days), "days", text, "forecast")
    ]


def upcoming_bills(p):
    bills = (p.get("forecast") or {}).get("upcoming_bills") or []
    bills = [b for b in bills if _num(b.get("amount")) and b["amount"] > 0]
    if not bills or not _available(p, "forecast.upcoming_bills"):
        return []
    parts = [
        f"{b.get('name') or 'bill'} {_eur(b['amount'])} on {_nice_date(b['date'])}"
        for b in bills[:3]
    ]
    total = round(sum(b["amount"] for b in bills), 2)
    text = "Regular bills in the next 30 days: " + ", ".join(parts) + "."
    return [
        _item("upcoming_bills", 21, "Upcoming bills", total, "EUR", text, "forecast")
    ]


def surprise_fund(p):
    value = (p.get("forecast") or {}).get("surprise_fund_monthly")
    if not _available(p, "forecast.surprise_fund") or not _num(value) or value <= 0:
        return []
    text = (
        f"Unexpected must-pay costs average {_eur(value)} a month over the last "
        "year; setting that aside covers them."
    )
    return [_item("surprise_fund", 22, "Surprise fund", value, "EUR", text, "forecast")]


def seasonal(p):
    s = (p.get("forecast") or {}).get("seasonal") or {}
    if not s.get("warn") or not _available(p, "forecast.seasonal"):
        return []
    text = (
        f"Last year {s.get('next_month')} cost {s.get('ratio')}x a usual month. "
        f"A pot of {_eur(s.get('pot') or 0)} would cover the extra."
    )
    return [
        _item(
            "seasonal",
            23,
            "Expensive month ahead",
            s.get("pot"),
            "EUR",
            text,
            "forecast",
        )
    ]


def level(p):
    lv = p.get("levels") or {}
    if not _available(p, "levels") or lv.get("current") is None:
        return []
    text = f"You are at level {lv['current']}: {lv.get('current_name')}."
    if lv.get("next"):
        text += f" Next: {lv.get('next_name')}"
        if _num(lv.get("progress")) and lv["progress"] > 0:
            text += f" ({lv['progress'] * 100:.0f}% there)"
        if _num(lv.get("euros_to_go")) and lv["euros_to_go"] > 0:
            text += f", {_eur(lv['euros_to_go'])} to go"
        text += "."
    step = lv.get("easiest_next_step") or {}
    if _available(p, "levels.easiest_next_step") and step.get("text"):
        text += f" Easiest next step: {step['text']}."
    return [_item("level", 30, "Level", lv["current"], None, text, "levels")]


def detected_goals(p):
    if not _available(p, "goals.detected"):
        return []
    out = []
    for g in (p.get("goals") or {}).get("detected") or []:
        if not g.get("text"):
            continue
        amount = g.get("monthly_amount")
        text = g["text"]
        if _num(amount) and amount > 0:
            text += f" (about {_eur(amount)} a month)"
        out.append(
            _item(
                f"goal_{g.get('id')}",
                g.get("inference"),
                "Goal idea",
                amount,
                "EUR",
                text,
                "goals",
            )
        )
    return out


def active_goals(p):
    out = []
    for g in (p.get("goals") or {}).get("active") or []:
        if not _num(g.get("progress_pct")):
            continue
        state = "on track" if g.get("on_track") else "behind"
        text = (
            f"{g.get('name')}: {g['progress_pct']:.0f}% of {_eur(g.get('target', 0))}"
            f", {state}."
        )
        out.append(
            _item(
                f"goal_{g.get('id')}",
                51,
                g.get("name") or "Goal",
                g["progress_pct"],
                "%",
                text,
                "goals",
            )
        )
    return out


def alerts(p):
    out = []
    rows = sorted(
        p.get("alerts") or [],
        key=lambda a: (
            SEVERITY_ORDER.get(a.get("severity"), 3),
            -(a.get("priority") or 0),
        ),
    )
    for a in rows:
        out.append(
            {
                **_item(
                    a["id"],
                    a.get("inference"),
                    a.get("title") or "Alert",
                    a.get("trigger_values"),
                    None,
                    a.get("text") or "",
                    "alerts",
                ),
                "severity": a.get("severity"),
            }
        )
    return out


def benchmarks(p):
    b = p.get("benchmarks") or {}
    out = []
    for kind, inference, who in (
        ("age", 36, "your age group"),
        ("area", 37, "your area"),
    ):
        if not _available(p, f"benchmarks.{kind}"):
            continue
        flagged = [r for r in b.get(kind) or [] if r.get("flag")]
        if not flagged:
            continue
        parts = [
            f"{r['category']} {_eur(r['user'])} vs {_eur(r['peer_median'])} "
            f"({'above' if r['flag'] == 'above' else 'below'})"
            for r in flagged[:3]
        ]
        text = f"Compared with {who} (monthly median): " + "; ".join(parts) + "."
        value = {r["category"]: r.get("ratio") for r in flagged[:3]}
        out.append(
            _item(
                f"benchmark_{kind}",
                inference,
                f"You vs {who}",
                value,
                "ratio",
                text,
                "benchmarks",
            )
        )
    return out


def mortgage_readiness(p):
    r = (p.get("mortgage") or {}).get("readiness") or {}
    if not _available(p, "mortgage.readiness") or not _num(r.get("score")):
        return []
    text = (
        f"Mortgage readiness {r['score'] * 100:.0f}% compared with approved "
        "S-Bank applicants"
    )
    gaps = [g.get("feature", "").replace("_", " ") for g in r.get("gaps") or []]
    if gaps:
        text += f"; biggest gaps: {', '.join(gaps[:2])}"
    text += ". Guidance only, not a loan decision."
    return [
        _item(
            "mortgage_readiness",
            35,
            "Mortgage readiness",
            r["score"],
            "score",
            text,
            "mortgage",
        )
    ]


BUILDERS = [
    alerts,
    safe_to_spend,
    payday,
    income,
    saver,
    baskets,
    leaky,
    upcoming_bills,
    end_of_month,
    danger_days,
    surprise_fund,
    seasonal,
    level,
    active_goals,
    detected_goals,
    spender_type,
    habits,
    benchmarks,
    mortgage_readiness,
]


def insights(profile):
    """Flat list of supported insights, most urgent (alerts) first."""
    out = []
    for build in BUILDERS:
        out.extend(build(profile or {}))
    return out
