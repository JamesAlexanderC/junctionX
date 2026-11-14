"""Mortgage readiness and loan summary (context.md #34, #35, #76, #77).

#34: features per applicant from the 6 months before their application,
compared between approved and rejected applicants, then a logistic regression
on standardised features (scikit-learn). #35: the user's readiness score is the
model's predicted probability; gaps are ranked by coefficient x gap. With too
few applicants the score falls back to the mean percentile within the approved
group. Always guidance, never a loan decision.

The model is a plain dict (it holds a fitted sklearn pipeline, so it is not
JSON); fit it once per data load and pass it to compute_mortgage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import models
from . import thresholds as th
from .common import full_months, lowest_balance, monthly_totals, prepare, r2, spend

FEATURES = th.READINESS_FEATURES


# --- #34 features


def loan_outflows(df: pd.DataFrame) -> pd.DataFrame:
    """Spend rows with a loan / credit category or MCC (#76)."""
    s = spend(df)
    mask = s["category"].isin(th.LOAN_CATEGORIES) | s["mcc_code"].isin(th.LOAN_MCCS)
    return s[mask]


def monthly_loan_payments(df: pd.DataFrame, today, months: int = 3) -> float:
    """Mean monthly loan payments over the last full months."""
    df = prepare(df, today)
    window = full_months(today, months, df)
    if not window:
        return 0.0
    totals = monthly_totals(loan_outflows(df), window)
    return float(np.mean(list(totals.values())))


def features_for(df: pd.DataFrame, today, income=None, baskets=None) -> dict:
    """#34 feature vector as of `today` (application date or now).

    buffer_months (#30), saver_share (#75 / income), income_cv (#3),
    leaky_share and essentials_share (of total outflow, #9 / #7) and
    debt_share (loan payments / income), over the last 6 full months.
    """
    from .baskets import compute_baskets
    from .income import compute_income

    df = prepare(df, today)
    if income is None:
        income = compute_income(df, today)
    if baskets is None:
        baskets = compute_baskets(df, today, income.get("bills"))
    inc = income.get("monthly_income") or 0.0
    essentials = baskets.get("monthly_essentials") or 0.0
    low = lowest_balance(df, today) if len(df) else 0.0
    months = set(full_months(today, th.READINESS_FEATURE_MONTHS, df))
    hist = [h["totals"] for h in baskets.get("history", []) if h["month"] in months]
    totals = {
        b: sum(h.get(b, 0.0) for h in hist)
        for b in ("essential", "surprise", "leaky", "saver", "other")
    }
    outflow = sum(totals.values())
    n = max(1, len(hist))
    return {
        "buffer_months": r2(low / essentials) if essentials else 0.0,
        "saver_share": r2(totals["saver"] / n / inc) if inc else 0.0,
        "income_cv": (income.get("stability") or {}).get("cv") or 0.0,
        "leaky_share": r2(models.share(totals["leaky"], outflow)),
        "essentials_share": r2(models.share(totals["essential"], outflow)),
        "debt_share": (
            r2(monthly_loan_payments(df, today, th.READINESS_FEATURE_MONTHS) / inc)
            if inc
            else 0.0
        ),
    }


def applicant_features(tx_df: pd.DataFrame, applicants) -> pd.DataFrame:
    """Feature table for applicants: iterable of (customer_id, application_date,
    approved). Returns one row per applicant with FEATURES + approved."""
    rows = []
    for customer_id, applied, approved in applicants:
        sub = tx_df[tx_df["customer_id"] == customer_id]
        if not len(sub):
            continue
        f = features_for(sub, applied)
        f.update({"customer_id": customer_id, "approved": int(bool(approved))})
        rows.append(f)
    return pd.DataFrame(rows)


# --- #34 model


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[list(FEATURES)].astype(float).fillna(0.0)


def fit_readiness_model(features: pd.DataFrame, outcomes) -> dict:
    """Fit #34. Logistic regression with enough applicants of both classes,
    otherwise the percentile fallback (approved-group distributions only)."""
    X = _clean(features)
    y = np.asarray(list(outcomes), dtype=int)
    approved = X[y == 1]
    rejected = X[y == 0]
    base = {
        "approved_medians": (
            {f: float(approved[f].median()) for f in FEATURES}
            if len(approved)
            else {f: 0.0 for f in FEATURES}
        ),
        "rejected_medians": (
            {f: float(rejected[f].median()) for f in FEATURES} if len(rejected) else {}
        ),
        "approved_values": {f: approved[f].tolist() for f in FEATURES},
        "n_applicants": int(len(X)),
    }
    few = (
        len(X) < th.READINESS_MIN_APPLICANTS
        or len(approved) < th.READINESS_MIN_PER_CLASS
        or len(rejected) < th.READINESS_MIN_PER_CLASS
    )
    if few:
        return {**base, "method": "percentile_fallback", "auc": None}

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    folds = int(min(5, len(approved), len(rejected)))
    auc = float(np.mean(cross_val_score(pipe, X, y, cv=folds, scoring="roc_auc")))
    pipe.fit(X, y)
    scaler = pipe.named_steps["standardscaler"]
    lr = pipe.named_steps["logisticregression"]
    return {
        **base,
        "method": "logistic_regression",
        "auc": r2(auc),
        "pipeline": pipe,
        "mean": dict(zip(FEATURES, scaler.mean_.tolist())),
        "scale": dict(zip(FEATURES, scaler.scale_.tolist())),
        "coef": dict(zip(FEATURES, lr.coef_[0].tolist())),
        "intercept": float(lr.intercept_[0]),
    }


def _percentile(values: list, x: float, higher_better: bool) -> float:
    """F_j(x): share of approved applicants the user is at least as good as."""
    if not values:
        return 0.0
    arr = np.asarray(values, dtype=float)
    return float(np.mean(arr <= x) if higher_better else np.mean(arr >= x))


def readiness(user: dict, model: dict | None) -> dict:
    """#35 score, the top 2 gaps and the guidance note."""
    note = th.READINESS_NOTE
    if not model:
        return {"score": None, "method": "unavailable", "gaps": [], "note": note}
    med = model["approved_medians"]
    x = {f: float(user.get(f) or 0.0) for f in FEATURES}
    if model["method"] == "logistic_regression":
        row = pd.DataFrame([x])[list(FEATURES)]
        score = float(model["pipeline"].predict_proba(row)[0, 1])
        ranked = []
        for f in FEATURES:
            z_user = (x[f] - model["mean"][f]) / (model["scale"][f] or 1.0)
            z_med = (med[f] - model["mean"][f]) / (model["scale"][f] or 1.0)
            ranked.append((model["coef"][f] * (z_med - z_user), f))
    else:
        pct = {
            f: _percentile(
                model["approved_values"][f], x[f], f in th.READINESS_HIGHER_BETTER
            )
            for f in FEATURES
        }
        score = float(np.mean(list(pct.values())))
        ranked = []
        for f in FEATURES:
            better_high = f in th.READINESS_HIGHER_BETTER
            gap = (med[f] - x[f]) if better_high else (x[f] - med[f])
            ranked.append((gap / (abs(med[f]) or 1.0), f))
    gaps = [
        {"feature": f, "user": r2(x[f]), "approved_median": r2(med[f])}
        for g, f in sorted(ranked, reverse=True)
        if g > 0
    ][:2]
    return {
        "score": r2(score),
        "method": model["method"],
        "auc": model.get("auc"),
        "gaps": gaps,
        "note": note,
    }


# --- Section


def compute_mortgage(
    df: pd.DataFrame,
    today,
    income: dict,
    baskets: dict,
    forecast: dict | None = None,
    model: dict | None = None,
    loans: dict | None = None,
) -> dict:
    """profile["mortgage"]: loan burden (#76), stress test (#77), readiness."""
    df = prepare(df, today)
    inc = income.get("monthly_income") or 0.0
    loan_rows = loan_outflows(df) if len(df) else df
    recent = pd.Timestamp(today) - pd.Timedelta(days=92)
    found = bool(len(loan_rows) and (loan_rows["tx_date"] >= recent).any())
    payments = monthly_loan_payments(df, today) if found else 0.0
    dsti = r2(payments / inc) if found and inc else None
    stress = None
    if loans and loans.get("balance"):
        other = float(loans.get("other_payments") or 0.0)
        stressed = models.stressed_payment(float(loans["balance"])) + other
        ratio = stressed / inc if inc else None
        stress = {
            "stressed_payment": r2(stressed),
            "ratio": r2(ratio),
            "limit": 0.60,
            "passes": bool(ratio is not None and ratio <= 0.60),
        }
    user = features_for(df, today, income, baskets) if len(df) else {}
    return {
        "loan_payments_found": found,
        "monthly_loan_payments": r2(payments) if found else None,
        "dsti": dsti,
        "stress_test": stress,
        "loan_details": loans or None,
        "features": user,
        "readiness": readiness(user, model),
    }
