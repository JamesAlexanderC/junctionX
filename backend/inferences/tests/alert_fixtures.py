"""Hand-built transactions and profiles for the alert unit tests."""

import copy

import pandas as pd

COLUMNS = [
    "tx_id",
    "customer_id",
    "bank_account_id",
    "tx_date",
    "tx_timestamp",
    "category",
    "tx_amount_eur",
    "balance_after_eur",
    "transaction_type",
    "merchant_id",
    "mcc_code",
]


def tx(
    ts,
    amount,
    merchant="M_SHOP",
    category="shopping",
    mcc="5999",
    ttype="card",
    balance=1000.0,
    account="A1",
):
    """One transaction row as a dict; ts is 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'."""
    stamp = pd.Timestamp(ts)
    return {
        "customer_id": "C1",
        "bank_account_id": account,
        "tx_date": stamp.normalize(),
        "tx_timestamp": stamp,
        "category": category,
        "tx_amount_eur": float(amount),
        "balance_after_eur": float(balance),
        "transaction_type": ttype,
        "merchant_id": merchant,
        "mcc_code": mcc,
    }


def make_df(rows):
    """DataFrame with the CLAUDE.md columns and sequential tx ids."""
    if not rows:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(rows)
    df.insert(0, "tx_id", [f"t-{i}" for i in range(1, len(df) + 1)])
    return df[COLUMNS]


BASE_PROFILE = {
    "customer_id": "C1",
    "today": "2026-10-18",
    "balance": 500.0,
    "income": {
        "payday": {
            "found": True,
            "day_of_month": 25,
            "next_payday": "2026-10-23",
            "merchant_id": "M_EMPLOYER",
            "amount": 2000.0,
        },
        "monthly_income": 2000.0,
        "bills": [],
        "subscriptions": [],
        "possibly_unused": [],
    },
    "baskets": {
        "month": "2026-10",
        "totals": {"essential": 890.0, "surprise": 0.0, "leaky": 172.99, "saver": 150},
        "shares": {"essential": 73.4, "surprise": 0.0, "leaky": 14.3, "saver": 12.4},
        "history": [],
        "monthly_essentials": 890.0,
        "monthly_saving": 150.0,
    },
    "forecast": {
        "buffer": 89.0,
        "safe_to_save_today": 120.0,
        "daily_path": [],
        "danger_days": [],
        "upcoming_bills": [],
        "seasonal": {"warn": False},
    },
    "goals": {"active": [], "clash": {"clash": False}},
    "multibank": {"hidden_loans": [], "duplicate_subscriptions": []},
}


def profile(**overrides):
    """Deep copy of BASE_PROFILE with dotted-path overrides, e.g. balance=40."""
    p = copy.deepcopy(BASE_PROFILE)
    for path, value in overrides.items():
        node = p
        keys = path.split("__")
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
    return p


def aino_rows():
    """Test Aino (context.md "Tests"): July to October 2026, no loans."""
    rows = []
    for m in (7, 8, 9, 10):
        rows.append(tx(f"2026-{m:02d}-01 09:00", -650, "M_RENT", "housing", "6513"))
        rows.append(
            tx(f"2026-{m:02d}-15 09:00", -12.99, "M_NETFLIX", "entertainment", "4899")
        )
        for day in (3, 10, 17, 24):
            rows.append(
                tx(f"2026-{m:02d}-{day:02d} 18:00", -60, "M_GROC", "groceries", "5411")
            )
        for day in range(1, 21):
            rows.append(
                tx(f"2026-{m:02d}-{day:02d} 08:{day:02d}", -3.5, "M_CAFE", "coffee")
            )
        for day in (2, 6, 11, 16, 21, 27):
            rows.append(
                tx(f"2026-{m:02d}-{day:02d} 20:00", -15, "M_WOLT", "takeaway", "5814")
            )
        if m < 10:
            rows.append(
                tx(
                    f"2026-{m:02d}-25 06:00",
                    2000,
                    "M_EMPLOYER",
                    "salary",
                    "0000",
                    "salary",
                )
            )
            rows.append(
                tx(
                    f"2026-{m:02d}-26 07:00",
                    -150,
                    "M_OWN",
                    "savings",
                    "0000",
                    "own_transfer",
                )
            )
    rows.append(tx("2026-09-12 12:00", -400, "M_GARAGE", "car_repair", "7538"))
    return [r for r in rows if r["tx_date"] <= pd.Timestamp("2026-10-18")]
