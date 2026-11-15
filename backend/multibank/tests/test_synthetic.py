"""MB-2: synthetic other-bank data, scenarios A-E (generate --seed 42)."""

import json
from datetime import date, timedelta

import pytest

from multibank import scenarios as sc
from multibank.synthetic import generate

# CUST03600's S-Bank salary sweeps (date, amount out), as the command reads them.
SWEEPS = {
    sc.SALARY_ELSEWHERE: [
        (date(2025, 10, 16) + timedelta(days=30 * i), 4100.0 + 7 * i) for i in range(11)
    ]
    + [(date(2026, 9, 30), 4200.0)]  # last day of the data: cannot move to +1
}


@pytest.fixture(scope="module")
def data():
    return generate(seed=42, sweeps=SWEEPS)


def _account(data, customer, bank, cash_type):
    accounts = data["customers"][customer][bank]["accounts"]
    return next(a for a in accounts if a["cashAccountType"] == cash_type)


def _amounts(account):
    return [float(t["transactionAmount"]["amount"]) for t in account["transactions"]]


def test_generation_is_reproducible(data):
    assert json.dumps(generate(seed=42, sweeps=SWEEPS), sort_keys=True) == json.dumps(
        data, sort_keys=True
    )
    assert generate(seed=7, sweeps=SWEEPS) != data


def test_everything_is_marked_synthetic_and_has_no_credentials(data):
    assert data["is_synthetic"] is True
    text = json.dumps(data).lower()
    assert "password" not in text and "username" not in text
    for banks in data["customers"].values():
        for bank in banks.values():
            assert all(a["isSynthetic"] for a in bank["accounts"])


def test_a_hero_has_a_car_loan_on_the_3rd(data):
    account = _account(data, sc.HERO, "NDEAFIHH", "CACC")
    loans = [t for t in account["transactions"] if t["merchantCategoryCode"] == "6141"]
    assert len(loans) == 12
    assert {t["bookingDate"][-2:] for t in loans} == {"03"}
    amounts = {float(t["transactionAmount"]["amount"]) for t in loans}
    assert len(amounts) == 1 and 250 <= -amounts.pop() <= 350


def test_b_every_sweep_arrives_at_the_other_bank_within_a_day(data):
    account = _account(data, sc.SALARY_ELSEWHERE, "OKOYFIHH", "CACC")
    ins = [
        (date.fromisoformat(t["bookingDate"]), float(t["transactionAmount"]["amount"]))
        for t in account["transactions"]
        if float(t["transactionAmount"]["amount"]) > 0
    ]
    for day, amount in SWEEPS[sc.SALARY_ELSEWHERE]:
        assert any(a == amount and abs((d - day).days) <= 1 for d, a in ins)


def test_c_two_banks_each_bill_a_music_subscription(data):
    banks = data["customers"][sc.DUPLICATE_SUBS]
    assert len(banks) == 2
    mccs = []
    for bank in banks.values():
        account = bank["accounts"][0]
        subs = [t for t in account["transactions"] if t["merchantCategoryCode"]]
        assert len(subs) == 12
        mccs.append({t["merchantCategoryCode"] for t in subs})
    assert mccs[0] == mccs[1] == {"5815"}


def test_d_credit_card_has_a_balance_and_a_monthly_repayment(data):
    card = _account(data, sc.CREDIT_CARD, "DABAFIHH", "CARD")
    assert card["balance"] < 0
    current = _account(data, sc.CREDIT_CARD, "DABAFIHH", "CACC")
    repayments = [
        t
        for t in current["transactions"]
        if t["proprietaryBankTransactionCode"] == "CARD_REPAYMENT"
    ]
    assert len(repayments) == 12


def test_e_savings_account_elsewhere(data):
    savings = _account(data, sc.SAVINGS_ELSEWHERE, "AABAFI22", "SVGS")
    assert savings["balance"] > 0


def test_data_ends_with_the_sbank_data(data):
    for banks in data["customers"].values():
        for bank in banks.values():
            for account in bank["accounts"]:
                dates = [t["bookingDate"] for t in account["transactions"]]
                assert all("2025-10-01" <= d <= "2026-09-30" for d in dates)
                assert account["balanceDate"] == "2026-09-30"


def test_a_hero_loan_account_holds_only_a_small_balance(data):
    # Otherwise #113 counts it as buffer and the level goes up, not down.
    account = _account(data, sc.HERO, "NDEAFIHH", "CACC")
    assert 0 < account["balance"] < 150
