"""MB-4: linked banks flow into the profile; revoking restores S-Bank only."""

import pytest

from coach import services
from multibank.models import ExternalTransaction

from .conftest import AINO

pytestmark = pytest.mark.django_db


def _connect(client, bank="NDEAFIHH"):
    consent = client.post(
        "/api/consents/", {"customer_id": AINO, "bank_code": bank}, format="json"
    ).json()
    client.post(f"/api/consents/{consent['consent_id']}/authorise/")
    return consent["consent_id"]


def _strip(profile):
    return {k: v for k, v in profile.items() if k not in ("generated_at", "multibank")}


def test_linking_adds_the_bank_and_keeps_the_sbank_only_numbers(
    client, aino, synthetic
):
    before = services.get_profile(AINO)
    _connect(client)
    after = services.get_profile(AINO)
    mb = after["multibank"]
    assert mb["connected_banks"] == ["Nordea"] and mb["simulated"] is True
    assert mb["hidden_loans"][0]["bank"] == "Nordea"
    assert mb["sbank_only"]["monthly_income"] == before["income"]["monthly_income"]
    assert set(mb["delta"]) >= {
        "safe_to_spend",
        "dsti",
        "buffer_months",
        "level",
        "monthly_income",
    }
    assert mb["delta"]["level"]["before"] == before["levels"]["current"]


def test_revoking_gives_back_the_sbank_only_profile(client, aino, synthetic):
    before = services.get_profile(AINO)
    consent_id = _connect(client)
    client.delete(f"/api/consents/{consent_id}/")
    after = services.get_profile(AINO)
    assert _strip(after) == _strip(before)
    assert after["multibank"]["connected_banks"] == []


def test_matched_transfers_are_marked_on_the_external_rows(
    client, aino, monkeypatch, synthetic
):
    # A transfer from S-Bank to the linked account, same amount the next day.
    sbank = services.transactions_df(AINO)
    out = sbank[sbank["tx_amount_eur"] < 0].iloc[-1]
    account = synthetic["customers"][AINO]["NDEAFIHH"]["accounts"][0]
    day = (out["tx_date"] + __import__("pandas").Timedelta(days=1)).date()
    account["transactions"].append(
        {
            "transactionId": "MIRROR-1",
            "bookingDate": day.isoformat(),
            "transactionAmount": {
                "amount": f"{-out['tx_amount_eur']:.2f}",
                "currency": "EUR",
            },
            "debtorName": "Own account at S-Bank",
            "proprietaryBankTransactionCode": "TRANSFER",
            "merchantCategoryCode": None,
        }
    )
    _connect(client)
    assert ExternalTransaction.objects.filter(own_transfer=True).count() == 1
