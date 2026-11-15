"""MB-5: #112 coverage from S-Bank data alone, and the partial-view nudge."""

import pandas as pd

from inferences.profile import build_profile
from inferences.tests.fixtures import TODAY, make_df

CUSTOMER = "C-AINO"
MONTHS = ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def _rows(sweep_share):
    rows = []
    for m in MONTHS:
        rows.append(
            {
                "ts": f"{m}-15 08:00",
                "amount": 3000.0,
                "ttype": "salary",
                "category": "Salary",
                "merchant": "",
            }
        )
        if sweep_share:
            rows.append(
                {
                    "ts": f"{m}-16 08:00",
                    "amount": -3000.0 * sweep_share,
                    "ttype": "salary_sweep",
                    "category": "Salary Sweep",
                    "merchant": "",
                }
            )
        rows.append(
            {
                "ts": f"{m}-05 12:00",
                "amount": -60.0,
                "category": "Groceries",
                "merchant": "M_FOOD",
                "mcc": "5411",
            }
        )
    return rows


def _linked_mirroring_sweeps(df):
    """The other bank receives each sweep the next day (exact amount)."""
    sweeps = df[df["transaction_type"] == "salary_sweep"]
    rows = [
        {
            "tx_id": f"EXT-{i}",
            "customer_id": CUSTOMER,
            "bank_account_id": "EXT-1",
            "tx_date": s["tx_date"] + pd.Timedelta(days=1),
            "tx_timestamp": s["tx_date"] + pd.Timedelta(days=1, hours=12),
            "category": "transfer",
            "tx_amount_eur": -s["tx_amount_eur"],
            "balance_after_eur": float("nan"),
            "transaction_type": "transfer",
            "merchant_id": "EXT:own-account",
            "mcc_code": "",
            "merchant_name": "Own account at S-Bank",
            "bank": "OP",
            "synthetic": True,
        }
        for i, (_, s) in enumerate(sweeps.iterrows())
    ]
    account = {"bank": "OP", "type": "current", "balance_eur": 900.0}
    return {"transactions": pd.DataFrame(rows), "accounts": [account], "consents": []}


def _profile(sweep_share, linked=False):
    df = make_df(_rows(sweep_share))
    return build_profile(
        df,
        {"customer_id": CUSTOMER},
        TODAY,
        linked=_linked_mirroring_sweeps(df) if linked else None,
    )


def _nudge(profile):
    return [a for a in profile["alerts"] if a["inference"] == 112]


def test_all_income_at_sbank_is_sbank_only_without_a_nudge():
    p = _profile(sweep_share=0)
    assert p["multibank"]["coverage"] == "sbank_only"
    assert _nudge(p) == []
    assert "caveat" not in p["availability"]["income.monthly_income"]


def test_most_income_swept_out_is_partial_with_a_nudge():
    p = _profile(sweep_share=0.9)
    assert p["multibank"]["coverage"] == "partial"
    (nudge,) = _nudge(p)
    assert nudge["severity"] == "blue"
    assert "part of your money" in nudge["title"]
    assert p["availability"]["income.monthly_income"]["caveat"] == "partial_view"
    assert p["availability"]["income.monthly_income"]["available"] is True


def test_linking_the_bank_the_salary_goes_to_makes_the_view_full():
    p = _profile(sweep_share=0.9, linked=True)
    assert p["multibank"]["coverage"] == "full"
    assert _nudge(p) == []
    assert "caveat" not in p["availability"]["income.monthly_income"]


def test_the_nudge_is_at_most_once_a_month():
    p = _profile(sweep_share=0.9)
    assert _nudge(p)[0]["id"] == "a-112-2026-10"
