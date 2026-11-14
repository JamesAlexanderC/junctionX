"""Management commands on a tiny synthetic CSV set."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from coach import services
from coach.models import Customer, MortgageOutcome, Transaction

pytestmark = pytest.mark.django_db

BOM = "﻿"


def write_csvs(tmp_path):
    rows = [
        "customer_id,bank_account_id,tx_date,tx_timestamp,category,"
        "tx_amount_eur,balance_after_eur,transaction_type,merchant_id,mcc_code"
    ]
    bal = 1000.0
    for month in (7, 8, 9, 10):
        for day, amt, cat, ttype, merch, mcc in (
            (25, 2000, "salary", "credit_transfer", "EMP", ""),
            (1, -650, "housing", "debit_transfer", "RENT", "6513"),
            (15, -12.99, "entertainment", "card", "NETFLIX", "4899.0"),
            (26, -150, "savings", "own_transfer", "SELF", ""),
        ):
            bal += amt
            rows.append(
                f"C1,A1,2026-{month:02d}-{day:02d},2026-{month:02d}-{day:02d} "
                f"12:00:00,{cat},{amt},{bal},{ttype},{merch},{mcc}"
            )
    rows.append("C2,B1,2026-10-02,2026-10-02 10:00:00,food,-5,10,card,CAFE,5814")
    rows.append("C2,B2,2026-10-03,2026-10-03 10:00:00,food,-5,5,card,CAFE,5814")
    (tmp_path / "tx_junction_transactions.csv").write_text(BOM + "\n".join(rows) + "\n")
    (tmp_path / "tx_customers_junction.csv").write_text(
        BOM
        + "customer_id,customer_postal_code,customer_age\nC1,00510,24\nC2,33100,31\n"
    )
    (tmp_path / "mtg_tx_customer_link_and_final_mtg_infio.csv").write_text(
        BOM + "mortgage_customer_id,customer_id,final_outcome\nM1,C1,approved\n"
    )
    (tmp_path / "mtg_negotiation_history.csv").write_text(
        BOM + "mortgage_customer_id,event\nM1,applied\n"
    )
    return tmp_path


def test_load_data_filters_customers(tmp_path):
    data = write_csvs(tmp_path)
    call_command(
        "load_data", "--customers", "C1", "--data-dir", str(data), stdout=io.StringIO()
    )
    assert Transaction.objects.filter(customer_id="C1").count() == 16
    assert not Transaction.objects.filter(customer_id="C2").exists()
    assert Customer.objects.get(customer_id="C1").age == 24
    assert MortgageOutcome.objects.get().outcome == "approved"
    assert Transaction.objects.filter(mcc_code="4899").count() == 4
    df = services.transactions_df("C1")
    assert list(df.columns) == services.TX_COLUMNS
    assert df["tx_amount_eur"].sum() == pytest.approx(4 * (2000 - 650 - 12.99 - 150))


def test_lfs_pointer_detected(tmp_path):
    (tmp_path / "tx_junction_transactions.csv").write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\n"
    )
    (tmp_path / "tx_customers_junction.csv").write_text(
        "customer_id,customer_postal_code,customer_age\nC1,00510,24\n"
    )
    with pytest.raises(CommandError, match="Git LFS"):
        call_command(
            "load_data",
            "--customers",
            "C1",
            "--data-dir",
            str(tmp_path),
            stdout=io.StringIO(),
        )


def test_explore_data_writes_profile(tmp_path):
    data = write_csvs(tmp_path)
    out = tmp_path / "data_profile.md"
    call_command(
        "explore_data",
        "--data-dir",
        str(data),
        "--out",
        str(out),
        stdout=io.StringIO(),
    )
    text = out.read_text()
    assert "Transactions: 18" in text
    assert "more than one bank_account_id: 1" in text


def test_rank_demo_customers(tmp_path):
    data = write_csvs(tmp_path)
    buf = io.StringIO()
    call_command("rank_demo_customers", "--data-dir", str(data), stdout=buf)
    assert "DEMO_CUSTOMERS=" in buf.getvalue()


def test_run_evals_skips_without_key():
    buf = io.StringIO()
    call_command("run_evals", stdout=buf)
    assert "skipped" in buf.getvalue()
