"""Alert rules (context.md "Alerts", "More alerts" and P1.7).

Every rule has the signature ``rule(df, profile, today, **ctx)`` and returns one
alert dict, a list of alert dicts, or ``None``. An alert dict is::

    {id, inference, severity, title, text, trigger_values, impact_date,
     priority, evidence_tx_ids, snoozed_until}

``df`` is the customer's transactions (columns in CLAUDE.md), ``profile`` is the
profile dict (shape in shared/fixtures/profile_demo.json). Rules that read the
profile work on a simulated (deep-copied, edited) profile, so the alert coach
planner can apply a what-if and call ``run_all_alerts`` again. Rules that read
``df`` only change when the planner also edits the transactions.

Inputs per rule (profile keys use dotted paths):

====  ==========================  ==============================================
#     Alert                       Reads
====  ==========================  ==============================================
6     Possibly unused sub         income.possibly_unused
20    Danger days                 forecast.danger_days
23    Seasonal heads-up           forecast.seasonal.{warn,next_month,ratio,pot}
38    Unusual charge              df
39    Duplicate charge            df
40    Category spike              df
42    Hidden loans                multibank.hidden_loans
43    Cross-bank duplicate subs   multibank.duplicate_subscriptions
50    Goal not realistic          goals.active[].{realistic,paused}
52    Goal off track              goals.active[].{on_track,paused,target_date}
62    Life change                 df, income.monthly_income
70    Goal clash                  goals.clash.{clash,total_needed,...}
76    Loan burden (DSTI)          df (loan outflows), income.monthly_income
77    Rate-rise stress test       ctx loans, income.monthly_income
78    Mortgage payment at risk    df, forecast.daily_path[].{date,low}
79    Mortgage payment changed    df
80    Missed loan payment         df
81    Buffer thin for mortgage    df (balance_after_eur, loan outflows)
82    Affordability check         ctx home_target, ctx loans, income
83    New credit taken            df
84    Many lenders                df
85    Overdraft                   df
86    Fees and late charges       df
87    Income dropped              df, income.payday.day_of_month
88    Spending pace               df, income.monthly_income
89    Lifestyle creep             baskets.history[].totals, baskets.totals
90    Subscription creep          df, income.subscriptions
91    Free trial turned paid      df
92    Similar subscriptions       income.subscriptions[].mcc_code
93    Annual bill coming          df
94    Savings withdrawn           df (own-account transfers)
95    Saving streak broken        df, income.payday.day_of_month
96    Cash withdrawals up         df
97    Small leaks                 df
98    Gambling (opt-in)           df, ctx opted_in_gambling
99    Low balance now             balance, forecast.buffer
100   Payday missed               df, income.payday
101   Bill went up                df, income.bills, income.subscriptions
102   Big bill coming             balance, forecast.{buffer,upcoming_bills}
====  ==========================  ==============================================

``forecast.buffer`` falls back to max(EUR 50, 10% of baskets.monthly_essentials).
Loan alerts (#76 to #84) only fire when loan outflows are found; #77 and #82 need
``loans={balance, interest_rate, years_left, other_payments?}``.

Constants shared with the inferences (own-transfer and loan sets, buffer, robust
z, stress test) come from inferences/thresholds.py; buffer, CV and the annuity
use inferences/common.py and inferences/models.py.
"""

import calendar
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from inferences import alert_thresholds as thresholds
from inferences import models
from inferences.common import buffer_amount, fill_pseudo_merchants, merchant_name

T = thresholds

# --- Small helpers ------------------------------------------------------------


def _to_date(value):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(str(value)).date()


def _get(profile, path, default=None):
    node = profile or {}
    for key in path.split("."):
        if not isinstance(node, dict) or node.get(key) is None:
            return default
        node = node[key]
    return node


def _prep(df):
    """Copy of df with clean types; an empty frame when df is None."""
    cols = [
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
    if df is None or len(df) == 0:
        out = pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
        out["tx_date"] = pd.Series(dtype="datetime64[ns]")
        out["tx_timestamp"] = pd.Series(dtype="datetime64[ns]")
        out["tx_amount_eur"] = pd.Series(dtype="float64")
        out["balance_after_eur"] = pd.Series(dtype="float64")
        return out
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = None
    if out["tx_id"].isna().all():
        out["tx_id"] = [f"t-{i}" for i in range(len(out))]
    out["tx_date"] = pd.to_datetime(out["tx_date"]).dt.normalize()
    stamp = pd.to_datetime(out["tx_timestamp"], errors="coerce")
    out["tx_timestamp"] = stamp.fillna(out["tx_date"])
    out["tx_amount_eur"] = out["tx_amount_eur"].astype(float)
    out["balance_after_eur"] = pd.to_numeric(out["balance_after_eur"], errors="coerce")
    out["mcc_code"] = out["mcc_code"].astype(str)
    out["category"] = out["category"].astype(str).str.lower()
    out["transaction_type"] = out["transaction_type"].astype(str).str.lower()
    out["merchant_id"] = fill_pseudo_merchants(out)
    out["tx_id"] = out["tx_id"].astype(str)
    return out.sort_values("tx_timestamp").reset_index(drop=True)


def _own(df):
    return df["transaction_type"].isin(T.OWN_TRANSFER_TYPES)


def _savings(df):
    """Moves into or out of savings / investments (#94, #95), not sweeps."""
    return df["transaction_type"].isin(T.SAVER_TYPES | T.SAVER_WITHDRAW_TYPES)


def _outflows(df):
    """Spending outflows: negative amounts, own-account transfers excluded."""
    return df[(df["tx_amount_eur"] < 0) & ~_own(df)]


def _inflows(df):
    return df[(df["tx_amount_eur"] > 0) & ~_own(df)]


def _loans(df):
    out = _outflows(df)
    mask = out["category"].isin(T.LOAN_CATEGORIES) | out["mcc_code"].isin(T.LOAN_MCCS)
    return out[mask]


def _month_bounds(today):
    start = today.replace(day=1)
    days = calendar.monthrange(today.year, today.month)[1]
    return start, days


def _month_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def _shift_month(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _monthly(frame, value=None):
    """Sum of abs amounts per 'YYYY-MM' key."""
    if frame.empty:
        return {}
    amounts = frame["tx_amount_eur"].abs() if value is None else value
    keys = frame["tx_date"].dt.strftime("%Y-%m")
    return amounts.groupby(keys).sum().to_dict()


def _buffer(profile):
    buf = _get(profile, "forecast.buffer")
    if buf is not None:
        return float(buf)
    essentials = float(_get(profile, "baskets.monthly_essentials", 0.0) or 0.0)
    return buffer_amount(essentials)


def _income(profile):
    return float(_get(profile, "income.monthly_income", 0.0) or 0.0)


def _cv(values):
    return models.cv(values)


def _label(merchant):
    """Display name; pseudo merchants ("type:housing_payment") -> "Housing"."""
    return merchant_name(pd.DataFrame(), merchant)


def _ids(frame, limit=5):
    return [str(i) for i in frame["tx_id"].tolist()[-limit:]]


def _eur(x):
    return f"EUR {x:,.2f}".replace(".00", "")


def _prev_weekday(d):
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _payday_in_month(year, month, day_of_month):
    day = min(int(day_of_month), calendar.monthrange(year, month)[1])
    return _prev_weekday(date(year, month, day))


def _last_expected_payday(profile, today):
    """Most recent expected payday on or before today (moved off weekends)."""
    day = _get(profile, "income.payday.day_of_month")
    if not _get(profile, "income.payday.found", day is not None) or day is None:
        return None
    this = _payday_in_month(today.year, today.month, day)
    if this <= today:
        return this
    prev = _shift_month(today.replace(day=1), -1)
    return _payday_in_month(prev.year, prev.month, day)


def stressed_payment(balance, rate=T.STRESS_RATE, months=T.STRESS_MONTHS):
    """Annuity payment at the FIN-FSA stress rate (#77, #82)."""
    return models.annuity_payment(balance, rate / 12, months)


def alert_priority(severity, impact_date, today):
    """priority = w_severity / max(1, days until impact) (Alert coach)."""
    today = _to_date(today)
    impact = _to_date(impact_date) or today
    days = (impact - today).days
    return T.SEVERITY_WEIGHT[severity] / max(1, days)


def _alert(
    inference, severity, title, text, today, impact, trigger, evidence=(), key=None
):
    impact = _to_date(impact) or today
    alert_id = f"a-{inference}" if key is None else f"a-{inference}-{key}"
    return {
        "id": alert_id,
        "inference": inference,
        "severity": severity,
        "title": title,
        "text": text,
        "trigger_values": trigger,
        "impact_date": impact.isoformat(),
        "priority": round(alert_priority(severity, impact, today), 4),
        "evidence_tx_ids": list(evidence),
        "snoozed_until": None,
    }


def _recurring_groups(frame, min_count=3):
    """Yield (merchant_id, rows) for merchants paid about monthly (model 1)."""
    for merchant, rows in frame.groupby("merchant_id"):
        if len(rows) < min_count:
            continue
        gaps = rows["tx_date"].diff().dt.days.dropna()
        if gaps.empty:
            continue
        if T.RECUR_GAP_MIN <= gaps.median() <= T.RECUR_GAP_MAX:
            yield merchant, rows


def _loan_merchants(df, today):
    """Per loan merchant: payments, median amount, next expected date."""
    loans = _loans(df)
    result = []
    for merchant, rows in loans.groupby("merchant_id"):
        amounts = rows["tx_amount_eur"].abs()
        gaps = rows["tx_date"].diff().dt.days.dropna()
        gap = float(gaps.median()) if not gaps.empty else 30.0
        last = rows["tx_date"].iloc[-1].date()
        result.append(
            {
                "merchant_id": merchant,
                "rows": rows,
                "payment": float(amounts.tail(3).median()),
                "last_date": last,
                "first_date": rows["tx_date"].iloc[0].date(),
                "gap": gap,
                "next_date": last + timedelta(days=round(gap)),
                "active": (today - last).days <= T.NEW_RECURRING_DAYS,
            }
        )
    return result


def _monthly_loan_payments(df, today):
    return sum(m["payment"] for m in _loan_merchants(df, today) if m["active"])


# --- Profile-based rules ----------------------------------------------------------


def rule_6_possibly_unused(df, profile, today, **ctx):
    found = []
    for sub in _get(profile, "income.possibly_unused", []) or []:
        name = sub.get("name") or sub.get("merchant_id")
        found.append(
            _alert(
                6,
                "blue",
                "Check this subscription",
                f"{name} ({_eur(sub.get('amount', 0))}) shows no other activity. "
                "Still using it?",
                today,
                today + timedelta(days=30),
                dict(sub),
                key=sub.get("merchant_id"),
            )
        )
    return found


def rule_20_danger_days(df, profile, today, **ctx):
    days = _get(profile, "forecast.danger_days", []) or []
    dates = sorted(_to_date(d.get("date") if isinstance(d, dict) else d) for d in days)
    if not dates:
        return None
    first = dates[0]
    return _alert(
        20,
        "amber",
        "Tight days ahead",
        f"Your balance could drop below EUR 50 around {first:%d %b}, before payday.",
        today,
        first,
        {"danger_days": [d.isoformat() for d in dates], "first": first.isoformat()},
    )


def rule_23_seasonal(df, profile, today, **ctx):
    seasonal = _get(profile, "forecast.seasonal", {}) or {}
    if not seasonal.get("warn"):
        return None
    month = seasonal.get("next_month") or _month_key(_shift_month(today, 1))
    impact = date.fromisoformat(f"{month}-01")
    return _alert(
        23,
        "amber",
        "Pricier month coming",
        f"Last year {month[5:]}/{month[:4][2:]} cost more than usual. A pot of "
        f"{_eur(seasonal.get('pot', 0))} would cover it.",
        today,
        impact,
        dict(seasonal),
    )


def rule_42_hidden_loans(df, profile, today, **ctx):
    loans = _get(profile, "multibank.hidden_loans", []) or []
    if not loans:
        return None
    total = sum(float(x.get("amount", 0)) for x in loans)
    return _alert(
        42,
        "amber",
        "Loan at another bank",
        f"You also pay {_eur(total)} a month on loans at another bank, so your "
        "safe to spend is lower.",
        today,
        today + timedelta(days=7),
        {"hidden_loans": loans, "monthly_total": round(total, 2)},
    )


def rule_43_cross_bank_subscriptions(df, profile, today, **ctx):
    dups = _get(profile, "multibank.duplicate_subscriptions", []) or []
    found = []
    for dup in dups:
        name = dup.get("name") or dup.get("merchant_id")
        found.append(
            _alert(
                43,
                "blue",
                "Paying twice?",
                f"{name} is a subscription on two of your accounts.",
                today,
                today + timedelta(days=30),
                dict(dup),
                key=dup.get("merchant_id"),
            )
        )
    return found


def _goals(profile):
    return [g for g in _get(profile, "goals.active", []) or [] if not g.get("paused")]


def rule_50_goal_realism(df, profile, today, **ctx):
    found = []
    for goal in _goals(profile):
        if goal.get("realistic", True):
            continue
        found.append(
            _alert(
                50,
                "amber",
                "Goal may be out of reach",
                f"{goal.get('name')} needs more each month than you can usually "
                "save. A later date or smaller amount would fit.",
                today,
                today + timedelta(days=T.GOAL_REVIEW_DAYS),
                {
                    "goal_id": goal.get("id"),
                    "monthly_needed": goal.get("monthly_needed"),
                },
                key=goal.get("id"),
            )
        )
    return found


def rule_52_goal_off_track(df, profile, today, **ctx):
    found = []
    for goal in _goals(profile):
        if goal.get("on_track", True):
            continue
        impact = today + timedelta(days=T.GOAL_REVIEW_DAYS)
        target = _to_date(goal.get("target_date"))
        if target and target < impact:
            impact = target
        found.append(
            _alert(
                52,
                "amber",
                "Goal off track",
                f"{goal.get('name')} is behind plan: "
                f"{goal.get('progress_pct', 0)}% saved, "
                f"{goal.get('expected_pct', 0)}% expected by now.",
                today,
                impact,
                {
                    "goal_id": goal.get("id"),
                    "progress_pct": goal.get("progress_pct"),
                    "expected_pct": goal.get("expected_pct"),
                },
                key=goal.get("id"),
            )
        )
    return found


def rule_70_goal_clash(df, profile, today, **ctx):
    clash = _get(profile, "goals.clash", {}) or {}
    if not clash.get("clash"):
        return None
    return _alert(
        70,
        "amber",
        "Goals compete for money",
        f"Your goals need {_eur(clash.get('total_needed', 0))} a month, but you can "
        f"safely save about {_eur(clash.get('safe_to_save_monthly', 0))}.",
        today,
        today + timedelta(days=T.GOAL_REVIEW_DAYS),
        dict(clash),
    )


def rule_89_lifestyle_creep(df, profile, today, **ctx):
    history = sorted(
        _get(profile, "baskets.history", []) or [], key=lambda h: h.get("month", "")
    )
    current_month = _get(profile, "baskets.month")
    series = [h.get("totals", {}) for h in history if h.get("month") != current_month]
    current = _get(profile, "baskets.totals")
    if current:
        series.append(current)
    shares = []
    for totals in series:
        total = sum(float(v or 0) for v in totals.values() if float(v or 0) > 0)
        shares.append(100 * float(totals.get("leaky", 0) or 0) / total if total else 0)
    n = T.CREEP_MONTHS
    if len(shares) < n + 1:
        return None
    tail = shares[-(n + 1) :]
    if not all(b > a for a, b in zip(tail, tail[1:])):
        return None
    return _alert(
        89,
        "blue",
        "Lifestyle creep",
        f"Your leaky share has risen {n} months in a row, to {tail[-1]:.1f}%.",
        today,
        today + timedelta(days=30),
        {"leaky_shares": [round(s, 1) for s in tail]},
    )


def rule_92_similar_subscriptions(df, profile, today, **ctx):
    by_mcc = {}
    for sub in _get(profile, "income.subscriptions", []) or []:
        by_mcc.setdefault(str(sub.get("mcc_code")), []).append(sub)
    found = []
    for mcc, subs in sorted(by_mcc.items()):
        if len(subs) < 2 or mcc in ("None", ""):
            continue
        names = [s.get("name") or s.get("merchant_id") for s in subs]
        total = sum(float(s.get("amount", 0)) for s in subs)
        found.append(
            _alert(
                92,
                "blue",
                "Similar subscriptions",
                f"{' and '.join(names)} are similar services "
                f"({_eur(total)} a month). Need both?",
                today,
                today + timedelta(days=30),
                {"merchants": names, "mcc_code": mcc, "monthly_total": round(total, 2)},
                key="-".join(str(s.get("merchant_id")) for s in subs),
            )
        )
    return found


def rule_99_low_balance(df, profile, today, **ctx):
    balance = _get(profile, "balance")
    if balance is None:
        return None
    buffer = _buffer(profile)
    if float(balance) >= buffer:
        return None
    return _alert(
        99,
        "red",
        "Low balance",
        f"Your balance is {_eur(float(balance))}, below your "
        f"{_eur(buffer)} safety cushion.",
        today,
        today,
        {"balance": float(balance), "buffer": round(buffer, 2)},
    )


def rule_102_big_bill(df, profile, today, **ctx):
    balance = _get(profile, "balance")
    if balance is None:
        return None
    buffer = _buffer(profile)
    found = []
    for bill in _get(profile, "forecast.upcoming_bills", []) or []:
        due = _to_date(bill.get("date"))
        amount = float(bill.get("amount", 0))
        if due is None or not 0 <= (due - today).days <= T.BIG_BILL_DAYS:
            continue
        if float(balance) - amount >= buffer:
            continue
        found.append(
            _alert(
                102,
                "amber",
                "Big bill coming",
                f"{bill.get('name', 'A bill')} ({_eur(amount)}) is due {due:%d %b} "
                "and would leave you below your safety cushion.",
                today,
                due,
                {"bill": dict(bill), "balance": float(balance), "buffer": buffer},
                key=bill.get("merchant_id") or bill.get("name"),
            )
        )
    return found


# --- Transaction-based rules -------------------------------------------------------


def rule_38_unusual_charge(df, profile, today, **ctx):
    out = _outflows(df)
    cutoff = pd.Timestamp(today - timedelta(days=T.RECENT_DAYS))
    found = []
    for _, row in out[out["tx_date"] >= cutoff].iterrows():
        amount = abs(row["tx_amount_eur"])
        # Purchases without a merchant_id have no merchant history.
        known = row["merchant_id"] not in ("", "None", "nan", "<NA>")
        past = out[known & (out["merchant_id"] == row["merchant_id"])]
        past = past[past["tx_timestamp"] < row["tx_timestamp"]]["tx_amount_eur"].abs()
        z = None
        flagged = False
        if len(past) >= T.UNUSUAL_MIN_HISTORY:
            median = past.median()
            mad = (past - median).abs().median()
            # Calibrated: also > 3 x median and > EUR 50 above it.
            big = (
                amount > T.UNUSUAL_MIN_MULT * median
                and amount - median > T.UNUSUAL_MIN_EXCESS_EUR
            )
            if mad > 0:
                z = T.ROBUST_Z_CONST * (amount - median) / mad
                flagged = z > T.ROBUST_Z_FLAG and big
            else:
                flagged = big
        else:
            cat = out[
                (out["category"] == row["category"]) & (out["tx_id"] != row["tx_id"])
            ]["tx_amount_eur"].abs()
            flagged = len(cat) > 0 and amount > T.UNUSUAL_CATEGORY_MULT * cat.median()
        if not flagged:
            continue
        found.append(
            _alert(
                38,
                "amber",
                "Unusual charge",
                f"{_eur(amount)} at {_label(row['merchant_id'])} is much more than you "
                "usually pay there. Looks fine?",
                today,
                today,
                {
                    "amount": amount,
                    "merchant_id": row["merchant_id"],
                    "z": None if z is None else round(float(z), 2),
                },
                [row["tx_id"]],
                key=row["tx_id"],
            )
        )
    return found


def rule_39_duplicate_charge(df, profile, today, **ctx):
    out = _outflows(df)
    cutoff = pd.Timestamp(today - timedelta(days=T.RECENT_DAYS))
    out = out[out["tx_date"] >= cutoff]
    found = []
    window = pd.Timedelta(minutes=T.DUPLICATE_MINUTES)
    for (merchant, amount), rows in out.groupby(["merchant_id", "tx_amount_eur"]):
        rows = rows.sort_values("tx_timestamp")
        stamps = rows["tx_timestamp"].tolist()
        ids = rows["tx_id"].tolist()
        for i in range(1, len(rows)):
            if stamps[i] - stamps[i - 1] <= window:
                found.append(
                    _alert(
                        39,
                        "amber",
                        "Charged twice?",
                        f"{_label(merchant)} charged {_eur(abs(amount))} twice within "
                        f"{T.DUPLICATE_MINUTES} minutes.",
                        today,
                        today,
                        {"merchant_id": merchant, "amount": abs(amount)},
                        [ids[i - 1], ids[i]],
                        key=ids[i],
                    )
                )
    return found


def rule_40_category_spike(df, profile, today, **ctx):
    out = _outflows(df)
    if out.empty:
        return []
    this = _month_key(today)
    prev = [_month_key(_shift_month(today.replace(day=1), -k)) for k in (1, 2, 3)]
    found = []
    for category, rows in out.groupby("category"):
        monthly = _monthly(rows)
        current = monthly.get(this, 0.0)
        if T.SPIKE_REQUIRE_FULL_HISTORY and not all(
            monthly.get(m, 0.0) > 0 for m in prev
        ):
            continue  # calibrated: needs spend in each of the previous 3 months
        mean_prev = sum(monthly.get(m, 0.0) for m in prev) / 3
        if mean_prev <= 0:
            continue
        if current > T.SPIKE_RATIO * mean_prev and current - mean_prev > (
            T.SPIKE_MIN_DIFF_EUR
        ):
            month_rows = rows[rows["tx_date"].dt.strftime("%Y-%m") == this]
            found.append(
                _alert(
                    40,
                    "amber",
                    "Category spike",
                    f"{category.title()} is at {_eur(current)} this month, up from "
                    f"about {_eur(mean_prev)}.",
                    today,
                    today,
                    {
                        "category": category,
                        "this_month": round(current, 2),
                        "mean_prev_3": round(mean_prev, 2),
                    },
                    _ids(month_rows),
                    key=category,
                )
            )
    return found


def rule_62_life_change(df, profile, today, **ctx):
    income = _income(profile)
    out = _outflows(df)
    cutoff = pd.Timestamp(today - timedelta(days=T.NEW_RECURRING_DAYS))
    found = []
    for merchant, rows in out.groupby("merchant_id"):
        if len(rows) < 2 or rows["tx_date"].min() < cutoff:
            continue
        gaps = rows["tx_date"].diff().dt.days.dropna()
        median = rows["tx_amount_eur"].abs().median()
        if not T.RECUR_GAP_MIN <= gaps.median() <= T.RECUR_GAP_MAX:
            continue
        if income <= 0 or median <= T.LIFE_CHANGE_INCOME_SHARE * income:
            continue
        found.append(
            _alert(
                62,
                "amber",
                "New big regular payment",
                f"A new monthly payment of about {_eur(median)} to "
                f"{_label(merchant)} started recently. Want to re-plan your goals?",
                today,
                today + timedelta(days=7),
                {"merchant_id": merchant, "amount": round(float(median), 2)},
                _ids(rows),
                key=merchant,
            )
        )
    return found


def rule_76_loan_burden(df, profile, today, **ctx):
    payments = _monthly_loan_payments(df, today)
    income = _income(profile)
    if payments <= 0 or income <= 0:
        return None
    dsti = payments / income
    if dsti <= T.DSTI_AMBER:
        return None
    severity = "red" if dsti > T.DSTI_RED else "amber"
    advisor = " An S-Bank advisor can help." if severity == "red" else ""
    return _alert(
        76,
        severity,
        "Loan payments are high",
        f"Loan payments take {dsti:.0%} of your income "
        f"({_eur(payments)} of {_eur(income)}).{advisor}",
        today,
        today + timedelta(days=7),
        {"dsti": round(dsti, 4), "loan_payments": payments, "net_income": income},
        _ids(_loans(df)),
    )


def rule_77_stress_test(df, profile, today, loans=None, **ctx):
    if not loans or not loans.get("balance"):
        return None
    income = _income(profile)
    if income <= 0:
        return None
    stressed = stressed_payment(float(loans["balance"]))
    other = float(loans.get("other_payments", 0) or 0)
    ratio = (stressed + other) / income
    if ratio <= T.STRESS_DSTI_MAX:
        return None
    return _alert(
        77,
        "red",
        "Rate-rise stress test",
        f"If rates rose to 6%, loan payments would be about "
        f"{_eur(stressed + other)} a month, {ratio:.0%} of your income (limit 60%). "
        "Talk to an S-Bank advisor.",
        today,
        today + timedelta(days=1),
        {
            "stressed_payment": round(stressed, 2),
            "other_payments": other,
            "stressed_dsti": round(ratio, 4),
            "net_income": income,
        },
    )


def _mortgage(df, today):
    merchants = [m for m in _loan_merchants(df, today) if m["active"]]
    return max(merchants, key=lambda m: m["payment"]) if merchants else None


def rule_78_mortgage_at_risk(df, profile, today, **ctx):
    mortgage = _mortgage(df, today)
    if mortgage is None:
        return None
    day_before = mortgage["next_date"] - timedelta(days=1)
    low = None
    for point in _get(profile, "forecast.daily_path", []) or []:
        if _to_date(point.get("date")) == day_before:
            low = point.get("low")
    if low is None or float(low) >= mortgage["payment"]:
        return None
    return _alert(
        78,
        "red",
        "Loan payment at risk",
        f"Your balance may not cover the {_eur(mortgage['payment'])} loan payment on "
        f"{mortgage['next_date']:%d %b}. Talk to an S-Bank advisor.",
        today,
        mortgage["next_date"],
        {"payment": mortgage["payment"], "forecast_low": float(low)},
        _ids(mortgage["rows"], 3),
    )


def rule_79_payment_changed(df, profile, today, **ctx):
    found = []
    for m in _loan_merchants(df, today):
        amounts = m["rows"]["tx_amount_eur"].abs().tolist()
        if len(amounts) < 4 or not m["active"]:
            continue
        base = float(np.median(amounts[-4:-1]))
        if base <= 0 or abs(amounts[-1] - base) / base <= T.PAYMENT_CHANGE_PCT:
            continue
        found.append(
            _alert(
                79,
                "amber",
                "Loan payment changed",
                f"Your loan payment changed from about {_eur(base)} to "
                f"{_eur(amounts[-1])}. Your loan's interest rate probably changed.",
                today,
                m["next_date"],
                {"merchant_id": m["merchant_id"], "previous": base, "new": amounts[-1]},
                _ids(m["rows"], 4),
                key=m["merchant_id"],
            )
        )
    return found


def rule_80_missed_payment(df, profile, today, **ctx):
    found = []
    for m in _loan_merchants(df, today):
        if not m["active"] or len(m["rows"]) < 2:
            continue
        if (today - m["next_date"]).days <= T.MISSED_PAYMENT_GRACE_DAYS:
            continue
        found.append(
            _alert(
                80,
                "red",
                "Loan payment not seen",
                f"We expected a {_eur(m['payment'])} loan payment around "
                f"{m['next_date']:%d %b}. If it's missed, an S-Bank advisor can help.",
                today,
                today,
                {
                    "merchant_id": m["merchant_id"],
                    "expected": m["next_date"].isoformat(),
                },
                _ids(m["rows"], 3),
                key=m["merchant_id"],
            )
        )
    return found


def _lowest_balance(df, today, days=30):
    recent = df[df["tx_date"] >= pd.Timestamp(today - timedelta(days=days))]
    balances = recent["balance_after_eur"].dropna()
    return float(balances.min()) if not balances.empty else None


def rule_81_buffer_thin(df, profile, today, **ctx):
    payments = _monthly_loan_payments(df, today)
    if payments <= 0:
        return None
    lowest = _lowest_balance(df, today)
    if lowest is None:
        lowest = _get(profile, "balance")
    if lowest is None or float(lowest) / payments >= 1:
        return None
    return _alert(
        81,
        "amber",
        "Thin cushion for your loan",
        f"Your lowest balance this month ({_eur(float(lowest))}) would not cover one "
        f"loan payment ({_eur(payments)}).",
        today,
        today + timedelta(days=14),
        {"lowest_balance": float(lowest), "monthly_loan_payments": payments},
    )


def rule_82_affordability(df, profile, today, loans=None, home_target=None, **ctx):
    if not home_target or not home_target.get("price"):
        return None
    income = _income(profile)
    if income <= 0:
        return None
    loan = float(home_target["price"]) - float(home_target.get("deposit", 0) or 0)
    other = float((loans or {}).get("other_payments", 0) or 0)
    if not loans:
        other = _monthly_loan_payments(df, today)
    ratio = (stressed_payment(max(loan, 0)) + other) / income
    if ratio <= T.AFFORD_FITS_MAX:
        label = "fits"
    elif ratio <= T.STRESS_DSTI_MAX:
        label = "tight"
    else:
        label = "doesn't fit"
    return _alert(
        82,
        "blue",
        "Home affordability check",
        f"A {_eur(loan)} loan would take {ratio:.0%} of your income in the 6% "
        f"stress test: {label}. Guidance only, not a loan decision.",
        today,
        today + timedelta(days=30),
        {"loan": loan, "stressed_dsti": round(ratio, 4), "label": label},
    )


def rule_83_new_credit(df, profile, today, **ctx):
    found = []
    cutoff = today - timedelta(days=T.NEW_RECURRING_DAYS)
    for m in _loan_merchants(df, today):
        if m["first_date"] < cutoff:
            continue
        found.append(
            _alert(
                83,
                "amber",
                "New credit",
                f"A new loan or credit payment to {m['merchant_id']} "
                f"({_eur(m['payment'])}) started recently.",
                today,
                m["next_date"],
                {"merchant_id": m["merchant_id"], "payment": m["payment"]},
                _ids(m["rows"]),
                key=m["merchant_id"],
            )
        )
    return found


def rule_84_many_lenders(df, profile, today, **ctx):
    loans = _loans(df)
    recent = loans[
        loans["tx_date"] >= pd.Timestamp(today - timedelta(days=T.MANY_LENDERS_DAYS))
    ]
    lenders = sorted(recent["merchant_id"].dropna().unique().tolist())
    if len(lenders) < T.MANY_LENDERS_MIN:
        return None
    return _alert(
        84,
        "amber",
        "Several lenders",
        f"You're paying {len(lenders)} different lenders. Combining them could be "
        "simpler; an S-Bank advisor can look at options.",
        today,
        today + timedelta(days=14),
        {"lenders": lenders},
        _ids(recent),
    )


def rule_85_overdraft(df, profile, today, **ctx):
    recent = df[df["tx_date"] >= pd.Timestamp(today - timedelta(days=30))]
    negative = recent[recent["balance_after_eur"] < 0]
    if negative.empty:
        return None
    low = float(negative["balance_after_eur"].min())
    return _alert(
        85,
        "red",
        "Balance went below zero",
        f"Your balance dipped to {_eur(low)} this month. It happens; let's find a "
        "little room before payday.",
        today,
        today,
        {"lowest_balance": low, "times": int(len(negative))},
        _ids(negative),
    )


def _this_month(frame, today):
    start, _ = _month_bounds(today)
    return frame[
        (frame["tx_date"] >= pd.Timestamp(start))
        & (frame["tx_date"] <= pd.Timestamp(today))
    ]


def rule_86_fees(df, profile, today, **ctx):
    out = _this_month(_outflows(df), today)
    fees = out[
        out["category"].isin(T.FEE_CATEGORIES) | out["mcc_code"].isin(T.FEE_MCCS)
    ]
    total = float(fees["tx_amount_eur"].abs().sum())
    if total <= 0:
        return None
    return _alert(
        86,
        "amber",
        "Fees this month",
        f"You've paid {_eur(total)} in fees or late charges this month.",
        today,
        today + timedelta(days=7),
        {"total": round(total, 2), "count": int(len(fees))},
        _ids(fees),
    )


def rule_87_income_dropped(df, profile, today, **ctx):
    day = _get(profile, "income.payday.day_of_month")
    if day is None:
        return None
    expected = _payday_in_month(today.year, today.month, day)
    if (today - expected).days < T.INCOME_DROP_CHECK_DAYS:
        return None
    monthly = _monthly(_inflows(df))
    prev = [
        monthly.get(_month_key(_shift_month(today.replace(day=1), -k)), 0.0)
        for k in (1, 2, 3)
    ]
    median = float(np.median(prev))
    current = monthly.get(_month_key(today), 0.0)
    if median <= 0 or current >= T.INCOME_DROP_RATIO * median:
        return None
    return _alert(
        87,
        "amber",
        "Income lower this month",
        f"You've received {_eur(current)} this month, less than your usual "
        f"{_eur(median)}.",
        today,
        today + timedelta(days=3),
        {"this_month": current, "median_prev_3": median},
    )


def rule_88_spending_pace(df, profile, today, **ctx):
    start, days_in_month = _month_bounds(today)
    if today.day < T.PACE_MIN_DAY:
        return None
    income = _income(profile)
    spent = float(_this_month(_outflows(df), today)["tx_amount_eur"].abs().sum())
    projected = spent / today.day * days_in_month
    if income <= 0 or projected <= income:
        return None
    end = date(today.year, today.month, days_in_month)
    return _alert(
        88,
        "amber",
        "Spending pace",
        f"At this pace you'll spend about {_eur(projected)} this month, more than "
        f"your {_eur(income)} income.",
        today,
        end,
        {"spent": round(spent, 2), "projected": round(projected, 2), "income": income},
    )


def rule_90_subscription_creep(df, profile, today, **ctx):
    ids = {
        s.get("merchant_id") for s in _get(profile, "income.subscriptions", []) or []
    }
    if not ids or df.empty:
        return None
    subs = _outflows(df)
    subs = subs[subs["merchant_id"].isin(ids)]
    last_full = _shift_month(today.replace(day=1), -1)
    old = _shift_month(last_full, -T.SUB_CREEP_MONTHS_BACK)
    if df["tx_date"].min() > pd.Timestamp(old):
        return None
    monthly = _monthly(subs)
    now_total = monthly.get(_month_key(last_full), 0.0)
    old_total = monthly.get(_month_key(old), 0.0)
    if old_total <= 0 or now_total <= T.SUB_CREEP_RATIO * old_total:
        return None
    return _alert(
        90,
        "blue",
        "Subscriptions creeping up",
        f"Subscriptions cost {_eur(now_total)} a month now, up from "
        f"{_eur(old_total)} six months ago.",
        today,
        today + timedelta(days=30),
        {"now": round(now_total, 2), "six_months_ago": round(old_total, 2)},
    )


def rule_91_free_trial(df, profile, today, **ctx):
    found = []
    amounts = df["tx_amount_eur"]
    trials = df[(amounts <= 0) & (amounts >= -T.TRIAL_MAX_EUR) & ~_own(df)]
    full = df[(amounts < -T.TRIAL_MAX_EUR) & ~_own(df)]
    recent = pd.Timestamp(today - timedelta(days=T.TRIAL_RECENT_DAYS))
    for _, trial in trials.iterrows():
        later = full[(full["merchant_id"] == trial["merchant_id"])]
        later = later[later["tx_date"] > trial["tx_date"]]
        if later.empty:
            continue
        first = later.iloc[0]
        gap = (first["tx_date"] - trial["tx_date"]).days
        if not T.TRIAL_GAP_MIN <= gap <= T.TRIAL_GAP_MAX or first["tx_date"] < recent:
            continue
        found.append(
            _alert(
                91,
                "blue",
                "Free trial now paid",
                f"{_label(trial['merchant_id'])} started charging "
                f"{_eur(abs(first['tx_amount_eur']))} after a free trial. Keep it?",
                today,
                today + timedelta(days=30),
                {
                    "merchant_id": trial["merchant_id"],
                    "amount": abs(float(first["tx_amount_eur"])),
                },
                [trial["tx_id"], first["tx_id"]],
                key=trial["merchant_id"],
            )
        )
    return found


def rule_93_annual_bill(df, profile, today, **ctx):
    found = []
    for merchant, rows in _outflows(df).groupby("merchant_id"):
        if len(rows) < 2:
            continue
        gaps = rows["tx_date"].diff().dt.days.dropna()
        gap = gaps.iloc[-1]
        if not T.ANNUAL_GAP_MIN <= gap <= T.ANNUAL_GAP_MAX:
            continue
        if _cv(rows["tx_amount_eur"].abs().tail(2)) >= T.RECUR_CV_MAX:
            continue
        next_date = rows["tx_date"].iloc[-1].date() + timedelta(days=int(gap))
        if not 0 <= (next_date - today).days <= T.ANNUAL_LOOKAHEAD_DAYS:
            continue
        amount = float(rows["tx_amount_eur"].abs().iloc[-1])
        found.append(
            _alert(
                93,
                "amber",
                "Yearly bill coming",
                f"{_label(merchant)} charges about {_eur(amount)} once a year; "
                f"next around {next_date:%d %b}.",
                today,
                next_date,
                {"merchant_id": merchant, "amount": amount},
                _ids(rows, 2),
                key=merchant,
            )
        )
    return found


def rule_94_savings_withdrawn(df, profile, today, **ctx):
    own = _this_month(df[_savings(df)], today)
    if own.empty:
        return None
    net_saved = float(-own["tx_amount_eur"].sum())
    if net_saved >= 0:
        return None
    return _alert(
        94,
        "amber",
        "Savings dipped",
        f"You moved {_eur(-net_saved)} more out of savings than in this month.",
        today,
        today + timedelta(days=7),
        {"net_saver": round(net_saved, 2)},
        _ids(own),
    )


def rule_95_saving_streak(df, profile, today, **ctx):
    payday = _last_expected_payday(profile, today)
    if payday is None:
        return None
    saves = df[_savings(df) & (df["tx_amount_eur"] < 0)]
    window = pd.Timestamp(today - timedelta(days=92))
    if len(saves[saves["tx_date"] >= window]) < T.SAVING_STREAK_MIN_TRANSFERS:
        return None
    if (today - payday).days < T.SAVING_STREAK_GRACE_DAYS:
        return None
    if not saves[saves["tx_date"] >= pd.Timestamp(payday)].empty:
        return None
    return _alert(
        95,
        "blue",
        "Saving streak paused",
        "Your usual transfer to savings hasn't happened since payday yet.",
        today,
        today + timedelta(days=3),
        {"last_payday": payday.isoformat()},
        _ids(saves, 3),
    )


def rule_96_cash_up(df, profile, today, **ctx):
    atm = _outflows(df)
    atm = atm[atm["mcc_code"] == T.ATM_MCC]
    if atm.empty:
        return None
    monthly = _monthly(atm)
    current = monthly.get(_month_key(today), 0.0)
    prev = [
        monthly.get(_month_key(_shift_month(today.replace(day=1), -k)), 0.0)
        for k in (1, 2, 3)
    ]
    avg = sum(prev) / 3
    if avg <= 0 or current <= T.CASH_UP_RATIO * avg:
        return None
    return _alert(
        96,
        "blue",
        "More cash than usual",
        f"You've taken out {_eur(current)} in cash this month, versus about "
        f"{_eur(avg)} usually. Cash is easy to lose track of.",
        today,
        today + timedelta(days=14),
        {"this_month": current, "avg_prev_3": round(avg, 2)},
        _ids(_this_month(atm, today)),
    )


def rule_97_small_leaks(df, profile, today, **ctx):
    out = _this_month(_outflows(df), today)
    small = out[out["tx_amount_eur"].abs() < T.SMALL_LEAK_EUR]
    if len(small) <= T.SMALL_LEAK_COUNT:
        return None
    total = float(small["tx_amount_eur"].abs().sum())
    return _alert(
        97,
        "blue",
        "Small leaks",
        f"{len(small)} small purchases under EUR 3 this month add up to {_eur(total)}.",
        today,
        today + timedelta(days=14),
        {"count": int(len(small)), "total": round(total, 2)},
        _ids(small),
    )


def rule_98_gambling(df, profile, today, opted_in_gambling=False, **ctx):
    if not opted_in_gambling:
        return None
    bets = _outflows(df)
    bets = bets[bets["mcc_code"] == T.GAMBLING_MCC]
    monthly = _monthly(bets)
    months = [_month_key(_shift_month(today.replace(day=1), -k)) for k in (2, 1, 0)]
    series = [monthly.get(m, 0.0) for m in months]
    if not (series[0] < series[1] < series[2]):
        return None
    return _alert(
        98,
        "amber",
        "Gaming spend rising",
        f"Gaming spend went {_eur(series[0])}, {_eur(series[1])}, {_eur(series[2])} "
        "over three months. If you'd like support, it's free and confidential: "
        f"{T.GAMBLING_SUPPORT_URL}",
        today,
        today + timedelta(days=7),
        {"monthly": dict(zip(months, series))},
        _ids(bets),
    )


def rule_100_payday_missed(df, profile, today, **ctx):
    # Only for a payday that was actually detected (#1) and with transactions
    # to check against; no data is not a missed salary.
    if df is None or len(df) == 0 or _get(profile, "income.payday.found") is not True:
        return None
    expected = _last_expected_payday(profile, today)
    if expected is None:
        return None
    if (today - expected).days <= T.PAYDAY_MISSED_DAYS:
        return None
    merchant = _get(profile, "income.payday.merchant_id")
    amount = float(_get(profile, "income.payday.amount", 0) or 0)
    inflows = _inflows(df)
    window = inflows[inflows["tx_date"] >= pd.Timestamp(expected - timedelta(days=5))]
    if merchant:
        window = window[window["merchant_id"] == merchant]
    elif amount > 0:
        window = window[window["tx_amount_eur"] >= 0.5 * amount]
    if not window.empty:
        return None
    return _alert(
        100,
        "red",
        "Salary not arrived",
        f"We expected your salary around {expected:%a %d %b} and haven't seen it yet.",
        today,
        today,
        {"expected_payday": expected.isoformat(), "merchant_id": merchant},
    )


def rule_101_bill_went_up(df, profile, today, **ctx):
    out = _outflows(df)
    ids = {b.get("merchant_id") for b in _get(profile, "income.bills", []) or []}
    ids |= {
        s.get("merchant_id") for s in _get(profile, "income.subscriptions", []) or []
    }
    ids |= {m for m, _ in _recurring_groups(out, min_count=4)}
    found = []
    recent = pd.Timestamp(today - timedelta(days=T.RECUR_GAP_MAX))
    for merchant in sorted(i for i in ids if i):
        rows = out[out["merchant_id"] == merchant]
        if len(rows) < 4 or rows["tx_date"].iloc[-1] < recent:
            continue
        amounts = rows["tx_amount_eur"].abs().tolist()
        # A bill is stable: restaurants visited about monthly are not bills
        # (calibration: 25% of customers flagged before this check).
        if _cv(amounts[-4:-1]) >= T.RECUR_CV_MAX:
            continue
        base = float(np.median(amounts[-4:-1]))
        threshold = T.BILL_UP_RATIO * base
        if amounts[-1] <= threshold:
            continue
        found.append(
            _alert(
                101,
                "amber",
                "Bill went up",
                f"{_label(merchant)} went from {_eur(base)} to {_eur(amounts[-1])}.",
                today,
                today + timedelta(days=7),
                {
                    "merchant_id": merchant,
                    "previous": base,
                    "new": amounts[-1],
                    "threshold": round(threshold, 2),
                },
                _ids(rows, 4),
                key=merchant,
            )
        )
    return found


# --- Registry -----------------------------------------------------------------

ALERT_RULES = {
    6: rule_6_possibly_unused,
    20: rule_20_danger_days,
    23: rule_23_seasonal,
    38: rule_38_unusual_charge,
    39: rule_39_duplicate_charge,
    40: rule_40_category_spike,
    42: rule_42_hidden_loans,
    43: rule_43_cross_bank_subscriptions,
    50: rule_50_goal_realism,
    52: rule_52_goal_off_track,
    62: rule_62_life_change,
    70: rule_70_goal_clash,
    76: rule_76_loan_burden,
    77: rule_77_stress_test,
    78: rule_78_mortgage_at_risk,
    79: rule_79_payment_changed,
    80: rule_80_missed_payment,
    81: rule_81_buffer_thin,
    82: rule_82_affordability,
    83: rule_83_new_credit,
    84: rule_84_many_lenders,
    85: rule_85_overdraft,
    86: rule_86_fees,
    87: rule_87_income_dropped,
    88: rule_88_spending_pace,
    89: rule_89_lifestyle_creep,
    90: rule_90_subscription_creep,
    91: rule_91_free_trial,
    92: rule_92_similar_subscriptions,
    93: rule_93_annual_bill,
    94: rule_94_savings_withdrawn,
    95: rule_95_saving_streak,
    96: rule_96_cash_up,
    97: rule_97_small_leaks,
    98: rule_98_gambling,
    99: rule_99_low_balance,
    100: rule_100_payday_missed,
    101: rule_101_bill_went_up,
    102: rule_102_big_bill,
}


def run_all_alerts(
    df,
    profile,
    today,
    loans=None,
    opted_in_gambling=False,
    snoozed=None,
    home_target=None,
):
    """Run every rule; return active alerts sorted by priority (highest first).

    ``snoozed`` maps alert id -> date; the alert stays hidden until that date.
    Works on a simulated profile from the what-if engine (see module docstring).
    """
    today = _to_date(today)
    frame = _prep(df)
    snoozed = {k: _to_date(v) for k, v in (snoozed or {}).items()}
    ctx = {
        "loans": loans,
        "opted_in_gambling": opted_in_gambling,
        "home_target": home_target,
    }
    found = []
    for rule in ALERT_RULES.values():
        result = rule(frame, profile or {}, today, **ctx)
        if result is None:
            continue
        found.extend(result if isinstance(result, list) else [result])
    active = [
        a for a in found if not (snoozed.get(a["id"]) and today < snoozed[a["id"]])
    ]
    return sorted(active, key=lambda a: (-a["priority"], a["inference"], a["id"]))


def top_nudge(alerts):
    """Highest-priority red or amber alert for the home screen, or None."""
    urgent = [a for a in alerts if a.get("severity") in ("red", "amber")]
    if not urgent:
        return None
    return max(urgent, key=lambda a: a.get("priority", 0))


__all__ = [
    "ALERT_RULES",
    "alert_priority",
    "run_all_alerts",
    "stressed_payment",
    "thresholds",
    "top_nudge",
]
