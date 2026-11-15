"""Edge-case tests (context.md "Tests", edge-case table)."""

from datetime import date

import pytest

from inferences import anomalies, baskets, forecast, habits, income, models, whatif
from inferences.common import prepare
from inferences.tests.fixtures import make_df


def test_impulse_burst_three_coffees_in_45_minutes():
    # #13: 1 burst.
    rows = [
        dict(ts="2026-10-05 08:00", amount=-3.5, category="coffee"),
        dict(ts="2026-10-05 08:20", amount=-3.5, category="coffee"),
        dict(ts="2026-10-05 08:45", amount=-3.5, category="coffee"),
        dict(ts="2026-10-07 08:00", amount=-3.5, category="coffee"),
    ]
    df = make_df(rows)
    assert models.count_bursts(df["tx_timestamp"]) == 1
    assert (
        habits.impulse(prepare(df), date(2026, 10, 31), months=1)["bursts_per_month"]
        == 1.0
    )


def test_duplicate_charge():
    # #39: first pair flagged, second not.
    rows = [
        dict(ts="2026-10-01 12:00", amount=-14.90, merchant="M_X", tx_id="a1"),
        dict(ts="2026-10-01 12:03", amount=-14.90, merchant="M_X", tx_id="a2"),
        dict(ts="2026-10-05 12:00", amount=-14.90, merchant="M_Y", tx_id="b1"),
        dict(ts="2026-10-07 12:00", amount=-14.90, merchant="M_Y", tx_id="b2"),
    ]
    dups = anomalies.duplicate_charges(make_df(rows))
    assert [d["tx_ids"] for d in dups] == [["a1", "a2"]]


def test_unusual_charge():
    # #38: median 20, MAD 1, z ~ 46.5 -> flagged.
    res = anomalies.unusual_charge(89, [20, 22, 19, 21, 20])
    assert res["median"] == 20.0
    assert res["mad"] == 1.0
    assert res["z"] == pytest.approx(46.5, abs=0.1)
    assert res["flagged"] is True
    assert anomalies.unusual_charge(21, [20, 22, 19, 21, 20])["flagged"] is False


def test_unusual_charge_in_frame():
    rows = [
        dict(ts=f"2026-{m:02d}-10", amount=-a, merchant="M_GYM", category="sport")
        for m, a in zip((5, 6, 7, 8, 9), (20, 22, 19, 21, 20))
    ] + [dict(ts="2026-10-10", amount=-89, merchant="M_GYM", category="sport")]
    flagged = anomalies.unusual_charges(make_df(rows), date(2026, 10, 18))
    assert len(flagged) == 1 and flagged[0]["amount"] == 89.0


def test_unusual_charge_short_merchant_history_uses_category():
    # Fewer than 3 merchant payments: falls back to the category history,
    # which arrives as a pandas Series (this used to raise ValueError).
    rows = [
        dict(ts=f"2026-{m:02d}-10", amount=-20, merchant=f"M_{m}", category="sport")
        for m in (5, 6, 7, 8, 9)
    ] + [dict(ts="2026-10-10", amount=-90, merchant="M_NEW", category="sport")]
    flagged = anomalies.unusual_charges(make_df(rows), date(2026, 10, 18))
    assert [f["rule"] for f in flagged] == ["category_median"]
    assert flagged[0]["amount"] == 90.0


def test_category_spike():
    # #40: taxis 20, 22, 21, then 47.80 -> flagged (47.80 > 31.50, +26.80 > 20).
    rows = [
        dict(ts=f"2026-{m:02d}-10", amount=-a, category="taxi", merchant="M_TAXI")
        for m, a in zip((7, 8, 9, 10), (20, 22, 21, 47.80))
    ]
    spikes = anomalies.category_spikes(make_df(rows), date(2026, 10, 18))
    assert len(spikes) == 1
    s = spikes[0]
    assert s["category"] == "taxi"
    assert s["previous_mean"] == 21.0
    assert s["threshold"] == 31.5
    assert s["difference"] == 26.8


def test_own_account_transfer_not_income():
    # #41: -300 from A and +300 into B the same day is not income.
    rows = [
        dict(
            ts="2026-09-25 08:00",
            amount=2000,
            merchant="M_EMP",
            category="income",
            ttype="incoming_transfer",
            account="A",
        ),
        dict(
            ts="2026-09-27 10:00",
            amount=-300,
            merchant="ME",
            account="A",
            ttype="transfer",
            category="transfer",
        ),
        dict(
            ts="2026-09-27 10:05",
            amount=300,
            merchant="ME",
            account="B",
            ttype="transfer",
            category="transfer",
        ),
    ]
    inc = income.compute_income(make_df(rows), date(2026, 10, 18))
    sep = next(s for s in inc["monthly_income_series"] if s["month"] == "2026-09")
    assert sep["value"] == 2000.0


def test_no_income():
    # #1, #17: payday not found, safe to spend = balance - buffer, no crash.
    rows = [
        dict(ts=f"2026-{m:02d}-{d:02d}", amount=-10, category="coffee")
        for m in (8, 9, 10)
        for d in (3, 9, 14)
    ]
    df = make_df(rows, start_balance=500)
    today = date(2026, 10, 18)
    inc = income.compute_income(df, today)
    assert inc["payday"]["found"] is False
    assert inc["payday"]["next_payday"] is None
    bsk = baskets.compute_baskets(df, today, bills=inc["bills"])
    fc = forecast.compute_forecast(df, today, inc, bsk)
    assert fc["safe_to_spend_week"] == max(0.0, 410.0 - fc["buffer"])


def test_goal_not_reachable():
    # #26: Saver rate 0 -> "not reachable at the current pace".
    res = whatif.goal_date(1500, 640, 0, date(2026, 10, 18))
    assert res["reachable"] is False
    assert res["months"] is None
    assert res["text"] == "Not reachable at the current pace"


def test_empty_month():
    # #10: month with no outflows -> all baskets 0, no division by zero.
    rows = [dict(ts="2026-09-10", amount=-20, category="coffee")]
    cls = baskets.classify(make_df(rows), date(2026, 10, 31))
    split = baskets.basket_split(cls, "2026-10")
    assert all(v == 0.0 for v in split["totals"].values())
    assert all(v == 0.0 for v in split["shares"].values())


def test_empty_frame_does_not_crash():
    df = make_df([])
    today = date(2026, 10, 18)
    inc = income.compute_income(df, today)
    bsk = baskets.compute_baskets(df, today, bills=inc["bills"])
    forecast.compute_forecast(df, today, inc, bsk)
    habits.compute_habits(df, today, inc, bsk)


def test_models_misc():
    assert models.laplace_weight(0, 0) == 0.5
    assert models.hhi([50, 50]) == 0.5
    assert models.linear_slope([1, 2, 3]) == 1.0
    # #77 stress payment: 150,000 at 6% over 300 months ~ 966.45.
    assert models.stressed_payment(150000) == pytest.approx(966.45, abs=0.01)
    assert models.proportional_split(60, {"a": 2, "b": 1}) == {"a": 40.0, "b": 20.0}
