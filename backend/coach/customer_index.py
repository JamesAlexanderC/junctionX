"""Customer index for the landing page: every customer's spender type (#16).

A full profile takes 0.6-2 s, mostly bill detection (#4), the forecast and
the mortgage model. The spender type needs none of them: only payday dates
(#1) and the basket totals (#10), whose saver share does not depend on which
outflows are bills. So this runs just those steps (~0.15 s a customer, the
same label as the full profile) in worker processes, and the result is cached
as a ComputedArtifact.
"""

import os
from concurrent.futures import ProcessPoolExecutor

CHUNK = 25


def _init_worker():
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")
    django.setup()


def summarise(customer_id):
    """Spender type of one customer, or an error row."""
    from coach import services
    from inferences.baskets import compute_baskets
    from inferences.common import prepare
    from inferences.habits import compute_habits
    from inferences.income import detect_payday

    try:
        today = services.as_of_date()
        df = prepare(services.transactions_df(customer_id), today)
        income = {"payday": detect_payday(df, today)}
        # bills=[] only moves outflows between Essential and Surprise; the
        # saver share and total outflow the spender type uses are unchanged.
        baskets = compute_baskets(df, today, bills=[])
        stype = compute_habits(df, today, income, baskets)["spender_type"]
    except Exception as exc:  # noqa: BLE001 - one bad customer must not stop it
        return {"customer_id": customer_id, "error": str(exc)[:200]}
    return {
        "customer_id": customer_id,
        "spender_type": stype.get("label"),
        "spender_scores": stype.get("scores") or {},
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
