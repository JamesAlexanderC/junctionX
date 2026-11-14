"""Injected demo events: EUR 5,000 bonus and an overdraft with a EUR 5 fee."""

import io
from datetime import date

import pandas as pd
import pytest
from django.core.management import call_command

from coach import demo_events
from coach.models import Transaction
from coach.tests.test_commands import write_csvs
from inferences import alerts
from inferences.tests.alert_fixtures import profile as alert_profile
from inferences.tests.fixtures import make_df

REF = date(2026, 10, 26)


def _history():
    rows = []
    for m in (8, 9, 10):
        rows.append(
            dict(
                ts=f"2026-{m:02d}-01 09:00",
                amount=1200,
                ttype="salary",
                category="Salary",
                mcc="",
                merchant="EMP",
            )
        )
        for d in (5, 12, 19, 24):
            rows.append(
                dict(
                    ts=f"2026-{m:02d}-{d:02d} 12:00",
                    amount=-250,
                    category="Lifestyle",
                    mcc="5999",
                )
            )
    return make_df(rows, start_balance=100.0)


def test_bonus_adds_5000_and_shifts_later_balances():
    df = _history()
    out = demo_events.inject_bonus(df, REF)
    bonus = out[out["is_synthetic"]]
    assert len(bonus) == 1
    assert bonus["tx_amount_eur"].iloc[0] == 5000
    assert bonus["transaction_type"].iloc[0] == "other_income"
    after = out[
        (~out["is_synthetic"]) & (out["tx_timestamp"] > bonus["tx_timestamp"].iloc[0])
    ]
    orig = df.set_index("tx_id").loc[after["tx_id"], "balance_after_eur"].values
    assert after["balance_after_eur"].values - orig == pytest.approx(5000)


def test_overdraft_goes_negative_with_5_eur_fee_and_fires_alerts():
    out = demo_events.inject_overdraft(_history(), REF)
    synth = out[out["is_synthetic"]]
    assert len(synth) == 2
    fee = synth[synth["category"] == "fee"]
    assert fee["tx_amount_eur"].tolist() == [-5.0]
    assert out["balance_after_eur"].min() == pytest.approx(-45.0)
    ids = {a["inference"] for a in alerts.run_all_alerts(out, alert_profile(), REF)}
    assert {85, 86} <= ids


def test_remove_synthetic_restores_original_balances():
    df = _history()
    injected = demo_events.inject_overdraft(demo_events.inject_bonus(df, REF), REF)
    restored = demo_events.remove_synthetic(injected)
    assert restored["tx_id"].tolist() == df["tx_id"].tolist()
    assert restored["balance_after_eur"].values == pytest.approx(
        df["balance_after_eur"].values
    )


@pytest.mark.django_db
def test_command_is_idempotent_and_flags_rows(tmp_path):
    data = write_csvs(tmp_path)
    call_command(
        "load_data",
        "--customers",
        "C1,C2",
        "--data-dir",
        str(data),
        stdout=io.StringIO(),
    )
    for _ in range(2):
        call_command(
            "inject_demo_events",
            "--saver",
            "C1",
            "--splurger",
            "C2",
            stdout=io.StringIO(),
        )
    bonus = Transaction.objects.filter(customer_id="C1", is_synthetic=True)
    overdraft = Transaction.objects.filter(customer_id="C2", is_synthetic=True)
    assert list(bonus.values_list("tx_amount_eur", flat=True)) == [5000.0]
    assert overdraft.count() == 2
    assert -5.0 in set(overdraft.values_list("tx_amount_eur", flat=True))
    assert Transaction.objects.filter(customer_id="C2").order_by(
        "balance_after_eur"
    ).first().balance_after_eur == pytest.approx(-45.0)


def test_overdraft_needs_history_in_reference_month():
    empty = _history()
    empty = empty[empty["tx_date"] < pd.Timestamp("2026-09-01")]
    with pytest.raises(ValueError, match="no transactions"):
        demo_events.inject_overdraft(empty, REF)


def test_overdraft_refuses_an_implausibly_large_charge():
    rich = make_df(
        [dict(ts="2026-10-05 12:00", amount=-10, category="Lifestyle", mcc="5999")],
        start_balance=9000.0,
    )
    with pytest.raises(ValueError, match="lowest balance"):
        demo_events.inject_overdraft(rich, REF)


def test_injected_balances_are_rounded_to_cents():
    rows = [
        dict(ts=f"2026-10-{d:02d} 12:00", amount=-33.333, category="Lifestyle")
        for d in (3, 9, 20)
    ]
    out = demo_events.inject_bonus(make_df(rows, start_balance=123.456), REF)
    shifted = out[out["tx_date"] > pd.Timestamp("2026-10-16")]["balance_after_eur"]
    assert len(shifted) == 1
    assert (shifted == shifted.round(2)).all()


@pytest.mark.django_db
def test_command_reports_bad_reference_date_cleanly(tmp_path, monkeypatch):
    from django.core.management.base import CommandError

    from coach import services

    data = write_csvs(tmp_path)
    call_command(
        "load_data", "--customers", "C1", "--data-dir", str(data), stdout=io.StringIO()
    )
    monkeypatch.setattr(services, "today", lambda: date(2026, 11, 1))
    with pytest.raises(CommandError, match="C1"):
        call_command(
            "inject_demo_events",
            "--saver",
            "C1",
            "--splurger",
            "C1",
            stdout=io.StringIO(),
        )
