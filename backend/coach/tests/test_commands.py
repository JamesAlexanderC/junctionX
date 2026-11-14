"""Management commands on a tiny synthetic CSV set."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from coach import services
from coach.models import Customer, MortgageOutcome, Transaction

pytestmark = pytest.mark.django_db

BOM = "﻿"


MONTHS = {7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT"}


def write_csvs(tmp_path):
    rows = [
        "customer_id,bank_account_id,tx_date,tx_timestamp,category,"
        "tx_amount_eur,balance_after_eur,transaction_type,merchant_id,mcc_code"
    ]
    bal = 1000.0
    for month in (7, 8, 9, 10):
        for day, amt, cat, ttype, merch, mcc in (
            (25, 2000, "Salary", "salary", "EMP", ""),
            (1, -650, "Housing", "housing_payment", "RENT", ""),
            (15, -12.99, "Entertainment", "purchase", "NETFLIX", "4899.0"),
            (26, -150, "Invest Deposit", "investment_deposit", "", ""),
        ):
            bal += amt
            rows.append(
                f"C1,A1,2026-{month:02d}-{day:02d},{day:02d}{MONTHS[month]}26:"
                f"12:00:00,{cat},{amt},{bal},{ttype},{merch},{mcc}"
            )
    rows.append(
        "C2,B1,2026-10-02,02OCT26:10:00:00,Restaurants,-5,10,purchase,CAFE,5814"
    )
    rows.append("C2,B2,2026-10-03,03OCT26:10:00:00,Restaurants,-5,5,purchase,CAFE,5814")
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


def test_build_profiles_end_to_end_serves_home(tmp_path, client):
    data = write_csvs(tmp_path)
    call_command(
        "load_data", "--customers", "C1", "--data-dir", str(data), stdout=io.StringIO()
    )
    call_command("build_profiles", stdout=io.StringIO())
    resp = client.get("/api/home/C1/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"] == services.today().isoformat()
    assert body["income"]["monthly_income"] == pytest.approx(2000)
    assert body["baskets"]["monthly_saving"] == pytest.approx(150)


def test_refresh_profile_includes_db_goals(tmp_path):
    from coach.models import Goal

    data = write_csvs(tmp_path)
    call_command(
        "load_data", "--customers", "C1", "--data-dir", str(data), stdout=io.StringIO()
    )
    Goal.objects.create(
        customer_id="C1",
        name="Trip",
        target=600,
        saved=100,
        start_date="2026-09-01",
        target_date="2027-03-01",
    )
    out = services.refresh_profile("C1")
    names = [g["name"] for g in out["goals"]["active"]]
    assert names == ["Trip"]


def test_build_profiles_uses_the_shared_reference_date(tmp_path, client):
    # P1.1: every customer is profiled as of max(tx_date) over all data, even
    # when their own transactions stop earlier.
    data = write_csvs(tmp_path)
    call_command(
        "load_data",
        "--customers",
        "C1,C2",
        "--data-dir",
        str(data),
        stdout=io.StringIO(),
    )
    call_command("build_profiles", stdout=io.StringIO())
    assert client.get("/api/home/C2/").json()["today"] == services.today().isoformat()


def _load_c1(tmp_path):
    data = write_csvs(tmp_path)
    call_command(
        "load_data", "--customers", "C1", "--data-dir", str(data), stdout=io.StringIO()
    )


def test_refresh_profile_fills_stress_test_for_real_customers(tmp_path):
    from coach.models import LoanDetails

    _load_c1(tmp_path)
    LoanDetails.objects.create(
        customer_id="C1", balance=200000, interest_rate=0.04, years_left=25
    )
    out = services.refresh_profile("C1")
    assert out["mortgage"]["stress_test"] is not None


def test_build_profile_receives_goals_with_on_track(tmp_path, monkeypatch):
    from coach.models import Goal
    from inferences import profile as profile_mod

    _load_c1(tmp_path)
    Goal.objects.create(
        customer_id="C1",
        name="Trip",
        target=600,
        saved=590,
        start_date="2026-09-01",
        target_date="2027-03-01",
    )
    seen = {}
    real = profile_mod.build_profile

    def spy(df, customer, today, goals=None, loans=None):
        seen["goals"] = goals
        return real(df, customer, today, goals=goals, loans=loans)

    monkeypatch.setattr(profile_mod, "build_profile", spy)
    services.refresh_profile("C1")
    assert seen["goals"][0]["on_track"] is True


def test_refresh_profile_ignores_demo_fixture_date(tmp_path, settings, monkeypatch):
    from datetime import date

    _load_c1(tmp_path)
    settings.DEMO_MODE = True
    monkeypatch.setattr(services, "today", lambda: date(2026, 10, 26))
    assert services.refresh_profile("C1")["today"] == "2026-10-26"
