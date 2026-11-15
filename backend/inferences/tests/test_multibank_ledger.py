"""MB-4: merged ledger and own-transfer removal across banks (#41)."""

import pandas as pd
import pytest

from inferences import multibank
from inferences.common import income_inflows, latest_balance, prepare, spend
from inferences.profile import build_profile
from inferences.tests.fixtures import TODAY, aino_df

CUSTOMER = "C-AINO"


def external(rows):
    """External rows as multibank/ledger.py builds them (no balances)."""
    recs = []
    for i, (day, amount, category, ttype, name) in enumerate(rows):
        recs.append(
            {
                "tx_id": f"EXT-{i}",
                "customer_id": CUSTOMER,
                "bank_account_id": "EXT-1",
                "tx_date": pd.Timestamp(day),
                "tx_timestamp": pd.Timestamp(day) + pd.Timedelta(hours=12),
                "category": category,
                "tx_amount_eur": amount,
                "balance_after_eur": float("nan"),
                "transaction_type": ttype,
                "merchant_id": "EXT:" + name.lower().replace(" ", "-"),
                "mcc_code": "",
                "merchant_name": name,
                "bank": "Nordea",
                "synthetic": True,
            }
        )
    return pd.DataFrame(recs)


@pytest.fixture
def sbank():
    return aino_df(until=TODAY)


def _sbank_out(sbank, amount, day):
    row = sbank.iloc[[-1]].copy()
    row["tx_id"] = f"S-{day}-{amount}"
    row["tx_date"] = pd.Timestamp(day)
    row["tx_timestamp"] = pd.Timestamp(day) + pd.Timedelta(hours=9)
    row["tx_amount_eur"] = -amount
    row["category"] = "Transfer"
    row["transaction_type"] = "transfer"
    row["merchant_id"] = ""
    return pd.concat([sbank, row], ignore_index=True)


def test_merged_ledger_tags_banks_and_keeps_sbank_balances(sbank):
    ext = external([("2026-10-03", -310.0, "loan_payment", "loan_payment", "Auto")])
    merged = multibank.merged_transactions(sbank, ext)
    assert set(merged["bank"]) == {"S-Bank", "Nordea"}
    assert len(merged) == len(sbank) + 1
    # External rows carry no S-Bank balance: B (#17) is still S-Bank's.
    assert latest_balance(prepare(merged, TODAY)) == latest_balance(
        prepare(sbank, TODAY)
    )


def test_exact_transfer_between_banks_is_neither_spend_nor_income(sbank):
    with_out = _sbank_out(sbank, 1200.0, "2026-10-16")
    ext = external([("2026-10-17", 1200.0, "transfer", "transfer", "Own account")])
    df = prepare(multibank.merged_transactions(with_out, ext), TODAY)
    assert "EXT-0" not in set(income_inflows(df)["tx_id"])
    assert "S-2026-10-16-1200.0" not in set(spend(df)["tx_id"])
    assert multibank.own_transfer_ids(df) >= {"EXT-0", "S-2026-10-16-1200.0"}


@pytest.mark.parametrize(
    "amount, day",
    [(1201.0, "2026-10-10"), (1200.0, "2026-10-13")],  # amount off; 3 days apart
)
def test_near_misses_do_not_pair(sbank, amount, day):
    with_out = _sbank_out(sbank, 1200.0, "2026-10-10")
    ext = external([(day, amount, "transfer", "transfer", "Own account")])
    df = prepare(multibank.merged_transactions(with_out, ext), TODAY)
    assert "EXT-0" in set(income_inflows(df)["tx_id"])
    assert "EXT-0" not in multibank.own_transfer_ids(df)


def test_no_linked_banks_builds_exactly_the_old_profile(sbank):
    old = build_profile(sbank, {"customer_id": CUSTOMER}, TODAY)
    new = build_profile(sbank, {"customer_id": CUSTOMER}, TODAY, linked=None)
    for key in old:
        if key != "generated_at":
            assert new[key] == old[key], key
