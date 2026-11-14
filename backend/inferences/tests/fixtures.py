"""Hand-made customers with known answers (context.md "Inference unit tests").

"Test Aino": 4 months of data, July to October 2026, today = 18 October 2026.

Decisions where the doc's numbers do not fit together:
- The October basket split (#10) assumes all of October (incl. the 26 Oct
  saving transfer and 20 coffees), while payday (#1) is judged "from 18 Oct".
  `aino_df()` therefore holds the full four months; pass `until=TODAY` for
  the as-of-today tests. Inferences cut the data at `today` themselves, so
  basket tests use `today=AINO_OCT_END`.
- A running balance cannot be both 500 on 18 Oct and never below 445 in the
  30 days before (she spends ~1,100 between the 25 Sep payday and 18 Oct).
  We keep the lowest balance = 445 (the #30 test) by shifting the running
  balance; B on 18 Oct then comes out higher than 500.
- Groceries are "every week (4 a month)": we use the 3rd, 10th, 17th and
  24th, so each month has exactly 4 (EUR 240). Coffee is one a day on days
  1-20 at 08:30, takeaway on days 2, 7, 12, 17, 22, 27 at 19:30, so no
  accidental impulse bursts.
"""

from datetime import date

import pandas as pd

from inferences.common import COLUMNS

TODAY = date(2026, 10, 18)
AINO_OCT_END = date(2026, 10, 31)
AINO_LOWEST_30D = 445.0


def make_df(rows, start_balance=1000.0, customer="C-AINO"):
    """rows: dicts with ts, amount and optional merchant, category, mcc, ttype,
    account, name. Builds the CLAUDE.md columns with a running balance per
    account."""
    recs = []
    for i, r in enumerate(rows):
        stamp = pd.Timestamp(r["ts"])
        recs.append(
            {
                "tx_id": r.get("tx_id", f"t-{i}"),
                "customer_id": customer,
                "bank_account_id": r.get("account", "A1"),
                "tx_date": stamp.normalize(),
                "tx_timestamp": stamp,
                "category": r.get("category", "shopping"),
                "tx_amount_eur": float(r["amount"]),
                "transaction_type": r.get("ttype", "card_payment"),
                "merchant_id": r.get("merchant", "M_SHOP"),
                "merchant_name": r.get("name", r.get("merchant", "M_SHOP")),
                "mcc_code": str(r.get("mcc", "5999")),
            }
        )
    df = pd.DataFrame(recs)
    if not len(df):
        return pd.DataFrame(columns=COLUMNS + ["merchant_name"])
    df = df.sort_values("tx_timestamp", kind="stable").reset_index(drop=True)
    df["balance_after_eur"] = (
        start_balance + df.groupby("bank_account_id")["tx_amount_eur"].cumsum()
    )
    return df[COLUMNS + ["merchant_name"]]


def aino_rows():
    rows = []
    for m in (7, 8, 9, 10):

        def at(day, hhmm):
            return f"2026-{m:02d}-{day:02d} {hhmm}"

        rows.append(
            dict(
                ts=at(25, "08:00"),
                amount=2000,
                merchant="M_EMPLOYER",
                name="Employer Oy",
                category="income",
                mcc="",
                ttype="incoming_transfer",
            )
        )
        rows.append(
            dict(
                ts=at(1, "06:00"),
                amount=-650,
                merchant="M_RENT",
                name="Rent",
                category="housing",
                mcc="6513",
                ttype="direct_debit",
            )
        )
        rows.append(
            dict(
                ts=at(15, "06:00"),
                amount=-12.99,
                merchant="M_NETFLIX",
                name="Netflix",
                category="entertainment",
                mcc="4899",
                ttype="direct_debit",
            )
        )
        for day in (3, 10, 17, 24):
            rows.append(
                dict(
                    ts=at(day, "17:30"),
                    amount=-60,
                    merchant="M_SMARKET",
                    name="S-market",
                    category="groceries",
                    mcc="5411",
                )
            )
        for day in range(1, 21):
            rows.append(
                dict(
                    ts=at(day, "08:30"),
                    amount=-3.50,
                    merchant="M_CAFE",
                    name="Cafe",
                    category="coffee",
                    mcc="5814",
                )
            )
        for day in (2, 7, 12, 17, 22, 27):
            rows.append(
                dict(
                    ts=at(day, "19:30"),
                    amount=-15,
                    merchant="M_WOLT",
                    name="Wolt",
                    category="takeaway",
                    mcc="5812",
                )
            )
        rows.append(
            dict(
                ts=at(26, "10:00"),
                amount=-150,
                merchant="OWN_SAVINGS",
                name="Own savings",
                category="transfer",
                mcc="",
                ttype="investment_deposit",  # real S-Bank savings type
            )
        )
    rows.append(
        dict(
            ts="2026-09-12 14:00",
            amount=-400,
            merchant="M_GARAGE",
            name="Garage",
            category="vehicle",
            mcc="7538",
        )
    )
    return rows


def aino_df(until=None):
    """Test Aino, shifted so the lowest balance in the 30 days to 18 Oct is 445."""
    df = make_df(aino_rows(), start_balance=0.0)
    win = df[
        (df["tx_date"] >= pd.Timestamp(TODAY) - pd.Timedelta(days=30))
        & (df["tx_date"] <= pd.Timestamp(TODAY))
    ]
    df["balance_after_eur"] += AINO_LOWEST_30D - win["balance_after_eur"].min()
    df["balance_after_eur"] = df["balance_after_eur"].round(2)
    if until is not None:
        df = df[df["tx_date"] <= pd.Timestamp(until)].reset_index(drop=True)
    return df
