"""profile["spending"]: spending per data category (inferences/spending.py)."""

from datetime import date

from inferences.spending import compute_spending
from inferences.tests.fixtures import make_df

DAY = date(2026, 10, 18)


def _rows():
    return [
        dict(ts="2026-10-02 12:00", amount=-650, category="Housing", merchant="M_R"),
        dict(ts="2026-10-03 12:00", amount=-40, category="Groceries"),
        dict(ts="2026-10-09 12:00", amount=-60, category="Groceries"),
        dict(ts="2026-10-10 12:00", amount=-15, category="Home & Tech"),
        dict(ts="2026-10-05 12:00", amount=2000, category="Salary", ttype="salary"),
        dict(
            ts="2026-10-06 12:00",
            amount=-200,
            category="Invest Deposit",
            ttype="investment_deposit",
        ),
    ]


def test_categories_keep_the_data_spelling_and_sum_to_total():
    out = compute_spending(make_df(_rows()), DAY)
    assert out["month"] == "2026-10" and out["is_current"] is True
    names = [c["category"] for c in out["categories"]]
    assert names == ["Housing", "Groceries", "Home & Tech"]
    groceries = out["categories"][1]
    assert groceries["total"] == 100.0 and groceries["count"] == 2
    assert out["total"] == 765.0
    assert round(sum(c["share"] for c in out["categories"]), 0) == 100


def test_inflows_and_savings_transfers_are_not_spending():
    names = {
        c["category"] for c in compute_spending(make_df(_rows()), DAY)["categories"]
    }
    assert not names & {"Salary", "Invest Deposit"}


def test_empty_month_falls_back_to_last_month():
    rows = [dict(ts="2026-09-12 12:00", amount=-30, category="Restaurants")]
    out = compute_spending(make_df(rows), DAY)
    assert out["month"] == "2026-09" and out["is_current"] is False
    assert out["categories"][0]["category"] == "Restaurants"


def test_no_spending():
    out = compute_spending(make_df([]), DAY)
    assert out["categories"] == [] and out["total"] == 0
