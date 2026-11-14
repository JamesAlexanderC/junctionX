"""Goals detected from the data (context.md #58).

The profile builder puts these under profile["goals"]["detected"], which the
get_detected_goals Gemini tool reads.
"""

from __future__ import annotations

import pandas as pd

from . import thresholds as th
from .common import prepare, r2, spend, to_date


def _months_until(today, month: int) -> int:
    """Months from today's month to the next time `month` comes round (1-12)."""
    ahead = (month - today.month) % 12
    return ahead or 12


def detect_travel_goal(df: pd.DataFrame, today) -> dict | None:
    """#58: last 12 months' travel spend > EUR 300 -> suggest a holiday pot.

    Travel = category == travel (P1.1 decision). Season = month with the most
    travel spend; pot per month = last year's spend / months until that month.
    """
    today = to_date(today)
    s = spend(prepare(df, today))
    start = pd.Timestamp(today) - pd.DateOffset(months=th.TRAVEL_LOOKBACK_MONTHS)
    trips = s[(s["category"] == th.TRAVEL_CATEGORY) & (s["tx_date"] > start)]
    total = float(trips["amount"].sum())
    if total <= th.TRAVEL_GOAL_MIN_EUR:
        return None
    season = int(trips.groupby(trips["tx_date"].dt.month)["amount"].sum().idxmax())
    months = _months_until(today, season)
    return {
        "inference": 58,
        "name": "Holiday pot",
        "category": th.TRAVEL_CATEGORY,
        "last_year_spend": r2(total),
        "season_month": season,
        "months_until": months,
        "target": r2(total),
        "monthly_needed": r2(total / months),
    }
