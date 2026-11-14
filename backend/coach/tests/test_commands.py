"""Management commands on a tiny synthetic CSV set."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from coach import services
from coach.management import csvdata
from coach.models import Customer, MortgageEvent, MortgageOutcome, Transaction

pytestmark = pytest.mark.django_db

BOM = "﻿"


MONTHS = {7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT"}


def sas(month, day, hhmm="12:00:00"):
    """The real CSVs' SAS datetime format, e.g. 25JUL26:12:00:00."""
    return f"{day:02d}{MONTHS[month]}26:{hhmm}"


def write_csvs(tmp_path):
    rows = [
        "customer_id,bank_account_id,tx_date,tx_timestamp,category,"
        "tx_amount_eur,balance_after_eur,transaction_type,merchant_id,mcc_code"
    ]
    bal = 1000.0
    for month in (7, 8, 9, 10):
        for day, amt, cat, ttype, merch, mcc in (
            (15, 2000, "Salary", "salary", "", ""),
            (1, -650, "Housing", "housing_payment", "", ""),
            (12, -12.5, "Restaurants", "purchase", "MRC-RES-1", "5814.0"),
            (16, -150, "Invest Deposit", "investment_deposit", "", ""),
        ):
            bal += amt
            rows.append(
                f"C1,A1,2026-{month:02d}-{day:02d},{sas(month, day)},{cat},{amt},"
                f"{bal},{ttype},{merch},{mcc}"
            )
    rows.append(
        f"C2,B1,2026-10-02,{sas(10, 2, '21:30:05')},Restaurants,-5,10,"
        "purchase,MRC-RES-2,5814"
    )
    (tmp_path / "tx_junction_transactions.csv").write_text(BOM + "\n".join(rows) + "\n")
    (tmp_path / "tx_customers_junction.csv").write_text(
        BOM
        + "customer_id,customer_postal_code,customer_age\nC1,00510,24\nC2,33100,31\n"
    )
    (tmp_path / "mtg_tx_customer_link_and_final_mtg_infio.csv").write_text(
        BOM + "mortgage_customer_id,customer_id,final_decision,rejection_reason,"
        "final_property_price_eur,final_requested_loan_eur,final_equity_amount_eur,"
        "final_collateral_value_eur,required_monthly_income_eur,"
        "lfinal_loan_to_value\n"
        "M1,C1,approved,,203000,170500,32500,132500,3138.67,0.84\n"
    )
    (tmp_path / "mtg_negotiation_history.csv").write_text(
        BOM + "mortgage_customer_id,timestamp,event_type,decision,note\n"
        "M1,26MAY26:00:00:00,application_created,,Started.\n"
        "M1,27MAY26:19:36:59,customer_contact,,Called.\n"
    )
    return tmp_path


def test_load_data_loads_everything(tmp_path):
    data = write_csvs(tmp_path)
    call_command(
        "load_data",
        "--data-dir",
        str(data),
        "--skip-artifacts",
        stdout=io.StringIO(),
    )
    assert Customer.objects.count() == 2
    assert Transaction.objects.filter(customer_id="C1").count() == 16
    assert Transaction.objects.filter(customer_id="C2").count() == 1
    assert Customer.objects.get(customer_id="C1").age == 24
    outcome = MortgageOutcome.objects.get()
    assert outcome.approved and outcome.final_loan_to_value == pytest.approx(0.84)
    event = MortgageEvent.objects.get(event_type="application_created")
    assert event.timestamp.date().isoformat() == "2026-05-26"
    assert Transaction.objects.filter(mcc_code="5814").count() == 5
    df = services.transactions_df("C1")
    assert list(df.columns) == services.TX_COLUMNS
    assert df["tx_amount_eur"].sum() == pytest.approx(4 * (2000 - 650 - 12.5 - 150))
    # SAS timestamps keep their time of day (night spending #12 needs it).
    late = services.transactions_df("C2")["tx_timestamp"].iloc[0]
    assert (late.hour, late.minute, late.second) == (21, 30, 5)


def test_load_data_refuses_reload_without_replace(tmp_path):
    data = write_csvs(tmp_path)
    args = ["load_data", "--data-dir", str(data), "--skip-artifacts"]
    call_command(*args, stdout=io.StringIO())
    with pytest.raises(CommandError, match="--replace"):
        call_command(*args, stdout=io.StringIO())
    call_command(*args, "--replace", stdout=io.StringIO())
    assert Transaction.objects.count() == 17


def test_load_data_customer_subset(tmp_path):
    data = write_csvs(tmp_path)
    call_command(
        "load_data",
        "--customers",
        "C1",
        "--data-dir",
        str(data),
        "--skip-artifacts",
        stdout=io.StringIO(),
    )
    assert not Transaction.objects.filter(customer_id="C2").exists()


def test_build_artifacts_and_profiles(tmp_path, settings):
    settings.AS_OF_DATE = "2026-11-01"
    data = write_csvs(tmp_path)
    call_command("load_data", "--data-dir", str(data), stdout=io.StringIO())
    assert services.peer_table() is not None
    model = services.mortgage_model()
    assert model is not None and model["n_applicants"] == 1
    buf = io.StringIO()
    call_command("build_profiles", "--all", stdout=buf)
    assert "Built 2 profiles" in buf.getvalue()


def test_parse_sas_timestamp():
    stamps = csvdata.parse_timestamp(["03OCT24:09:04:04", "2026-10-01 10:00:00", ""])
    assert str(stamps.iloc[0]) == "2024-10-03 09:04:04"
    assert str(stamps.iloc[1]) == "2026-10-01 10:00:00"
    assert stamps.isna().iloc[2]


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
    assert "Transactions: 17" in text


def test_rank_demo_customers(tmp_path):
    data = write_csvs(tmp_path)
    buf = io.StringIO()
    call_command("rank_demo_customers", "--data-dir", str(data), stdout=buf)
    assert "Suggested demo customers" in buf.getvalue()
    assert "multi-account" not in buf.getvalue()
    assert "high salary sweep" in buf.getvalue()


def test_run_evals_skips_without_key():
    buf = io.StringIO()
    call_command("run_evals", "--customer", "C1", stdout=buf)
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
