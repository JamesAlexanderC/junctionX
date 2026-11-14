"""Goals, mortgage, benchmarks, multibank and build_profile (context.md
#34 to #37, #41 to #74, P1.5, P1.6)."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from inferences import benchmarks, goals, models, mortgage, multibank
from inferences.common import income_inflows, prepare
from inferences.profile import build_profile, recompute_goals_and_levels
from inferences.tests.fixtures import TODAY, aino_df, make_df

DEMO = Path(__file__).resolve().parents[3] / "shared" / "fixtures"
DEMO_PROFILE = json.loads((DEMO / "profile_demo.json").read_text())
AINO = {"customer_id": "C-AINO", "age": 24, "postal_code": "00510"}
JAPAN = {
    "id": 1,
    "name": "Japan trip",
    "type": "custom",
    "target": 1500,
    "saved": 640,
    "start_date": "2026-07-01",
    "target_date": "2027-06-01",
    "priority": "high",
    "status": "active",
}


# --- Goals (#26, #49, #52, #56, #65 and friends)


def test_goal_date_and_difficulty():
    # #26 1,500 target, 640 saved, 150 a month -> 6 months; #49 Stretch.
    d = goals.difficulty(1500, 640, 150)
    assert d == {"months_needed": 6, "difficulty": "Stretch"}


def test_goal_not_reachable_is_hard():
    assert goals.difficulty(1500, 640, 0) == {
        "months_needed": None,
        "difficulty": "Hard",
    }


def test_monthly_needed_rounds_up_to_5():
    # #65 1,500 target, 640 saved, 10 months -> 86 -> 90.
    assert goals.monthly_needed(1500, 640, "2026-10-18", "2027-08-18") == 90.0


def test_realism_suggests_realistic_amount_and_date():
    # #50 / #66: needs 200 a month, can safely save 100 -> later date.
    r = goals.realism(200, 1500, 500, date(2026, 10, 18), 100)
    assert r["realistic"] is False
    assert r["suggested_monthly"] == 100
    assert r["suggested_date"] == "2027-08-18"  # ceil(1000 / 100) = 10 months


def test_on_track_and_paused_never_off_track():
    g = dict(JAPAN, saved=100)  # 6.7% done, ~32% expected
    assert goals.progress(g, TODAY)["on_track"] is False
    paused = dict(g, paused=True, paused_at="2026-07-02")
    p = goals.progress(paused, TODAY)
    assert p["on_track"] is True
    assert p["expected_pct"] < 1  # dates frozen at paused_at


def test_coaching_tip_when_off_track():
    g = dict(JAPAN, saved=100)
    bsk = {
        "monthly_saving": 150,
        "leaky_categories": [{"category": "takeaway", "monthly_total": 90.0}],
    }
    ev = goals.evaluate_goal(g, TODAY, bsk, {"safe_to_save_today": 0})
    assert ev["on_track"] is False
    assert ev["tip"]["category"] == "takeaway"
    assert ev["tip"]["shortfall"] > 0


def test_milestones_once_each():
    m = goals.milestones(52, [25])
    assert m["milestones_hit"] == [25, 50]
    assert m["new_milestones"] == [50]


def test_laplace_weights_and_user_goals():
    w = goals.suggestion_weights({"safety_net": {"up": 1, "down": 0}}, [JAPAN])
    assert w["safety_net"] == pytest.approx(0.67, abs=0.01)  # (1+1)/(1+0+2)
    assert w["custom"] == pytest.approx(0.67, abs=0.01)  # #74 +1 up
    assert w["wealth"] == 0.5


def test_success_score():
    hist = [{"status": "completed"}, {"status": "abandoned"}, {"status": "abandoned"}]
    assert goals.success_score(hist) == pytest.approx(0.33, abs=0.01)
    assert goals.success_score([]) is None


def test_priority_split_and_clash():
    gs = [
        {"id": 1, "name": "A", "priority": "high", "monthly_needed": 100},
        {"id": 2, "name": "B", "priority": "low", "monthly_needed": 80},
    ]
    split = goals.priority_split(gs, 120)
    assert [s["amount"] for s in split] == [90.0, 30.0]
    c = goals.clash(gs, 120)
    assert c["clash"] is True and c["total_needed"] == 180


def test_savings_goal_detected_on_aino():
    # #56: regular 150 transfers with CV 0.
    inc = {"bills": [], "monthly_income": 2000}
    found = goals.detected_goals(aino_df(until=TODAY), TODAY, inc)
    det = [g for g in found if g["inference"] == 56]
    assert det and det[0]["monthly_amount"] == 150.0


def test_dismissed_detected_goal_not_shown():
    inc = {"bills": [], "monthly_income": 2000}
    found = goals.detected_goals(aino_df(until=TODAY), TODAY, inc, dismissed=["det-56"])
    assert all(g["id"] != "det-56" for g in found)


def test_recommended_goal_for_safety_net():
    # #45: target = essentials - lowest balance, rounded up to EUR 50.
    lv = {"next": 3, "lowest_balance_30d": 445.0}
    bsk = {"monthly_essentials": 890.0, "monthly_saving": 150.0}
    rec = goals.recommended_goal(lv, {"monthly_income": 2000}, bsk, {})
    assert rec["type"] == "safety_net" and rec["target"] == 450.0


# --- Mortgage (#34, #35, #76, #77)


def _applicants(n_good, n_bad, seed=0):
    rng = np.random.default_rng(seed)

    def rows(n, buf, saver, debt):
        return [
            {
                "buffer_months": rng.normal(buf, 0.3),
                "saver_share": rng.normal(saver, 0.02),
                "income_cv": abs(rng.normal(0.1, 0.03)),
                "leaky_share": rng.normal(0.12, 0.02),
                "essentials_share": rng.normal(0.6, 0.05),
                "debt_share": abs(rng.normal(debt, 0.03)),
            }
            for _ in range(n)
        ]

    feats = pd.DataFrame(rows(n_good, 3.0, 0.12, 0.05) + rows(n_bad, 0.5, 0.02, 0.3))
    return feats, [1] * n_good + [0] * n_bad


def test_logistic_readiness_model():
    feats, y = _applicants(30, 30)
    model = mortgage.fit_readiness_model(feats, y)
    assert model["method"] == "logistic_regression"
    assert model["auc"] > 0.9
    weak = {
        "buffer_months": 0.5,
        "saver_share": 0.02,
        "income_cv": 0.1,
        "leaky_share": 0.12,
        "essentials_share": 0.6,
        "debt_share": 0.3,
    }
    r = mortgage.readiness(weak, model)
    assert r["score"] < 0.5
    assert len(r["gaps"]) == 2
    assert r["note"] == "Guidance only, not a loan decision."
    strong = dict(weak, buffer_months=3.0, saver_share=0.12, debt_share=0.05)
    assert mortgage.readiness(strong, model)["score"] > 0.5


def test_percentile_fallback_with_few_applicants():
    feats, y = _applicants(6, 3)
    model = mortgage.fit_readiness_model(feats, y)
    assert model["method"] == "percentile_fallback"
    user = {
        "buffer_months": 0.5,
        "saver_share": 0.02,
        "income_cv": 0.1,
        "leaky_share": 0.12,
        "essentials_share": 0.6,
        "debt_share": 0.3,
    }
    r = mortgage.readiness(user, model)
    assert 0 <= r["score"] <= 1
    assert r["gaps"][0]["feature"] in {"buffer_months", "saver_share", "debt_share"}


def test_mortgage_without_loans_or_model():
    from inferences.baskets import compute_baskets
    from inferences.income import compute_income

    df = aino_df(until=TODAY)
    inc = compute_income(df, TODAY)
    bsk = compute_baskets(df, TODAY, inc["bills"])
    m = mortgage.compute_mortgage(df, TODAY, inc, bsk)
    assert m["loan_payments_found"] is False
    assert m["dsti"] is None and m["stress_test"] is None
    assert m["readiness"]["score"] is None


def test_stress_test_with_loan_details():
    from inferences.baskets import compute_baskets
    from inferences.income import compute_income

    df = aino_df(until=TODAY)
    inc = compute_income(df, TODAY)
    bsk = compute_baskets(df, TODAY, inc["bills"])
    m = mortgage.compute_mortgage(df, TODAY, inc, bsk, loans={"balance": 150000})
    assert m["stress_test"]["stressed_payment"] == pytest.approx(966.45, abs=0.01)
    assert m["stress_test"]["passes"] is True  # 48% of 2,000


# --- Benchmarks (#36, #37)


def _peer_customers(n, age, postal, takeaway):
    frames, meta = [], []
    for i in range(n):
        cid = f"P{age}-{postal}-{i}"
        meta.append(
            {"customer_id": cid, "customer_age": age, "customer_postal_code": postal}
        )
        rows = [
            {
                "ts": f"2026-{m:02d}-10 12:00",
                "amount": -takeaway,
                "category": "takeaway",
                "merchant": "M_WOLT",
                "tx_id": f"{cid}-{m}",
            }
            for m in (7, 8, 9)
        ]
        frames.append(make_df(rows, customer=cid))
    return pd.concat(frames, ignore_index=True), meta


def test_benchmarks_need_20_customers():
    big, big_meta = _peer_customers(20, 24, "00510", 60.0)
    small, small_meta = _peer_customers(5, 24, "33100", 60.0)
    all_df = pd.concat([big, small], ignore_index=True)
    table = benchmarks.compute_peer_table(all_df, big_meta + small_meta, TODAY)
    assert table["age"]["18-24"]["n"] == 25
    assert table["area"]["33"]["n"] == 5

    user = aino_df(until=TODAY)  # takeaway 90 a month vs peers 60
    cust = {"age": 24, "postal_code": "00510"}
    out = benchmarks.compute_benchmarks(user, cust, table, TODAY)
    row = next(r for r in out["age"] if r["category"] == "takeaway")
    assert row["ratio"] == 1.5 and row["flag"] == "above"
    tampere = benchmarks.compute_benchmarks(
        user, {"age": 24, "postal_code": "33100"}, table, TODAY
    )
    assert tampere["area"] == []  # only 5 customers in area 33


def test_age_bands():
    assert benchmarks.age_band(18) == "18-24"
    assert benchmarks.age_band(29) == "25-29"
    assert benchmarks.age_band(60) == "55+"
    assert benchmarks.age_band(None) is None


# --- Multibank (#41 to #43)


def test_own_account_transfer_not_income():
    # #41: -300 from account A and +300 into account B the same day.
    df = make_df(
        [
            {
                "ts": "2026-10-05 10:00",
                "amount": -300,
                "account": "A",
                "ttype": "transfer",
                "merchant": "X",
            },
            {
                "ts": "2026-10-05 10:05",
                "amount": 300,
                "account": "B",
                "ttype": "transfer",
                "merchant": "X",
            },
        ]
    )
    assert income_inflows(prepare(df)).empty


def test_mock_nordea_hidden_loan_and_true_income():
    rows = [
        {
            "ts": f"2026-{m:02d}-25 06:00",
            "amount": 2000,
            "merchant": "EMP",
            "category": "salary",
            "ttype": "incoming_transfer",
        }
        for m in (7, 8, 9, 10)
    ] + [
        {
            "ts": f"2026-{m:02d}-05 06:00",
            "amount": -210,
            "merchant": "CARLOAN",
            "category": "loan",
            "mcc": "6141",
            "ttype": "direct_debit",
        }
        for m in (7, 8, 9, 10)
    ]
    df = multibank.mock_second_account(make_df(rows), ["CARLOAN"])
    out = multibank.compute_multibank(df, date(2026, 10, 28))
    banks = {a["bank"] for a in out["accounts"]}
    assert banks == {"S-Bank", "Nordea"}
    assert any(a["synthetic"] for a in out["accounts"])
    assert out["hidden_loans"][0]["amount"] == 210.0
    assert out["true_income"] == 2000.0


def test_relabel_account():
    df = multibank.relabel_account_as_mock_bank(aino_df(until=TODAY), "A1")
    assert set(df["bank"]) == {"Nordea"} and df["synthetic"].all()


# --- build_profile (P1.6)


def test_build_profile_on_aino_has_every_key_and_serialises():
    p = build_profile(aino_df(until=TODAY), AINO, TODAY, goals=[JAPAN])
    json.dumps(p, allow_nan=False)
    assert set(DEMO_PROFILE) <= set(p)
    for key, section in DEMO_PROFILE.items():
        if isinstance(section, dict):
            assert set(section) <= set(p[key]), key
    assert p["customer"]["age_band"] == "18-24" and p["customer"]["area"] == "00"
    goal = p["goals"]["active"][0]
    assert goal["months_needed"] == 6 and goal["difficulty"] == "Stretch"
    assert p["levels"]["current"] >= 2
    prios = [a["priority"] for a in p["alerts"]]
    assert prios == sorted(prios, reverse=True)


def test_build_profile_empty_df_does_not_crash():
    p = build_profile(pd.DataFrame(), {"customer_id": "X"}, TODAY)
    json.dumps(p, allow_nan=False)
    assert p["levels"]["current"] == 0
    assert p["alerts"] == []
    assert build_profile(None, None, TODAY)["income"]["payday"]["found"] is False


def test_build_profile_no_income():
    df = make_df(
        [{"ts": f"2026-10-{d:02d} 12:00", "amount": -10} for d in range(1, 15)],
        start_balance=400,
    )
    p = build_profile(df, AINO, TODAY)
    assert p["income"]["payday"]["found"] is False
    assert p["forecast"]["safe_to_spend_week"] >= 0


def test_recompute_goals_and_levels():
    df = aino_df(until=TODAY)
    p = build_profile(df, AINO, TODAY)
    assert p["goals"]["active"] == []
    p2 = recompute_goals_and_levels(p, df, TODAY, [JAPAN])
    assert p2["goals"]["active"][0]["name"] == "Japan trip"
    assert p["goals"]["active"] == []  # input not mutated
    p3 = recompute_goals_and_levels(p, None, TODAY, [JAPAN])
    assert p3["goals"]["active"][0]["on_track"] is True
    json.dumps(p3, allow_nan=False)


def test_stressed_payment_shared():
    assert models.stressed_payment(150000) == pytest.approx(966.45, abs=0.01)
