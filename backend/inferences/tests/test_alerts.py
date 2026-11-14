"""Alert unit tests from context.md ("Alert unit tests" plus edge cases)."""

import copy
from datetime import date

import pytest

from inferences import alerts
from inferences.tests.alert_fixtures import aino_rows, make_df, profile, tx

TODAY = date(2026, 10, 18)
LOAN_IDS = set(range(76, 85))


def loan_rows(amount, months=(7, 8, 9, 10)):
    return [
        tx(f"2026-{m:02d}-05 09:00", -amount, "M_BANKLOAN", "loan", "6012")
        for m in months
    ]


def by_inference(found, number):
    return [a for a in found if a["inference"] == number]


# --- Loans -----------------------------------------------------------------


def test_loan_burden_amber():
    a = alerts.rule_76_loan_burden(make_df(loan_rows(900)), profile(), TODAY)
    assert a["severity"] == "amber"
    assert a["trigger_values"]["dsti"] == pytest.approx(0.45)


def test_loan_burden_red():
    a = alerts.rule_76_loan_burden(make_df(loan_rows(1100)), profile(), TODAY)
    assert a["severity"] == "red"
    assert a["trigger_values"]["dsti"] == pytest.approx(0.55)


def test_stressed_payment_formula():
    assert alerts.stressed_payment(150_000) == pytest.approx(966.45, abs=0.01)


def test_stress_test_passes():
    loans = {"balance": 150_000, "interest_rate": 0.04, "years_left": 25}
    a = alerts.rule_77_stress_test(make_df([]), profile(), TODAY, loans=loans)
    assert a is None


def test_stress_test_fails():
    loans = {"balance": 150_000, "interest_rate": 0.04, "years_left": 25}
    p = profile(income__monthly_income=1500.0)
    a = alerts.rule_77_stress_test(make_df([]), p, TODAY, loans=loans)
    assert a["severity"] == "red"
    assert a["trigger_values"]["stressed_payment"] == pytest.approx(966.45, abs=0.01)
    assert a["trigger_values"]["stressed_dsti"] == pytest.approx(0.644, abs=0.001)


def test_no_loans_found_no_loan_alerts():
    found = alerts.run_all_alerts(make_df(aino_rows()), profile(), TODAY)
    assert not [a for a in found if a["inference"] in LOAN_IDS]


# --- Spending, subscriptions, savings --------------------------------------


def test_spending_pace():
    rows = [tx(f"2026-09-{d:02d} 12:00", -100) for d in range(1, 11)]
    a = alerts.rule_88_spending_pace(make_df(rows), profile(), date(2026, 9, 10))
    assert a is not None
    assert a["trigger_values"]["projected"] == pytest.approx(3000)


def test_spending_pace_not_before_day_7():
    rows = [tx(f"2026-09-{d:02d} 12:00", -300) for d in range(1, 6)]
    assert (
        alerts.rule_88_spending_pace(make_df(rows), profile(), date(2026, 9, 5)) is None
    )


def test_bill_went_up():
    rows = [
        tx(f"2026-{m:02d}-15 09:00", -12.99, "M_NETFLIX", "entertainment", "4899")
        for m in (7, 8, 9)
    ]
    rows.append(tx("2026-10-15 09:00", -15.99, "M_NETFLIX", "entertainment", "4899"))
    found = alerts.rule_101_bill_went_up(make_df(rows), profile(), TODAY)
    assert len(found) == 1
    assert found[0]["trigger_values"]["threshold"] == pytest.approx(14.29, abs=0.01)
    assert found[0]["severity"] == "amber"


def test_similar_subscriptions():
    subs = [
        {
            "merchant_id": "M_NETFLIX",
            "name": "Netflix",
            "amount": 12.99,
            "mcc_code": "4899",
        },
        {
            "merchant_id": "M_YT",
            "name": "YouTube Premium",
            "amount": 11.99,
            "mcc_code": "4899",
        },
        {"merchant_id": "M_GYM", "name": "Gym", "amount": 29.0, "mcc_code": "7997"},
    ]
    p = profile(income__subscriptions=subs)
    found = alerts.rule_92_similar_subscriptions(make_df([]), p, TODAY)
    assert len(found) == 1
    assert set(found[0]["trigger_values"]["merchants"]) == {
        "Netflix",
        "YouTube Premium",
    }


def test_free_trial_turned_paid():
    rows = [
        tx("2026-09-01 10:00", 0.0, "M_TRIAL", "entertainment", "4899"),
        tx("2026-10-01 10:00", -9.99, "M_TRIAL", "entertainment", "4899"),
    ]
    found = alerts.rule_91_free_trial(make_df(rows), profile(), date(2026, 10, 5))
    assert len(found) == 1
    assert found[0]["severity"] == "blue"


def test_low_balance_now():
    a = alerts.rule_99_low_balance(make_df([]), profile(balance=40.0), TODAY)
    assert a["severity"] == "red"
    assert (
        alerts.rule_99_low_balance(make_df([]), profile(balance=500.0), TODAY) is None
    )


def test_payday_missed_only_after_three_days():
    rows = [
        tx(f"2026-{m:02d}-25 06:00", 2000, "M_EMPLOYER", "salary", "0000", "salary")
        for m in (7, 8, 9)
    ]
    df = make_df(rows)
    assert alerts.rule_100_payday_missed(df, profile(), date(2026, 10, 26)) is None
    a = alerts.rule_100_payday_missed(df, profile(), date(2026, 10, 27))
    assert a["severity"] == "red"
    assert a["trigger_values"]["expected_payday"] == "2026-10-23"


def test_payday_missed_needs_detected_payday_and_data():
    # #100 never fires without transactions or without a detected payday.
    empty = make_df([])
    assert alerts.rule_100_payday_missed(empty, profile(), date(2026, 10, 27)) is None
    assert alerts.rule_100_payday_missed(None, profile(), date(2026, 10, 27)) is None
    rows = [tx("2026-10-01 09:00", -20, "M_SHOP", "shopping", "5999", "card")]
    p = profile()
    p["income"]["payday"]["found"] = False
    got = alerts.rule_100_payday_missed(make_df(rows), p, date(2026, 10, 27))
    assert got is None


# --- Earlier alerts ---------------------------------------------------------


def test_duplicate_charge():
    rows = [
        tx("2026-10-10 12:00", -14.90, "M_X"),
        tx("2026-10-10 12:03", -14.90, "M_X"),
        tx("2026-10-12 12:00", -14.90, "M_Y"),
        tx("2026-10-14 12:00", -14.90, "M_Y"),
    ]
    found = alerts.rule_39_duplicate_charge(make_df(rows), profile(), TODAY)
    assert len(found) == 1
    assert found[0]["evidence_tx_ids"] == ["t-1", "t-2"]


def test_unusual_charge():
    amounts = [20, 22, 19, 21, 20]
    rows = [tx(f"2026-0{3 + i}-10 12:00", -a, "M_Z") for i, a in enumerate(amounts)]
    rows.append(tx("2026-10-10 12:00", -89, "M_Z"))
    found = alerts.rule_38_unusual_charge(make_df(rows), profile(), TODAY)
    assert len(found) == 1
    assert found[0]["trigger_values"]["z"] == pytest.approx(46.5, abs=0.1)


def test_category_spike():
    rows = [
        tx("2026-07-10 23:00", -20, "M_TAXI", "taxi", "4121"),
        tx("2026-08-10 23:00", -22, "M_TAXI", "taxi", "4121"),
        tx("2026-09-10 23:00", -21, "M_TAXI", "taxi", "4121"),
        tx("2026-10-10 23:00", -47.80, "M_TAXI", "taxi", "4121"),
    ]
    found = alerts.rule_40_category_spike(make_df(rows), profile(), TODAY)
    assert len(found) == 1
    assert found[0]["trigger_values"]["category"] == "taxi"


def test_overdraft():
    rows = [tx("2026-10-10 12:00", -50, balance=-12.0)]
    a = alerts.rule_85_overdraft(make_df(rows), profile(), TODAY)
    assert a["severity"] == "red"


def test_gambling_requires_opt_in():
    rows = [
        tx(f"2026-{m:02d}-05 22:00", -amt, "M_CASINO", "gambling", "7995")
        for m, amt in ((8, 10), (9, 20), (10, 30))
    ]
    df = make_df(rows)
    assert alerts.rule_98_gambling(df, profile(), TODAY) is None
    a = alerts.rule_98_gambling(df, profile(), TODAY, opted_in_gambling=True)
    assert alerts.thresholds.GAMBLING_SUPPORT_URL in a["text"]


# --- Registry, priority, snooze, simulation ----------------------------------


def test_priority():
    assert alerts.alert_priority("amber", date(2026, 10, 23), TODAY) == pytest.approx(
        0.4
    )
    assert alerts.alert_priority("red", TODAY, TODAY) == 3
    assert alerts.alert_priority("blue", "2026-11-17", TODAY) == pytest.approx(1 / 30)


def test_registry_covers_every_alert():
    expected = {6, 20, 23, 38, 39, 40, 42, 43, 50, 52, 62, 70} | set(range(76, 103))
    assert set(alerts.ALERT_RULES) == expected


def test_run_all_on_profile_only_and_empty():
    found = alerts.run_all_alerts(make_df([]), profile(balance=40.0), TODAY)
    assert found == sorted(found, key=lambda a: -a["priority"])
    assert {"id", "inference", "severity", "priority"} <= set(found[0])
    assert alerts.run_all_alerts(None, {}, TODAY) == []


def test_snooze_hides_until_date():
    p = profile(balance=40.0)
    found = alerts.run_all_alerts(make_df([]), p, TODAY)
    alert_id = by_inference(found, 99)[0]["id"]
    snoozed = {alert_id: date(2026, 10, 21)}
    assert not by_inference(
        alerts.run_all_alerts(make_df([]), p, TODAY, snoozed=snoozed), 99
    )
    later = alerts.run_all_alerts(make_df([]), p, date(2026, 10, 21), snoozed=snoozed)
    assert by_inference(later, 99)


def test_top_nudge_skips_blue():
    blue = {"severity": "blue", "priority": 1.0}
    amber = {"severity": "amber", "priority": 0.1}
    assert alerts.top_nudge([blue, amber]) is amber
    assert alerts.top_nudge([blue]) is None


def planner_profile():
    goal = {
        "id": 1,
        "name": "Japan",
        "on_track": False,
        "paused": False,
        "target_date": "2027-06-01",
        "realistic": True,
    }
    history = [
        {
            "month": "2026-07",
            "totals": {"essential": 900, "surprise": 0, "leaky": 100, "saver": 150},
        },
        {
            "month": "2026-08",
            "totals": {"essential": 900, "surprise": 0, "leaky": 120, "saver": 150},
        },
        {
            "month": "2026-09",
            "totals": {"essential": 900, "surprise": 0, "leaky": 140, "saver": 150},
        },
    ]
    return profile(
        forecast__danger_days=["2026-10-23"],
        goals__active=[goal],
        baskets__history=history,
        baskets__totals={"essential": 900, "surprise": 0, "leaky": 160, "saver": 150},
    )


def test_simulated_profile_clears_alerts():
    p = planner_profile()
    before = {a["inference"] for a in alerts.run_all_alerts(make_df([]), p, TODAY)}
    assert {20, 52, 89} <= before

    sim = copy.deepcopy(p)
    sim["forecast"]["danger_days"] = []
    sim["goals"]["active"][0]["on_track"] = True
    sim["baskets"]["totals"]["leaky"] = 128  # takeaways cut 20%
    after = {a["inference"] for a in alerts.run_all_alerts(make_df([]), sim, TODAY)}
    assert not {20, 52, 89} & after
