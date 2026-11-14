"""Profile storage and recomputation shared by the API, tools and commands."""

import copy
import json
import logging
import math
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from .models import AlertSnooze, Customer, Goal, LoanDetails, Profile, Transaction

log = logging.getLogger(__name__)

DEMO_CUSTOMER_ID = "demo-aino"
TX_COLUMNS = [
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
SEVERITY_WEIGHT = {"red": 3, "amber": 2, "blue": 1}


def _reference_date_or_now():
    """P1.1: the reference date is the latest tx_date in the database.

    The S-Bank data ends in the past, so "today" everywhere (goals, chat,
    snoozes, alerts) is max(tx_date). With no transactions, the real date.
    """
    from django.db.models import Max

    from coach.models import Transaction

    latest = Transaction.objects.aggregate(d=Max("tx_date"))["d"]
    return latest or timezone.localdate()


def today():
    """The reference date (max tx_date); patched in tests."""
    return _reference_date_or_now()


def profile_today(profile):
    """The profile's own 'today' (synthetic data lives in the past)."""
    raw = (profile or {}).get("today")
    if raw:
        return date.fromisoformat(raw)
    return today()


def demo_fixture():
    path = settings.SHARED_FIXTURES_DIR / "profile_demo.json"
    return json.loads(path.read_text())


def get_profile(customer_id):
    """Return the stored profile dict or None.

    Order: DB Profile row, then backend/profiles/<id>.json, then the shared
    fixture for the demo customer (or any id when DEMO_MODE is on).
    """
    row = Profile.objects.filter(customer_id=customer_id).first()
    if row:
        return row.data
    path = settings.PROFILES_DIR / f"{customer_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    if customer_id == DEMO_CUSTOMER_ID or settings.DEMO_MODE:
        data = demo_fixture()
        data["customer_id"] = customer_id
        return data
    return None


def save_profile(customer_id, data, write_file=False):
    Profile.objects.update_or_create(customer_id=customer_id, defaults={"data": data})
    if write_file:
        settings.PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        path = settings.PROFILES_DIR / f"{customer_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str))


def list_customers():
    rows = [
        {
            "customer_id": c.customer_id,
            "customer_age": c.age,
            "customer_postal_code": c.postal_code,
        }
        for c in Customer.objects.order_by("customer_id")
    ]
    known = {r["customer_id"] for r in rows}
    for p in Profile.objects.exclude(customer_id__in=known):
        cust = p.data.get("customer", {})
        rows.append(
            {
                "customer_id": p.customer_id,
                "customer_age": cust.get("age"),
                "customer_postal_code": cust.get("postal_code"),
            }
        )
        known.add(p.customer_id)
    if DEMO_CUSTOMER_ID not in known:
        cust = demo_fixture()["customer"]
        rows.append(
            {
                "customer_id": DEMO_CUSTOMER_ID,
                "customer_age": cust["age"],
                "customer_postal_code": cust["postal_code"],
            }
        )
    return rows


def transactions_df(customer_id):
    """Transactions for one customer as the CLAUDE.md DataFrame, or None."""
    import pandas as pd

    qs = Transaction.objects.filter(customer_id=customer_id).values(
        "tx_id",
        "customer_id",
        "account_id",
        "tx_date",
        "tx_timestamp",
        "category",
        "tx_amount_eur",
        "balance_after_eur",
        "transaction_type",
        "merchant_id",
        "mcc_code",
    )
    rows = list(qs)
    if not rows:
        return None
    df = pd.DataFrame(rows).rename(columns={"account_id": "bank_account_id"})
    df["tx_date"] = pd.to_datetime(df["tx_date"])
    df["tx_timestamp"] = pd.to_datetime(df["tx_timestamp"]).dt.tz_localize(None)
    df["mcc_code"] = df["mcc_code"].astype(str)
    return df[TX_COLUMNS].sort_values("tx_timestamp").reset_index(drop=True)


def empty_df():
    import pandas as pd

    return pd.DataFrame(columns=TX_COLUMNS)


def goal_dicts(customer_id):
    return [
        g.as_dict()
        for g in Goal.objects.filter(customer_id=customer_id).exclude(
            status="abandoned"
        )
    ]


def latest_loan(customer_id):
    loan = LoanDetails.objects.filter(customer_id=customer_id).last()
    return loan.as_dict() if loan else None


def snoozed_ids(customer_id, on=None):
    on = on or today()
    return set(
        AlertSnooze.objects.filter(customer_id=customer_id, until__gt=on).values_list(
            "alert_id", flat=True
        )
    )


def alert_priority(alert, on):
    """priority = w_severity / max(1, days until impact) (Alert coach)."""
    weight = SEVERITY_WEIGHT.get(alert.get("severity"), 1)
    impact = alert.get("impact_date")
    days = 1
    if impact:
        days = (date.fromisoformat(str(impact)[:10]) - on).days
    return weight / max(1, days)


def active_alerts(customer_id, profile, on=None):
    """Profile alerts minus snoozed ones, sorted by priority (highest first)."""
    hidden = snoozed_ids(customer_id, on)
    p_today = profile_today(profile)
    alerts = []
    for alert in profile.get("alerts", []):
        if alert["id"] in hidden:
            continue
        alert = dict(alert)
        if alert.get("priority") is None:
            alert["priority"] = round(alert_priority(alert, p_today), 4)
        alerts.append(alert)
    return sorted(alerts, key=lambda a: a["priority"], reverse=True)


# --- recomputation -------------------------------------------------------


def build_customer_profile(customer_id, df, on):
    """Full profile for a customer with transactions, as of `on`.

    Goals get `on_track` first so levels (#31) are computed once, correctly;
    recompute_goals_locally then adds the full goal metrics, and the stress
    test (#77) is added when the user has given loan details.
    """
    from inferences import profile as profile_mod

    customer = Customer.objects.filter(customer_id=customer_id).first()
    cust = {
        "customer_id": customer_id,
        "age": customer.age if customer else None,
        "postal_code": customer.postal_code if customer else "",
    }
    goals = goal_dicts(customer_id)
    loans = latest_loan(customer_id)
    scored = [
        {**g, "on_track": goal_metrics(g, {}, on)["on_track"]}
        for g in goals
        if g["status"] == "active"
    ]
    data = profile_mod.build_profile(df, cust, on, goals=scored, loans=loans)
    recompute_goals_locally(data, goals, on)
    if loans:
        data["mortgage"]["stress_test"] = stress_test(data, loans["balance"])
    return data


def refresh_profile(customer_id):
    """Rerun goal and level inferences after a goal or loan change.

    With transactions in the DB the full ``build_profile`` runs. Without them
    (demo fixture), goal progress (#51, #52, #65, #49, #73), level 4 (#31) and
    the stress test (#77) are recomputed locally on the stored profile.
    """
    df = transactions_df(customer_id)
    goals = goal_dicts(customer_id)
    loans = latest_loan(customer_id)
    if df is not None:
        data = build_customer_profile(customer_id, df, today())
        save_profile(customer_id, data, write_file=True)
        return data

    base = get_profile(customer_id)
    if base is None:
        return None
    data = copy.deepcopy(base)
    p_today = profile_today(data)
    recompute_goals_locally(data, goals, p_today)
    if loans:
        data.setdefault("mortgage", {})["stress_test"] = stress_test(
            data, loans["balance"]
        )
    # TODO: rerun alerts once inferences.alerts can run without transactions.
    save_profile(customer_id, data)
    return data


def _months_between(start, end):
    return max(1, math.ceil((end - start).days / 30.44))


def goal_metrics(goal, profile, on):
    """#51 progress, #52 on track, #65 monthly, #26/#49 months and difficulty."""
    target, saved = float(goal["target"]), float(goal["saved"])
    start = date.fromisoformat(goal["start_date"])
    end = date.fromisoformat(goal["target_date"])
    # #72: a paused goal freezes its clock so it never shows off track.
    clock = date.fromisoformat(goal["paused_at"]) if goal.get("paused_at") else on
    total_days = max(1, (end - start).days)
    expected = min(100.0, max(0.0, (clock - start).days / total_days * 100))
    progress = saved / target * 100 if target else 0.0
    remaining = max(0.0, target - saved)
    months_left = _months_between(clock, end) if end > clock else 1
    monthly = 5 * math.ceil(remaining / (5 * months_left)) if remaining else 0
    rate = float(profile.get("baskets", {}).get("monthly_saving") or 0)
    months_needed = math.ceil(remaining / rate) if rate > 0 else None
    if months_needed is None:
        difficulty = "Hard"
    elif months_needed <= 2:
        difficulty = "Easy"
    elif months_needed <= 6:
        difficulty = "Stretch"
    else:
        difficulty = "Hard"
    safe_monthly = profile.get("goals", {}).get("clash", {}).get("safe_to_save_monthly")
    realistic = safe_monthly is None or monthly <= safe_monthly
    milestones = sorted(
        set(goal.get("milestones_hit") or [])
        | {m for m in (25, 50, 75, 100) if progress >= m}
    )
    return {
        "progress_pct": round(progress, 1),
        "expected_pct": round(expected, 1),
        "on_track": goal.get("paused") or progress >= 0.9 * expected,
        "monthly_needed": monthly,
        "months_needed": months_needed,
        "difficulty": difficulty,
        "realistic": realistic,
        "milestones_hit": milestones,
    }


def recompute_goals_locally(data, goals, on):
    section = data.setdefault("goals", {})
    fixture_goals = [g for g in section.get("active", []) if not g.get("db")]
    db_goals = []
    for g in goals:
        if g["status"] != "active":
            continue
        db_goals.append({**g, **goal_metrics(g, data, on), "db": True})
    section["active"] = fixture_goals + db_goals
    total = sum(g.get("monthly_needed") or 0 for g in section["active"])
    clash = section.setdefault("clash", {})
    clash["total_needed"] = total
    safe = clash.get("safe_to_save_monthly")
    clash["clash"] = safe is not None and total > safe
    _recompute_level4(data)


def _recompute_level4(data):
    levels = data.get("levels")
    if not levels or not levels.get("ladder"):
        return
    on_track = any(g.get("on_track") for g in data["goals"]["active"])
    for rung in levels["ladder"]:
        if rung["level"] == 4:
            rung["reached"] = bool(on_track)
    current = 0
    for rung in sorted(levels["ladder"], key=lambda r: r["level"]):
        if not rung.get("reached"):
            break
        current = rung["level"]
    levels["current"] = current
    names = {r["level"]: r["name"] for r in levels["ladder"]}
    levels["current_name"] = names.get(current, "")
    if current < 6:
        levels["next"] = current + 1
        levels["next_name"] = names.get(current + 1, "")


def stressed_payment(balance, annual_rate=0.06, months=300):
    """#77 annuity payment at the FIN-FSA stress rate."""
    i = annual_rate / 12
    return balance * i / (1 - (1 + i) ** -months)


def stress_test(profile, balance):
    """#77 rate-rise stress test with a user-entered loan balance."""
    income = float(profile.get("income", {}).get("monthly_income") or 0)
    other = float(profile.get("mortgage", {}).get("other_loan_payments") or 0)
    payment = stressed_payment(balance)
    dsti = (payment + other) / income if income else None
    return {
        "loan_balance": balance,
        "stressed_payment": round(payment, 2),
        "dsti_stress": round(dsti, 4) if dsti is not None else None,
        "fires": dsti is not None and dsti > 0.60,
        "limit": 0.60,
    }


def add_days(on, days):
    return on + timedelta(days=days)
