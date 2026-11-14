"""Which inferences the customer's own data actually supports.

Saldo only shows given, useful insights. build_profile() adds
profile["availability"]: {item: {available, reason, inferences}} for every
item below, so the API can drop anything that is not backed by the
customer's data instead of showing a zero or a placeholder. `reason` is a
plain-language sentence when `available` is False, else None.

Items are dotted paths into the profile (e.g. "income.payday").
"""

from __future__ import annotations

from . import thresholds as th


def _get(profile: dict, path: str, default=None):
    node = profile
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _nonempty(value) -> bool:
    return bool(value)


def _month_spend(profile) -> float:
    totals = _get(profile, "baskets.totals", {}) or {}
    return float(sum(v or 0 for v in totals.values()))


def _saver_ever(profile) -> bool:
    if (_get(profile, "baskets.totals.saver") or 0) > 0:
        return True
    return any(
        (h.get("totals") or {}).get("saver", 0) > 0
        for h in _get(profile, "baskets.history", []) or []
    )


def _trend_history(profile) -> bool:
    hist = _get(profile, "baskets.history", []) or []
    with_spend = [h for h in hist if sum((h.get("totals") or {}).values()) > 0]
    return len(with_spend) >= 3


def _payday(profile) -> bool:
    return _get(profile, "income.payday.found") is True


PAYDAY_REASONS = {
    "no_income": "No income in the data, so no payday to find.",
    "not_recurring": "No regular salary found (needs one in 3 of the last 4 months).",
    "amount_varies": (
        "Your income arrives regularly, but the amount changes too much from "
        f"month to month (more than {th.SALARY_CV_MAX:.0%}) to tell which "
        "payment is your salary."
    ),
}


def _payday_reason(profile) -> str:
    """#1: say which check detect_payday failed."""
    code = _get(profile, "income.payday.reason")
    return PAYDAY_REASONS.get(code, PAYDAY_REASONS["not_recurring"])


def _balance(profile) -> bool:
    return _get(profile, "balance") is not None


def _real_accounts(profile) -> int:
    accounts = _get(profile, "multibank.accounts", []) or []
    return len(accounts)


# item -> (inference numbers, check(profile) -> bool, reason when False);
# the reason may be a function of the profile when it depends on why.
RULES = {
    "balance": ([17], _balance, "No balance in the data."),
    "income.payday": ([1], _payday, _payday_reason),
    "income.monthly_income": (
        [2],
        lambda p: (_get(p, "income.monthly_income") or 0) > 0,
        "No income in the last 3 full months.",
    ),
    "income.stability": (
        [3],
        lambda p: _get(p, "income.stability.cv") is not None
        and (_get(p, "income.monthly_income") or 0) > 0,
        "Not enough months of income to judge stability.",
    ),
    "income.bills": (
        [4],
        lambda p: _nonempty(_get(p, "income.bills")),
        "No regular monthly bills found.",
    ),
    "income.subscriptions": (
        [5],
        lambda p: _nonempty(_get(p, "income.subscriptions")),
        "No subscriptions found in the transactions.",
    ),
    "income.possibly_unused": (
        [6],
        lambda p: _nonempty(_get(p, "income.possibly_unused")),
        "No subscription shows signs of being unused.",
    ),
    "baskets": (
        [7, 8, 9, 10],
        lambda p: _month_spend(p) > 0,
        "No spending this month to split into baskets.",
    ),
    "baskets.saver": (
        [75],
        _saver_ever,
        "No transfers to savings or investments found.",
    ),
    "baskets.trend": (
        [10],
        _trend_history,
        "Needs 3 earlier months of spending to show a trend.",
    ),
    "habits.weekend": (
        [11],
        lambda p: _get(p, "habits.weekend.share") is not None,
        "No spending in the last 3 full months.",
    ),
    "habits.night": (
        [12],
        lambda p: _get(p, "habits.night.share") is not None,
        "No spending in the last 3 full months.",
    ),
    "habits.impulse": (
        [13],
        lambda p: _get(p, "habits.impulse.bursts_per_month") is not None,
        "No spending in the last 3 full months.",
    ),
    "habits.payday_splurge": (
        [14],
        lambda p: _get(p, "habits.payday_splurge.ratio") is not None,
        "Needs a detected payday and spending around it.",
    ),
    "habits.loyalty": (
        [15],
        lambda p: _get(p, "habits.loyalty.label") is not None,
        "No spending in the last 3 full months.",
    ),
    "habits.spender_type": (
        [16],
        lambda p: _get(p, "habits.spender_type.label") is not None,
        "No spending in the last 3 full months.",
    ),
    "forecast.safe_to_spend_week": (
        [17],
        lambda p: _balance(p) and _payday(p),
        "Needs a detected payday to know how long the money must last.",
    ),
    "forecast.safe_to_save_today": (
        [18],
        lambda p: _balance(p) and _payday(p),
        "Needs a detected payday to forecast the balance.",
    ),
    "forecast.end_of_month": (
        [19],
        lambda p: _balance(p) and _payday(p),
        "Needs a balance and a detected payday.",
    ),
    "forecast.danger_days": (
        [20],
        lambda p: _balance(p) and _payday(p),
        "Needs a detected payday to forecast the days before it.",
    ),
    "forecast.upcoming_bills": (
        [21],
        lambda p: _nonempty(_get(p, "forecast.upcoming_bills")),
        "No regular bills due in the next 30 days.",
    ),
    "forecast.surprise_fund": (
        [22],
        lambda p: (_get(p, "forecast.surprise_fund_monthly") or 0) > 0,
        "No surprise expenses in the last 12 months.",
    ),
    "forecast.seasonal": (
        [23],
        lambda p: _get(p, "forecast.seasonal.ratio") is not None,
        "Needs a full year of spending history.",
    ),
    "whatif.category_cut": (
        [24],
        lambda p: _nonempty(_get(p, "whatif.category_means")),
        "No category spending in the last 3 full months.",
    ),
    "whatif.subscription_savings": (
        [25],
        lambda p: _nonempty(_get(p, "whatif.subscription_savings")),
        "No subscriptions to drop.",
    ),
    "whatif.goal_date": (
        [26],
        _saver_ever,
        "No regular saving yet, so a goal date cannot be estimated.",
    ),
    "whatif.habit_translation": (
        [27],
        lambda p: _nonempty(_get(p, "whatif.habit_translation")),
        "No leaky spending big enough to translate.",
    ),
    "levels": (
        [28, 29, 30, 31, 32],
        lambda p: _balance(p) and (_get(p, "income.monthly_income") or 0) > 0,
        "Needs income and a balance to place you on the ladder.",
    ),
    "levels.easiest_next_step": (
        [33],
        lambda p: _get(p, "levels.easiest_next_step") is not None,
        "No small cut in everyday spending closes the gap within 3 months.",
    ),
    "goals.recommended": (
        [44, 45, 46, 47, 48],
        lambda p: _get(p, "goals.recommended") is not None,
        "No goal to recommend at this level yet.",
    ),
    "goals.active": (
        [49, 50, 51, 52, 65, 66],
        lambda p: _nonempty(_get(p, "goals.active")),
        "No goals set yet.",
    ),
    "goals.detected": (
        [56, 57, 58, 59, 60, 61, 62],
        lambda p: _nonempty(_get(p, "goals.detected")),
        "No goal could be detected from the transactions.",
    ),
    "mortgage.loan_burden": (
        [76],
        lambda p: _get(p, "mortgage.loan_payments_found") is True,
        "No loan payments found in the transactions.",
    ),
    "mortgage.stress_test": (
        [77],
        lambda p: _get(p, "mortgage.stress_test") is not None,
        "Needs the loan balance, rate and years left from the user.",
    ),
    "mortgage.readiness": (
        [34, 35],
        lambda p: _get(p, "mortgage.readiness.score") is not None,
        "No mortgage readiness model has been fitted on applicant data.",
    ),
    "benchmarks.age": (
        [36],
        lambda p: _nonempty(_get(p, "benchmarks.age")),
        "No peer group of 20+ customers for this age band.",
    ),
    "benchmarks.area": (
        [37],
        lambda p: _nonempty(_get(p, "benchmarks.area")),
        "No peer group of 20+ customers for this area.",
    ),
    "multibank": (
        [41, 42, 43],
        lambda p: _real_accounts(p) > 1,
        "Only one bank account is connected.",
    ),
    "alerts": (
        [38, 39, 40] + list(range(76, 103)),
        lambda p: _nonempty(_get(p, "alerts")),
        "Nothing needs your attention right now.",
    ),
}


def availability(profile: dict) -> dict:
    """{item: {available, reason, inferences}} for every item in RULES."""
    out = {}
    for item, (numbers, check, reason) in RULES.items():
        try:
            ok = bool(check(profile))
        except (TypeError, ValueError):
            ok = False
        if not ok and callable(reason):
            reason = reason(profile)
        out[item] = {
            "available": ok,
            "reason": None if ok else reason,
            "inferences": numbers,
        }
    return out


def available(profile: dict, item: str) -> bool:
    """True when the stored availability (or a fresh check) allows `item`."""
    stored = (profile.get("availability") or {}).get(item)
    if stored is not None:
        return bool(stored.get("available"))
    return availability(profile).get(item, {}).get("available", False)
