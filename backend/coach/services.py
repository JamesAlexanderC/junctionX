"""Profiles built on demand from the real transactions in the database.

There is no demo or fixture fallback: a customer that is not in the DB has no
profile (the API answers 404). Profiles are cached in the Profile table and
rebuilt when the inference code changes or a goal, loan or snooze changes.
"""

import hashlib
import logging
import pickle
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db.models import Case, Count, F, FloatField, Max, Min, Q, Sum, When

from .models import (
    AlertSnooze,
    ComputedArtifact,
    Customer,
    DismissedSuggestion,
    Goal,
    GoalRating,
    LoanDetails,
    Profile,
    Transaction,
)

log = logging.getLogger(__name__)

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
PEER_TABLE_KEY = "peer_table"
MORTGAGE_MODEL_KEY = "mortgage_model"
DEMO_CUSTOMERS_KEY = "demo_customers"
CUSTOMER_INDEX_KEY = "customer_index"


# --- dates ------------------------------------------------------------------


@lru_cache(maxsize=1)
def _dataset_as_of():
    return Transaction.objects.aggregate(last=Max("tx_date"))["last"]


def as_of_date():
    """The date every inference runs 'as of'.

    The S-Bank data ends 2026-09-30, so "today" is settings.AS_OF_DATE when
    set, otherwise the date of the last loaded transaction. (The day after
    would start an empty month, and every "this month" inference, such as the
    basket split, would then have nothing to show.)
    """
    if settings.AS_OF_DATE:
        return date.fromisoformat(settings.AS_OF_DATE)
    found = _dataset_as_of()
    if found is None:
        _dataset_as_of.cache_clear()  # nothing loaded yet; look again next time
        return date.today()
    return found


def reset_as_of_cache():
    _dataset_as_of.cache_clear()


def today():
    """'Today' for goals, snoozes, alerts and the chat: the dataset's as-of
    date (max tx_date unless AS_OF_DATE is set; P1.1 reference date)."""
    return as_of_date()


def profile_today(profile):
    raw = (profile or {}).get("today")
    return date.fromisoformat(raw) if raw else today()


# --- inference version ---------------------------------------------------------


@lru_cache(maxsize=1)
def inference_version():
    """Hash of the inference source, so cached profiles rebuild after changes."""
    root = Path(__file__).resolve().parent.parent / "inferences"
    digest = hashlib.sha1()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def profile_version():
    """Cache key for a stored profile: inference code + as-of date."""
    return f"{inference_version()}@{as_of_date().isoformat()}"


# --- customers and transactions ---------------------------------------------


def customer_exists(customer_id):
    return Customer.objects.filter(customer_id=customer_id).exists()


def list_customers(q=None, limit=50):
    qs = Customer.objects.order_by("customer_id")
    if q:
        qs = qs.filter(Q(customer_id__icontains=q) | Q(postal_code__startswith=q))
    return [
        {
            "customer_id": c.customer_id,
            "customer_age": c.age,
            "customer_postal_code": c.postal_code,
        }
        for c in qs[:limit]
    ]


def customer_money_stats():
    """Per customer: mean monthly income and spending, own-account transfers
    excluded (#2, #41), aggregated in the database."""
    import pandas as pd
    from inferences import thresholds as th

    own = Q(transaction_type__in=th.OWN_TRANSFER_TYPES)
    rows = (
        Transaction.objects.values("customer_id")
        .annotate(
            income=Sum(
                Case(
                    When(Q(tx_amount_eur__gt=0) & ~own, then=F("tx_amount_eur")),
                    default=0.0,
                    output_field=FloatField(),
                )
            ),
            spend=Sum(
                Case(
                    When(Q(tx_amount_eur__lt=0) & ~own, then=-F("tx_amount_eur")),
                    default=0.0,
                    output_field=FloatField(),
                )
            ),
            first=Min("tx_date"),
            last=Max("tx_date"),
            n=Count("tx_id"),
        )
        .order_by()
    )
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df
    days = (pd.to_datetime(df["last"]) - pd.to_datetime(df["first"])).dt.days + 1
    df["months"] = days / 30.44
    span = df["months"].clip(lower=1)
    df["monthly_income"] = df["income"] / span
    df["monthly_spend"] = df["spend"] / span
    return df


def build_customer_index(workers=None, progress=None):
    """Income level, spender type and app level for every customer, plus the
    demo picks (one per app level); both cached as artifacts."""
    import pandas as pd

    from inferences.demo import INCOME_LABELS, NO_INCOME_LABEL
    from inferences.demo import income_levels, level_name, pick_level_demos

    from .customer_index import summarise_all

    money = customer_money_stats()
    ids = list(Customer.objects.order_by("customer_id").values_list("pk", flat=True))
    summary = pd.DataFrame(summarise_all(ids, workers=workers, progress=progress))
    for col in ("spender_type", "spender_scores", "level", "level_progress"):
        if col not in summary:
            summary[col] = None
    if summary.empty:
        save_artifact(CUSTOMER_INDEX_KEY, data={"customers": []})
        save_artifact(DEMO_CUSTOMERS_KEY, data={"customers": []})
        return [], []
    if money.empty:
        money = pd.DataFrame(columns=["customer_id", "monthly_income", "months"])
    df = summary.merge(
        money[["customer_id", "monthly_income", "months"]], on="customer_id", how="left"
    )
    df["monthly_income"] = df["monthly_income"].fillna(0.0)
    df["months"] = df["months"].fillna(0.0)
    df["income_level"] = income_levels(df["monthly_income"])
    df["spender_scores"] = df["spender_scores"].apply(
        lambda s: s if isinstance(s, dict) else {}
    )
    demos = pick_level_demos(df)

    def clean(v):
        return None if pd.isna(v) else v

    index = [
        {
            "customer_id": r.customer_id,
            "income_level": int(r.income_level),
            "income_label": INCOME_LABELS.get(int(r.income_level), NO_INCOME_LABEL),
            "spender_type": clean(r.spender_type),
            "level": None if pd.isna(r.level) else int(r.level),
            "level_name": None if pd.isna(r.level) else level_name(r.level),
        }
        for r in df.itertuples()
    ]
    meta = {"as_of": str(as_of_date()), "built_with": inference_version()}
    save_artifact(CUSTOMER_INDEX_KEY, data={**meta, "customers": index})
    save_artifact(DEMO_CUSTOMERS_KEY, data={**meta, "customers": demos})
    return index, demos


def demo_directory():
    """Landing page data: demo picks and every customer with their tags.
    built is False until build_customer_index has run."""
    rows = dict(
        ComputedArtifact.objects.filter(
            key__in=[CUSTOMER_INDEX_KEY, DEMO_CUSTOMERS_KEY]
        ).values_list("key", "data")
    )
    if CUSTOMER_INDEX_KEY not in rows:
        return {"built": False, "demos": [], "customers": []}
    known = set(Customer.objects.values_list("pk", flat=True))
    index = [c for c in rows[CUSTOMER_INDEX_KEY].get("customers", [])]
    demos = rows.get(DEMO_CUSTOMERS_KEY, {}).get("customers", [])
    return {
        "built": True,
        "as_of": rows[CUSTOMER_INDEX_KEY].get("as_of"),
        "demos": [d for d in demos if d["customer_id"] in known],
        "customers": [c for c in index if c["customer_id"] in known],
    }


def transactions_df(customer_id):
    """Transactions for one customer as the CLAUDE.md DataFrame, or None."""
    import pandas as pd

    rows = list(
        Transaction.objects.filter(customer_id=customer_id).values(
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
    )
    if not rows:
        return None
    return _frame(pd.DataFrame(rows))


def _frame(df):
    import pandas as pd

    df = df.rename(columns={"account_id": "bank_account_id"})
    df["tx_date"] = pd.to_datetime(df["tx_date"])
    ts = pd.to_datetime(df["tx_timestamp"], utc=True)
    df["tx_timestamp"] = ts.dt.tz_localize(None)
    df["mcc_code"] = df["mcc_code"].astype(str)
    return df[TX_COLUMNS].sort_values(["tx_timestamp", "tx_id"]).reset_index(drop=True)


def all_transactions_df():
    """Every loaded transaction (for the dataset-wide artifacts)."""
    import pandas as pd
    from django.db import connection

    if connection.vendor == "postgresql":
        import io

        cols = (
            "tx_id, customer_id, account_id, tx_date, tx_timestamp, category, "
            "tx_amount_eur, balance_after_eur, transaction_type, merchant_id, "
            "mcc_code"
        )
        buf = io.BytesIO()
        with connection.cursor() as cur:
            with cur.cursor.copy(
                f"COPY (SELECT {cols} FROM coach_transaction) TO STDOUT "
                "WITH (FORMAT csv, HEADER)"
            ) as copy:
                for block in copy:
                    buf.write(block)
        buf.seek(0)
        df = pd.read_csv(
            buf,
            dtype={
                "customer_id": "category",
                "account_id": "category",
                "category": "category",
                "transaction_type": "category",
                "merchant_id": str,
                "mcc_code": str,
            },
            keep_default_na=False,
            na_values={"balance_after_eur": [""]},
        )
        return _frame(df)
    rows = list(Transaction.objects.values())
    if not rows:
        return pd.DataFrame(columns=TX_COLUMNS)
    df = pd.DataFrame(rows).rename(columns={"id": "tx_id"})
    return _frame(df)


def empty_df():
    import pandas as pd

    return pd.DataFrame(columns=TX_COLUMNS)


def customer_dict(customer_id):
    c = Customer.objects.filter(customer_id=customer_id).first()
    return {
        "customer_id": customer_id,
        "age": c.age if c else None,
        "postal_code": c.postal_code if c else "",
    }


# --- user state ---------------------------------------------------------------


def goal_dicts(customer_id):
    return [
        g.as_dict()
        for g in Goal.objects.filter(customer_id=customer_id).exclude(
            status="abandoned"
        )
    ]


def ratings(customer_id):
    return [
        {"goal_type": r.goal_type, "rating": "up" if r.up else "down"}
        for r in GoalRating.objects.filter(customer_id=customer_id)
    ]


def dismissed_ids(customer_id):
    """Detected-goal suggestion ids the user dismissed (#56 to #62)."""
    return sorted(
        DismissedSuggestion.objects.filter(customer_id=customer_id).values_list(
            "suggestion_id", flat=True
        )
    )


def latest_loan(customer_id):
    loan = LoanDetails.objects.filter(customer_id=customer_id).last()
    return loan.as_dict() if loan else None


def snoozes(customer_id, on=None):
    on = on or today()
    return {
        s.alert_id: s.until.isoformat()
        for s in AlertSnooze.objects.filter(customer_id=customer_id, until__gt=on)
    }


def snoozed_ids(customer_id, on=None):
    return set(snoozes(customer_id, on))


# --- dataset-wide artifacts ----------------------------------------------------


def peer_table():
    row = ComputedArtifact.objects.filter(key=PEER_TABLE_KEY).first()
    return row.data if row else None


def mortgage_model():
    row = ComputedArtifact.objects.filter(key=MORTGAGE_MODEL_KEY).first()
    if row is None or row.blob is None:
        return None
    try:
        return pickle.loads(bytes(row.blob))
    except Exception:  # noqa: BLE001 - a stale pickle must not break profiles
        log.exception("Could not load the mortgage model; rebuild_artifacts needed")
        return None


def save_artifact(key, data=None, blob=None):
    ComputedArtifact.objects.update_or_create(
        key=key, defaults={"data": data or {}, "blob": blob}
    )


# --- profiles -------------------------------------------------------------------


def build(customer_id):
    """Run every inference for one customer (no caching)."""
    from inferences.profile import build_profile

    return build_profile(
        transactions_df(customer_id),
        customer_dict(customer_id),
        as_of_date(),
        goals=goal_dicts(customer_id),
        loans=latest_loan(customer_id),
        ratings=ratings(customer_id),
        dismissed=dismissed_ids(customer_id),
        peer_table=peer_table(),
        mortgage_model=mortgage_model(),
        # Snoozes are applied when reading (active_alerts), not baked into the
        # cached profile, so an alert comes back when its snooze ends.
    )


def get_profile(customer_id):
    """The customer's profile, built on demand and cached. None if unknown."""
    if not customer_exists(customer_id):
        return None
    version = profile_version()
    row = Profile.objects.filter(customer_id=customer_id).first()
    if row is not None and row.built_with == version:
        return row.data
    data = build(customer_id)
    Profile.objects.update_or_create(
        customer_id=customer_id, defaults={"data": data, "built_with": version}
    )
    return data


def invalidate(customer_id):
    Profile.objects.filter(customer_id=customer_id).delete()


def refresh_profile(customer_id):
    """Rebuild after a goal, rating, loan or snooze change."""
    invalidate(customer_id)
    return get_profile(customer_id)


# --- alerts -------------------------------------------------------------------


def alert_priority(alert, on):
    """priority = w_severity / max(1, days until impact) (Alert coach)."""
    weight = SEVERITY_WEIGHT.get(alert.get("severity"), 1)
    impact = alert.get("impact_date")
    days = 1
    if impact:
        days = (date.fromisoformat(str(impact)[:10]) - on).days
    return weight / max(1, days)


def active_alerts(customer_id, profile, on=None, limit=None):
    """Profile alerts minus snoozed ones, sorted by priority (highest first).

    With ``limit``, only the first ``limit`` of them (screens; chat sees all).
    """
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
    ranked = sorted(alerts, key=lambda a: a["priority"], reverse=True)
    return ranked if limit is None else ranked[:limit]


def add_days(on, days):
    return on + timedelta(days=days)
