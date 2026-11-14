"""Benchmarks: compared with your age group and area (context.md #36, #37).

Peer value = median monthly spend per category within the group (customers
with no spend in a category count as 0). Ratio = user / peer median, flagged
above 1.2 or below 0.8. Groups need at least 20 customers. The peer table is
computed once over all customers (compute_peer_table) and reused.
"""

from __future__ import annotations

import pandas as pd

from . import thresholds as th
from .common import full_months, prepare, r2, safe_div, spend

SOURCE = "S-Bank synthetic customers (peer groups of 20+)"


def age_band(age) -> str | None:
    """18-24, 25-29, 30-39, 40-54, 55+."""
    if age is None or pd.isna(age):
        return None
    age = int(age)
    for lo, hi in th.AGE_BANDS:
        if lo <= age <= hi:
            return f"{lo}+" if hi >= 200 else f"{lo}-{hi}"
    return None


def area(postal_code) -> str | None:
    """First 2 digits of the postcode."""
    code = str(postal_code or "").strip()
    if not code or code.lower() == "nan":
        return None
    return code.zfill(5)[:2]


def category_monthly(df: pd.DataFrame, today) -> dict:
    """Mean monthly spend per category over the last 3 full months."""
    df = prepare(df, today)
    months = full_months(today, th.WINDOW_FULL_MONTHS, df)
    if not months:
        return {}
    s = spend(df)
    s = s[s["month"].isin(months)]
    return (s.groupby("category")["amount"].sum() / len(months)).to_dict()


def compute_peer_table(all_df: pd.DataFrame, customers_meta, today) -> dict:
    """Median monthly category spend per age band and per area.

    customers_meta: DataFrame or list of dicts with customer_id,
    customer_age, customer_postal_code.
    """
    meta = pd.DataFrame(customers_meta)
    per_customer = {
        cid: category_monthly(g, today) for cid, g in all_df.groupby("customer_id")
    }
    wide = pd.DataFrame.from_dict(per_customer, orient="index").fillna(0.0)
    meta = meta.set_index("customer_id")
    meta = meta[meta.index.isin(wide.index)]
    groups = {
        "age": meta["customer_age"].map(age_band),
        "area": meta["customer_postal_code"].map(area),
    }
    table = {"today": str(pd.Timestamp(today).date()), "age": {}, "area": {}}
    for kind, keys in groups.items():
        for key, ids in keys.groupby(keys).groups.items():
            sub = wide.loc[list(ids)]
            table[kind][str(key)] = {
                "n": int(len(sub)),
                "medians": {c: r2(v) for c, v in sub.median().items()},
            }
    return table


def _compare(user: dict, group: dict | None) -> list[dict]:
    if not group or group["n"] < th.PEER_MIN_CUSTOMERS:
        return []
    rows = []
    for cat, peer in group["medians"].items():
        mine = float(user.get(cat, 0.0))
        if not peer and not mine:
            continue
        ratio = safe_div(mine, peer, default=None)
        flag = None
        if ratio is not None:
            if ratio > th.PEER_ABOVE:
                flag = "above"
            elif ratio < th.PEER_BELOW:
                flag = "below"
        rows.append(
            {
                "category": cat,
                "user": r2(mine),
                "peer_median": r2(peer),
                "ratio": r2(ratio),
                "flag": flag,
            }
        )
    return sorted(rows, key=lambda r: -(r["user"] or 0))


def compute_benchmarks(user_df, customer: dict, peer_table: dict | None, today):
    """profile["benchmarks"] (#36 age band, #37 area)."""
    band = age_band((customer or {}).get("age"))
    ar = area((customer or {}).get("postal_code"))
    user = category_monthly(user_df, today) if len(user_df) else {}
    table = peer_table or {"age": {}, "area": {}}
    age_group = table["age"].get(band)
    area_group = table["area"].get(ar)
    return {
        "age": _compare(user, age_group),
        "area": _compare(user, area_group),
        "age_band": band,
        "area_code": ar,
        "age_group_size": (age_group or {}).get("n", 0),
        "area_group_size": (area_group or {}).get("n", 0),
        "source": SOURCE,
    }
