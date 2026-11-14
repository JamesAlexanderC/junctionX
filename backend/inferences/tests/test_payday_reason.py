"""#1 payday: when no payday is found, say which check failed.

The availability reason used to always read "needs one in 3 of the last 4
months", but on the real data 85% of customers without a payday fail the
amount-variation check instead (docs: payday scan, 2026-11-14).
"""

import pytest

from inferences.availability import availability
from inferences.common import prepare
from inferences.income import detect_payday
from inferences.profile import build_profile
from inferences.tests.fixtures import TODAY, aino_df, make_df

CUSTOMER = {"customer_id": "x", "age": 30, "postal_code": "00100"}


def _salary(months_and_amounts):
    rows = [
        dict(
            ts=f"2026-{m:02d}-25 08:00",
            amount=a,
            merchant="M_EMPLOYER",
            category="salary",
            ttype="salary",
        )
        for m, a in months_and_amounts
    ]
    rows += [
        dict(ts=f"2026-{m:02d}-10 12:00", amount=-30, merchant="M_SHOP")
        for m in (7, 8, 9, 10)
    ]
    return make_df(rows)


CASES = {
    # Paid every month in the window, but the amount swings by a third.
    "amount_varies": _salary([(7, 1000), (8, 2000), (9, 1000), (10, 2000)]),
    # Steady amount, but only 2 of the last 4 months.
    "not_recurring": _salary([(7, 2000), (8, 2000)]),
    # Spending only.
    "no_income": _salary([]),
}


@pytest.mark.parametrize("reason", list(CASES))
def test_missing_payday_says_which_check_failed(reason):
    out = detect_payday(prepare(CASES[reason], TODAY), TODAY)
    assert out["found"] is False
    assert out["reason"] == reason


def test_found_payday_has_no_reason():
    out = detect_payday(prepare(aino_df(until=TODAY), TODAY), TODAY)
    assert out["found"] is True
    assert out["reason"] is None


@pytest.mark.parametrize(
    "reason, words",
    [
        ("amount_varies", "changes too much"),
        ("not_recurring", "3 of the last 4 months"),
        ("no_income", "No income"),
    ],
)
def test_availability_reason_matches_the_failed_check(reason, words):
    profile = build_profile(CASES[reason], CUSTOMER, TODAY)
    flag = availability(profile)["income.payday"]
    assert flag["available"] is False
    assert words in flag["reason"]


def test_amount_reason_names_the_threshold():
    profile = build_profile(CASES["amount_varies"], CUSTOMER, TODAY)
    assert "15%" in availability(profile)["income.payday"]["reason"]


def test_found_payday_availability_has_no_reason():
    profile = build_profile(aino_df(), CUSTOMER, TODAY)
    flag = profile["availability"]["income.payday"]
    assert flag == {**flag, "available": True, "reason": None}
