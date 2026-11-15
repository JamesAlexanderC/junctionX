"""MB-6: hidden loans (#42), duplicate subscriptions (#43), real income (#111),
total buffer (#113) and consent expiry (#114)."""

from datetime import date

import pandas as pd
import pytest

from inferences.profile import build_profile
from inferences.tests.fixtures import make_df

CUSTOMER = "C-HERO"
TODAY = date(2026, 9, 30)
MONTHS = [f"2026-{m:02d}" for m in range(4, 10)]


def _sbank(sweep=0.0):
    rows = []
    for m in MONTHS:
        rows += [
            {
                "ts": f"{m}-15 08:00",
                "amount": 2400.0,
                "ttype": "salary",
                "category": "Salary",
                "merchant": "",
            },
            {
                "ts": f"{m}-05 09:00",
                "amount": -900.0,
                "ttype": "housing_payment",
                "category": "Housing",
                "merchant": "",
            },
            {
                "ts": f"{m}-08 12:00",
                "amount": -150.0,
                "category": "Groceries",
                "merchant": "M_FOOD",
                "mcc": "5411",
            },
            {
                "ts": f"{m}-22 12:00",
                "amount": -150.0,
                "category": "Groceries",
                "merchant": "M_FOOD",
                "mcc": "5411",
            },
        ]
        if sweep:
            rows.append(
                {
                    "ts": f"{m}-16 08:00",
                    "amount": -sweep,
                    "ttype": "salary_sweep",
                    "category": "Salary Sweep",
                    "merchant": "",
                }
            )
    return make_df(rows, start_balance=1200.0, customer=CUSTOMER)


def _ext(rows, bank="Nordea", account="EXT-1"):
    recs = []
    for i, (day, amount, category, ttype, name, mcc) in enumerate(rows):
        recs.append(
            {
                "tx_id": f"EXT-{account}-{i}",
                "customer_id": CUSTOMER,
                "bank_account_id": account,
                "tx_date": pd.Timestamp(day),
                "tx_timestamp": pd.Timestamp(day) + pd.Timedelta(hours=12),
                "category": category,
                "tx_amount_eur": amount,
                "balance_after_eur": float("nan"),
                "transaction_type": ttype,
                "merchant_id": "EXT:" + name.lower().replace(" ", "-"),
                "mcc_code": mcc,
                "merchant_name": name,
                "bank": bank,
                "synthetic": True,
            }
        )
    return pd.DataFrame(recs)


def _linked(frames, accounts, consents=()):
    return {
        "transactions": pd.concat(frames, ignore_index=True),
        "accounts": list(accounts),
        "consents": list(consents),
    }


def _build(df, linked=None, loans=None):
    return build_profile(
        df, {"customer_id": CUSTOMER}, TODAY, linked=linked, loans=loans
    )


LOAN = _ext(
    [
        (f"{m}-03", -310.0, "loan_payment", "loan_payment", "Autorahoitus Oy", "6141")
        for m in MONTHS
    ]
)
CURRENT = {"bank": "Nordea", "type": "current", "balance_eur": 400.0}


@pytest.fixture(scope="module")
def hero():
    df = _sbank()
    return _build(df), _build(df, _linked([LOAN], [CURRENT]))


def test_42_hidden_loan_is_found_with_its_bank(hero):
    _, after = hero
    (loan,) = after["multibank"]["hidden_loans"]
    assert loan["bank"] == "Nordea" and loan["amount"] == 310.0
    assert loan["day_of_month"] == 3  # what the coach says ("on the 3rd")
    assert loan["next_date"] in ("2026-10-03", "2026-10-04")  # #4 estimate


def test_42_hidden_loan_counts_in_dsti_and_bills_before_payday(hero):
    before, after = hero
    assert before["mortgage"]["dsti"] is None
    assert after["mortgage"]["dsti"] == round(310.0 / 2400.0, 2)
    upcoming = {b["name"] for b in after["forecast"]["upcoming_bills"]}
    assert "Autorahoitus Oy" in upcoming
    assert (
        after["forecast"]["safe_to_spend_week"]
        < before["forecast"]["safe_to_spend_week"]
    )


def test_42_hidden_loan_counts_in_the_stress_test():
    df, loans = _sbank(), {"balance": 150000, "interest_rate": 0.04, "years_left": 25}
    before = _build(df, loans=loans)["mortgage"]["stress_test"]
    after = _build(df, _linked([LOAN], [CURRENT]), loans=loans)["mortgage"][
        "stress_test"
    ]
    assert after["stressed_payment"] == pytest.approx(
        before["stressed_payment"] + 310.0, abs=0.01
    )


def test_43_two_music_services_at_two_banks_are_flagged():
    subs_a = _ext(
        [
            (f"{m}-07", -11.99, "entertainment", "purchase", "StreamTone Music", "5815")
            for m in MONTHS
        ],
        "Danske Bank",
        "E1",
    )
    subs_b = _ext(
        [
            (f"{m}-21", -9.99, "entertainment", "purchase", "Melodia Plus", "5815")
            for m in MONTHS
        ],
        "Aktia",
        "E2",
    )
    accounts = [
        {"bank": "Danske Bank", "type": "current", "balance_eur": 50.0},
        {"bank": "Aktia", "type": "current", "balance_eur": 50.0},
    ]
    p = _build(_sbank(), _linked([subs_a, subs_b], accounts))
    (dup,) = p["multibank"]["duplicate_subscriptions"]
    assert {s["name"] for s in dup["services"]} == {"StreamTone Music", "Melodia Plus"}
    assert {s["bank"] for s in dup["services"]} == {"Danske Bank", "Aktia"}
    assert dup["yearly_cost"] == round(9.99 * 12, 2)  # the cheaper one is extra
    assert any(a["inference"] == 43 for a in p["alerts"])


def test_43_a_single_subscription_is_not_flagged():
    subs = _ext(
        [
            (f"{m}-07", -11.99, "entertainment", "purchase", "StreamTone Music", "5815")
            for m in MONTHS
        ],
        "Danske Bank",
        "E1",
    )
    p = _build(_sbank(), _linked([subs], [CURRENT]))
    assert p["multibank"]["duplicate_subscriptions"] == []


def test_111_income_is_not_double_counted_when_the_sweep_lands_elsewhere():
    df = _sbank(sweep=2100.0)
    mirror = _ext(
        [
            (f"{m}-17", 2100.0, "transfer", "transfer", "Own account", "")
            for m in MONTHS
        ],
        "OP",
    )
    before = _build(df)
    after = _build(
        df, _linked([mirror], [{"bank": "OP", "type": "current", "balance_eur": 900.0}])
    )
    assert after["income"]["monthly_income"] == before["income"]["monthly_income"]
    assert before["multibank"]["coverage"] == "partial"
    assert after["multibank"]["coverage"] == "full"
    assert after["multibank"]["own_transfers_found"] == len(MONTHS)


def test_113_buffer_includes_external_savings_but_safe_to_spend_does_not():
    df = _sbank()
    savings = {"bank": "Alandsbanken", "type": "savings", "balance_eur": 3000.0}
    card = {"bank": "Danske Bank", "type": "credit", "balance_eur": -800.0}
    before = _build(df)
    after = _build(
        df, {"transactions": None, "accounts": [savings, card], "consents": []}
    )
    assert after["levels"]["buffer_months"] > before["levels"]["buffer_months"]
    assert (
        after["forecast"]["safe_to_spend_week"]
        == before["forecast"]["safe_to_spend_week"]
    )
    assert after["multibank"]["external_liquid"] == 3000.0
    assert after["multibank"]["total_liquid_balance"] == round(
        before["balance"] + 3000.0, 2
    )


@pytest.mark.parametrize("days_left, fires", [(14, True), (10, True), (15, False)])
def test_114_consent_expiry_alert_14_days_before(days_left, fires):
    expires = (pd.Timestamp(TODAY) + pd.Timedelta(days=days_left)).date()
    consent = {"consent_id": 1, "bank": "Nordea", "expires_at": expires.isoformat()}
    p = _build(_sbank(), _linked([LOAN], [CURRENT], [consent]))
    alerts = [a for a in p["alerts"] if a["inference"] == 114]
    assert bool(alerts) is fires
    if fires:
        assert alerts[0]["severity"] == "blue" and "Nordea" in alerts[0]["text"]
