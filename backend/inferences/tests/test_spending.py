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
    out = compute_spending(make_df(_rows()), DAY)
    names = {c["category"] for c in out["categories"]}
    assert not names & {"Salary", "Invest Deposit"}
    # #75: savings are their own row, outside the spending total.
    saved = {"category": "Invest Deposit", "total": 200.0, "count": 1}
    assert out["savings"] == [saved]
    assert out["savings_total"] == 200.0
    assert out["total"] == 765.0


def test_usual_is_the_3_month_mean_from_24():
    rows = _rows()
    for m, amount in ((7, 80), (8, 90), (9, 100)):
        ts = f"2026-{m:02d}-01 12:00"
        rows.append(dict(ts=ts, amount=-amount, category="Groceries"))
    out = compute_spending(make_df(rows), DAY)
    groceries = next(c for c in out["categories"] if c["category"] == "Groceries")
    assert groceries["usual"] == 90.0
    assert groceries["vs_usual"] == 10.0  # 100 so far this month
    housing = next(c for c in out["categories"] if c["category"] == "Housing")
    assert housing["usual"] is None and housing["vs_usual"] is None


def test_means_passed_in_are_used():
    out = compute_spending(make_df(_rows()), DAY, means={"housing": 600.0})
    assert out["categories"][0]["usual"] == 600.0
    assert out["categories"][0]["vs_usual"] == 50.0


def test_empty_month_falls_back_to_last_month():
    rows = [dict(ts="2026-09-12 12:00", amount=-30, category="Restaurants")]
    out = compute_spending(make_df(rows), DAY)
    assert out["month"] == "2026-09" and out["is_current"] is False
    assert out["categories"][0]["category"] == "Restaurants"


def test_no_spending():
    out = compute_spending(make_df([]), DAY)
    assert out["categories"] == [] and out["total"] == 0
