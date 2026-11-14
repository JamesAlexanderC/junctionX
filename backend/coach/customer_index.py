"""Customer index for the landing page: every customer's spender type (#16)
and app level (#28 to #33).

A full profile takes 0.6-2 s; the forecast and the mortgage model are a big
part of it and neither the spender type nor the level before goals needs
them. So this runs payday, bills (#1 to #6), baskets (#10), habits and the
levels in worker processes, and the result is cached as a ComputedArtifact.

The level is the one a customer has with no goals and no readiness score:
levels 4 (an on-track goal, #31) and 5 (readiness, #32) cannot be reached
here, so the index tops out at level 3, Safety net (#30).
"""

import os
from concurrent.futures import ProcessPoolExecutor

CHUNK = 25


def _init_worker():
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")
    django.setup()


def summarise(customer_id):
    """Spender type and app level of one customer, or an error row."""
    from coach import services
    from inferences.baskets import compute_baskets
    from inferences.common import prepare
    from inferences.habits import compute_habits
    from inferences.income import compute_income
    from inferences.levels import compute_levels

    try:
        today = services.as_of_date()
        df = prepare(services.transactions_df(customer_id), today)
        # Same steps as build_profile, so the level matches the profile's.
        income = compute_income(df, today)
        baskets = compute_baskets(df, today, bills=income["bills"])
        stype = compute_habits(df, today, income, baskets)["spender_type"]
        levels = compute_levels(df, today, income, baskets)
    except Exception as exc:  # noqa: BLE001 - one bad customer must not stop it
        return {"customer_id": customer_id, "error": str(exc)[:200]}
    return {
        "customer_id": customer_id,
        "spender_type": stype.get("label"),
        "spender_scores": stype.get("scores") or {},
        "level": levels["current"],
        "level_progress": levels["progress"],
    }


def summarise_all(ids, workers=None, progress=None):
    """Summaries for every id, in id order. workers=1 runs in this process."""
    workers = workers or os.cpu_count() or 1
    if workers == 1:
        rows = []
        for n, cid in enumerate(ids, 1):
            rows.append(summarise(cid))
            if progress:
                progress(n, len(ids))
        return rows
    from django.db import connections

    connections.close_all()
    rows = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
        for n, row in enumerate(pool.map(summarise, ids, chunksize=CHUNK), 1):
            rows.append(row)
            if progress and (n % 250 == 0 or n == len(ids)):
                progress(n, len(ids))
    return rows
