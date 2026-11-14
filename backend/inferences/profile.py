"""build_profile: run every inference and return the profile_demo.json shape.

Pure: DataFrame in, plain dict out. Callers in coach/ add the database goals
afterwards with services.recompute_goals_locally (#51, #52, #65, #31), which
holds the single copy of the goal maths. Benchmarks (#36, #37) and mortgage
readiness (#34, #35) are not built yet and come out empty.
"""

from __future__ import annotations

import math

import pandas as pd

from . import alerts as alert_rules
from . import models
from .baskets import compute_baskets
from .common import iso, latest_balance, prepare, r2, to_date
from .detected_goals import detect_travel_goal
from .forecast import compute_forecast
from .habits import compute_habits
from .income import compute_income
from .levels import compute_levels
from .whatif import compute_whatif

# #36 age bands: (lowest age, label), checked from the top.
AGE_BANDS = ((55, "55+"), (40, "40-54"), (30, "30-39"), (25, "25-29"), (18, "18-24"))
AREA_DIGITS = 2  # #37: first 2 digits of the postcode
RECOMMENDED_GOAL_MONTHS = 5  # safety-net goal spread over 5 months


def age_band(age) -> str | None:
    if age is None or (isinstance(age, float) and math.isnan(age)):
        return None
    for lowest, label in AGE_BANDS:
        if age >= lowest:
            return label
    return None


def _customer(customer: dict) -> dict:
    postal = str(customer.get("postal_code") or "")
    age = customer.get("age")
    return {
        "age": age,
        "postal_code": postal,
        "age_band": age_band(age),
        "area": postal[:AREA_DIGITS] or None,
    }


def _recommended(levels: dict, baskets: dict) -> dict | None:
    """Next-level goal: the euros still missing for the next level."""
    to_go = levels.get("euros_to_go") or 0.0
    if not to_go or not levels.get("next"):
        return None
    monthly = models.monthly_needed(to_go, 0.0, RECOMMENDED_GOAL_MONTHS)
    rate = baskets.get("monthly_saving") or 0.0
    months = math.ceil(to_go / rate) if rate > 0 else None  # #26
    return {
        "id": f"rec-level-{levels['next']}",
        "type": "safety_net" if levels["next"] == 3 else "level",
        "for_level": levels["next"],
        "name": levels.get("next_name", ""),
        "target": r2(to_go),
        "monthly_needed": float(monthly),
        "difficulty": models.goal_difficulty(months),  # #49
        "weight": 0.5,
    }


def _detected(df: pd.DataFrame, today, baskets: dict) -> list[dict]:
    """#56 unnamed saving and #58 travel pot."""
    found = []
    saving = baskets.get("monthly_saving") or 0.0
    if saving > 0:
        found.append(
            {
                "id": "det-56",
                "inference": 56,
                "type": "savings",
                "text": "Looks like you're saving. Name it?",
                "monthly_amount": r2(saving),
            }
        )
    travel = detect_travel_goal(df, today)
    if travel:
        found.append({"id": "det-58", "type": "travel", **travel})
    return found


def _goals(df, today, levels, baskets, forecast) -> dict:
    step = levels.get("easiest_next_step") or {}
    cut_keys = ("category", "cut_pct", "monthly_saving")
    cuts = [{k: step[k] for k in cut_keys if k in step}] if step else []
    return {
        "recommended": _recommended(levels, baskets),
        "active": [],
        "detected": _detected(df, today, baskets),
        "clash": {
            "clash": False,
            "total_needed": 0.0,
            "safe_to_save_monthly": forecast.get("safe_to_save_today"),
        },
        "funding_cuts": cuts,
        "suggestion_weights": {},
        "success_score": None,
    }


def _mortgage(df: pd.DataFrame, today, income: dict) -> dict:
    """Loan payments and DSTI (#42, #76), whether or not alert #76 fires.

    stress_test (#77) needs the user's loan details: coach.services adds it.
    """
    payments = alert_rules.monthly_loan_payments(df, today) if len(df) else 0.0
    monthly = income.get("monthly_income") or 0.0
    dsti = r2(payments / monthly) if payments > 0 and monthly > 0 else None
    return {
        "loan_payments_found": payments > 0,
        "dsti": dsti,
        "stress_test": None,
        "readiness": None,
    }


def _multibank(df: pd.DataFrame, income: dict) -> dict:
    accounts = sorted(df["bank_account_id"].astype(str).unique()) if len(df) else []
    return {
        "accounts": [{"bank_account_id": a, "bank": "S-Bank"} for a in accounts],
        "true_income": income.get("monthly_income"),
        "hidden_loans": [],
        "duplicate_subscriptions": [],
    }


def build_profile(df, customer, today, goals=None, loans=None) -> dict:
    """profile JSON for one customer as of `today` (the reference date).

    goals: active goal dicts already carrying `on_track` (#31); others are
    added by the caller. loans: {balance, interest_rate, years_left} (#77).
    """
    today = to_date(today)
    df = prepare(df, today)
    income = compute_income(df, today)
    baskets = compute_baskets(df, today, income["bills"])
    forecast = compute_forecast(df, today, income, baskets)
    levels = compute_levels(df, today, income, baskets, goals=goals)
    profile = {
        "customer_id": customer.get("customer_id"),
        "generated_at": iso(today),
        "today": iso(today),
        "customer": _customer(customer),
        "balance": latest_balance(df),
        "income": income,
        "baskets": baskets,
        "habits": compute_habits(df, today, income, baskets),
        "forecast": forecast,
        "whatif": compute_whatif(df, today, income, baskets),
        "levels": levels,
        "goals": _goals(df, today, levels, baskets, forecast),
        "multibank": _multibank(df, income),
        "benchmarks": {
            "age": [],
            "area": [],
            "source": None,
            "excluded_partial_view": income.get("partial_view", False),
        },
    }
    profile["alerts"] = alert_rules.run_all_alerts(df, profile, today, loans=loans)
    profile["mortgage"] = _mortgage(df, today, income)
    return profile
