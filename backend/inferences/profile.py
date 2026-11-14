"""Build one customer profile (context.md P1.6).

build_profile runs every inference in dependency order and returns the dict
whose shape is shared/fixtures/profile_demo.json. Every number the app shows
comes from here; Gemini only explains it.

Order: income -> baskets -> habits, forecast, whatif -> mortgage -> active
goals (#52 on track) -> levels (#31 needs goals, #32 needs readiness) ->
goals section (#44 to #48 need the level) -> benchmarks, multibank -> alerts
(they read the finished profile) -> availability (which items the
customer's data supports; see availability.py).
"""

from __future__ import annotations

import copy
import math
from datetime import date

import pandas as pd

from . import alerts as alerts_mod
from .availability import availability
from . import goals as goals_mod
from .baskets import compute_baskets
from .spending import compute_spending
from .benchmarks import age_band, area, compute_benchmarks
from .common import COLUMNS, iso, latest_balance, prepare, r2, to_date
from .forecast import compute_forecast
from .habits import compute_habits
from .income import compute_income
from .levels import compute_levels
from .mortgage import compute_mortgage
from .multibank import compute_multibank
from .whatif import compute_whatif


def _customer(customer: dict | None) -> dict:
    """Accepts {customer_id, age, postal_code} (or the CSV column names)."""
    c = customer or {}
    age = c.get("age", c.get("customer_age"))
    postal = c.get("postal_code", c.get("customer_postal_code"))
    age = None if age is None or pd.isna(age) else int(age)
    postal = None if postal is None or pd.isna(postal) else str(postal)
    return {
        "age": age,
        "postal_code": postal,
        "age_band": age_band(age),
        "area": area(postal),
    }


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def _readiness_score(mortgage: dict):
    return ((mortgage or {}).get("readiness") or {}).get("score")


def _goals_and_levels(df, today, profile, goals, ratings, dismissed, loans):
    """#28 to #33 and #44 to #74 from the profile's other sections."""
    income, baskets, forecast = (
        profile["income"],
        profile["baskets"],
        profile["forecast"],
    )
    active = goals_mod.evaluate_goals(goals, today, baskets, forecast)
    levels = compute_levels(
        df,
        today,
        income,
        baskets,
        goals=active,
        readiness=_readiness_score(profile.get("mortgage")),
    )
    section = goals_mod.compute_goals(
        df,
        today,
        income,
        baskets,
        forecast,
        levels,
        profile.get("whatif"),
        goals=goals,
        ratings=ratings,
        dismissed=dismissed,
        customer=profile.get("customer"),
        mortgage=profile.get("mortgage"),
        loans=loans,
    )
    return levels, section


def build_profile(
    df: pd.DataFrame | None,
    customer: dict | None,
    today,
    goals: list[dict] | None = None,
    loans: dict | None = None,
    ratings=None,
    dismissed=None,
    peer_table: dict | None = None,
    mortgage_model: dict | None = None,
    snoozed: dict | None = None,
) -> dict:
    """Full profile for one customer as of `today` (JSON-serialisable).

    customer: {customer_id, age, postal_code}. goals: Goal rows as dicts.
    loans: {balance, interest_rate, years_left, other_payments?} (#77, #82).
    ratings: {goal_type: {up, down}} (#54). dismissed: detected-goal ids.
    peer_table: benchmarks.compute_peer_table output. mortgage_model:
    mortgage.fit_readiness_model output. snoozed: {alert_id: until date}.
    """
    today = to_date(today)
    df = _empty_df() if df is None or not len(df) else df
    prepared = prepare(df, today)
    cust = _customer(customer)
    customer_id = (customer or {}).get("customer_id")
    if customer_id is None and len(prepared):
        customer_id = str(prepared["customer_id"].iloc[0])

    income = compute_income(prepared, today)
    baskets = compute_baskets(prepared, today, bills=income["bills"])
    habits = compute_habits(prepared, today, income, baskets)
    forecast = compute_forecast(prepared, today, income, baskets)
    whatif = compute_whatif(prepared, today, income, baskets)
    mortgage = compute_mortgage(
        prepared, today, income, baskets, forecast, model=mortgage_model, loans=loans
    )
    profile = {
        "customer_id": customer_id,
        "generated_at": date.today().isoformat(),
        "today": iso(today),
        "customer": cust,
        "balance": r2(latest_balance(prepared)) if len(prepared) else None,
        "income": income,
        "baskets": baskets,
        "spending": compute_spending(df, today, whatif.get("category_means")),
        "habits": habits,
        "forecast": forecast,
        "whatif": whatif,
        "mortgage": mortgage,
    }
    levels, goals_section = _goals_and_levels(
        prepared, today, profile, goals, ratings, dismissed, loans
    )
    profile["levels"] = levels
    profile["goals"] = goals_section
    profile["benchmarks"] = compute_benchmarks(prepared, cust, peer_table, today)
    profile["multibank"] = compute_multibank(prepared, today)
    # No transactions -> nothing to alert about (not "balance EUR 0").
    profile["alerts"] = (
        alerts_mod.run_all_alerts(
            prepared, profile, today, loans=loans, snoozed=snoozed
        )
        if len(prepared)
        else []
    )
    # Which items the data supports, so the API shows only given insights.
    profile["availability"] = availability(profile)
    return _jsonable(profile)


def recompute_goals_and_levels(
    profile: dict,
    df: pd.DataFrame | None,
    today,
    goals: list[dict] | None,
    ratings=None,
    dismissed=None,
    loans: dict | None = None,
    snoozed: dict | None = None,
) -> dict:
    """After a goal is created, edited, paused or rated: rerun the goal and
    level inferences (#28 to #33, #44 to #74) and the alerts on a copy of the
    stored profile. Other sections are reused as they are."""
    today = to_date(today)
    df = _empty_df() if df is None or not len(df) else df
    prepared = prepare(df, today)
    out = copy.deepcopy(profile)
    out["today"] = iso(today)
    levels, section = _goals_and_levels(
        prepared, today, out, goals, ratings, dismissed, loans
    )
    out["levels"] = levels
    out["goals"] = section
    # Without transactions only the profile-based rules (#20, #50, #52, #70,
    # #99, ...) can run; they read the stored sections.
    out["alerts"] = alerts_mod.run_all_alerts(
        prepared if len(prepared) else None,
        out,
        today,
        loans=loans,
        snoozed=snoozed,
    )
    out["availability"] = availability(out)
    return _jsonable(out)


def _jsonable(obj):
    """Plain JSON types only: numpy / pandas scalars unwrapped, NaN / inf ->
    None, dates -> ISO strings, sets -> sorted lists."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        items = sorted(obj) if isinstance(obj, (set, frozenset)) else obj
        return [_jsonable(v) for v in items]
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        obj = obj.item()
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if obj is pd.NaT:
        return None
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
