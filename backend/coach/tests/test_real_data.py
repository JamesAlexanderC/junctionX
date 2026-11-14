"""SAS timestamps (P1.2), the reference date and verify_handoff."""

from datetime import date

import pandas as pd
import pytest
from django.core.management.base import CommandError

from coach import services
from coach.management import csvdata
from coach.management.commands import verify_handoff as vh
from coach.models import Account, Customer, Transaction


def test_parses_sas_timestamp():
    out = csvdata.parse_timestamps(pd.Series(["03OCT24:09:04:04"]))
    # Naive timestamps, the same convention as services.transactions_df.
    assert out.iloc[0] == pd.Timestamp("2024-10-03 09:04:04")


def test_raises_when_over_one_percent_fail():
    # ISO values still parse (test CSVs); only unparseable ones count.
    bad = pd.Series(["03OCT24:09:04:04"] * 98 + ["nonsense", "garbage"])
    with pytest.raises(CommandError, match="tx_timestamp"):
        csvdata.parse_timestamps(bad)


def test_tolerates_one_percent_failures():
    raw = pd.Series(["03OCT24:09:04:04"] * 99 + ["nonsense"])
    assert csvdata.parse_timestamps(raw).isna().sum() == 1


@pytest.mark.django_db
def test_reference_date_is_latest_transaction(settings):
    settings.AS_OF_DATE = ""
    services.reset_as_of_cache()
    cust = Customer.objects.create(customer_id="C1")
    acc = Account.objects.create(bank_account_id="A1", customer=cust)
    for i, day in enumerate((date(2026, 9, 1), date(2026, 9, 30))):
        Transaction.objects.create(
            tx_id=f"t{i}",
            customer=cust,
            account=acc,
            tx_date=day,
            tx_timestamp=pd.Timestamp(day, tz="UTC"),
            tx_amount_eur=-1.0,
        )
    assert services.today() == date(2026, 9, 30)
    services.reset_as_of_cache()


@pytest.mark.parametrize(
    "auc,mode,ok",
    [
        (0.74, "model", True),
        (0.62, "percentile_fallback", True),
        (0.62, "model", False),
    ],
)
def test_mortgage_check_enforces_auc_rule(monkeypatch, auc, mode, ok):
    report = {"cv_auc": auc, "mode": mode, "features": ["a"]}
    monkeypatch.setattr(vh, "_model_report", lambda: report)
    assert vh.check_mortgage_model()[0] is ok


def test_crashing_check_reports_failure(monkeypatch):
    def boom():
        raise ValueError("bad")

    monkeypatch.setattr(vh, "CHECKS", ((9, "boom", boom),))
    (result,) = vh.run_checks()
    assert result.ok is False and "ValueError" in result.detail
