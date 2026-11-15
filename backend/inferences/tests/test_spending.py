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
    housing = out["categories"][0]
    assert housing["usual"] == 600.0
    # No housing in the data's earlier months: 0 usually spent by the 18th.
    assert housing["usual_so_far"] == 0.0 and housing["vs_usual"] == 650.0


def test_part_month_is_compared_with_the_same_days_of_usual_months():
    rows = _rows()
    # Groceries usually 90 a month, but always bought late in the month.
    for m, amount in ((7, 80), (8, 90), (9, 100)):
        rows.append(
            dict(ts=f"2026-{m:02d}-25 12:00", amount=-amount, category="Groceries")
        )
        # Rent early in the month, like this month (on the 1st, so July
        # counts as a full month of data).
        rows.append(
            dict(
                ts=f"2026-{m:02d}-01 12:00",
                amount=-650,
                category="Housing",
                merchant="M_R",
            )
        )
    out = compute_spending(make_df(rows), DAY)
    by = {c["category"]: c for c in out["categories"]}
    # By the 18th the usual months had spent nothing on groceries yet.
    assert by["Groceries"]["usual"] == 90.0
    assert by["Groceries"]["usual_so_far"] == 0.0
    assert by["Groceries"]["vs_usual"] == 100.0
    # Rent is paid in full by the 18th in every month: no false "more".
    assert by["Housing"]["usual_so_far"] == 650.0
    assert by["Housing"]["vs_usual"] == 0.0


def test_last_month_is_not_compared_with_itself():
    rows = [
        dict(ts=f"2026-{m:02d}-12 12:00", amount=-a, category="Restaurants")
        for m, a in ((6, 30), (7, 60), (8, 90), (9, 300))
    ]
    out = compute_spending(make_df(rows), DAY)
    assert out["month"] == "2026-09" and out["is_current"] is False
    row = out["categories"][0]
    # Usual = June to August (60), not July to September (150).
    assert row["usual"] == 60.0 and row["usual_so_far"] == 60.0
    assert row["vs_usual"] == 240.0


def test_empty_month_falls_back_to_last_month():
    rows = [dict(ts="2026-09-12 12:00", amount=-30, category="Restaurants")]
    out = compute_spending(make_df(rows), DAY)
    assert out["month"] == "2026-09" and out["is_current"] is False
    assert out["categories"][0]["category"] == "Restaurants"


def test_no_spending():
    out = compute_spending(make_df([]), DAY)
    assert out["categories"] == [] and out["total"] == 0
