"""MB-3: mock AIS and consent API (create -> authorise -> list -> revoke)."""

import pytest

from multibank.models import BankConsent, ExternalTransaction, LinkedAccount

from .conftest import AINO

pytestmark = pytest.mark.django_db


@pytest.fixture
def rebuilt(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "multibank.views.services.refresh_profile", lambda cid: seen.append(cid)
    )
    return seen


def _create(client, bank="NDEAFIHH", **extra):
    return client.post(
        "/api/consents/",
        {"customer_id": AINO, "bank_code": bank, **extra},
        format="json",
    )


def _connect(client, bank="NDEAFIHH"):
    consent = _create(client, bank).json()
    return client.post(f"/api/consents/{consent['consent_id']}/authorise/").json()


def test_banks_are_a_plain_text_list(client):
    banks = client.get("/api/banks/").json()
    assert {"code": "NDEAFIHH", "name": "Nordea"} in banks
    assert all(set(b) == {"code", "name"} for b in banks)


def test_consent_starts_pending_with_scopes_and_expiry(client, aino):
    body = _create(client).json()
    assert body["status"] == "pending"
    assert body["scopes"] == ["accounts", "balances", "transactions"]
    assert body["expires_at"]


@pytest.mark.parametrize("field", ["password", "username", "pin", "bank_password"])
def test_no_endpoint_accepts_credentials(client, aino, field):
    res = _create(client, **{field: "hunter2"})
    assert res.status_code == 400
    assert BankConsent.objects.count() == 0


def test_unknown_bank_or_customer_is_refused(client, aino):
    assert _create(client, bank="NOPE").status_code == 400
    res = client.post(
        "/api/consents/", {"customer_id": "nobody", "bank_code": "NDEAFIHH"}
    )
    assert res.status_code == 404


def test_authorise_loads_accounts_and_rebuilds_the_profile(
    client, aino, synthetic, rebuilt
):
    body = _connect(client)
    assert body["status"] == "active"
    assert body["accounts_found"] == 1
    assert ExternalTransaction.objects.count() == 12
    loan = ExternalTransaction.objects.filter(mcc="6141").first()
    assert loan.category == "loan_payment" and loan.amount_eur < 0
    assert rebuilt == [AINO]


def test_a_bank_without_data_links_nothing_and_says_so(
    client, aino, synthetic, rebuilt
):
    body = _connect(client, bank="OKOYFIHH")
    assert body["status"] == "active"
    assert body["accounts_found"] == 0
    assert body["message"] == "No accounts found at this bank"
    assert LinkedAccount.objects.count() == 0


def test_accounts_lists_sbank_and_linked_accounts(client, aino, synthetic):
    _connect(client)
    body = client.get(f"/api/accounts/{AINO}/").json()
    accounts = body["accounts"]
    assert body["connected_banks"] == ["Nordea"] and body["coverage"] == "full"
    assert body["delta"]["safe_to_spend"].keys() == {"before", "after"}
    banks = {a["bank"] for a in accounts}
    assert banks == {"S-Bank", "Nordea"}
    linked = next(a for a in accounts if a["bank"] == "Nordea")
    assert linked["simulated"] is True and linked["consent_expires_at"]
    assert linked["iban_masked"].startswith("FI••")


def test_revoke_deletes_rows_and_rebuilds(client, aino, synthetic, rebuilt):
    consent_id = _connect(client)["consent_id"]
    res = client.delete(f"/api/consents/{consent_id}/")
    assert res.status_code == 200 and res.json()["status"] == "revoked"
    assert LinkedAccount.objects.count() == 0
    assert ExternalTransaction.objects.count() == 0
    assert rebuilt == [AINO, AINO]


def test_mock_aspsp_answers_in_berlin_group_shape(client, aino, synthetic, rebuilt):
    consent_id = _connect(client)["consent_id"]
    headers = {"HTTP_CONSENT_ID": str(consent_id)}
    accounts = client.get("/mock-aspsp/NDEAFIHH/v1/accounts", **headers).json()
    account = accounts["accounts"][0]
    assert {"resourceId", "iban", "cashAccountType", "currency"} <= set(account)
    rid = account["resourceId"]
    txs = client.get(
        f"/mock-aspsp/NDEAFIHH/v1/accounts/{rid}/transactions", **headers
    ).json()
    booked = txs["transactions"]["booked"]
    assert {"bookingDate", "transactionAmount", "creditorName"} <= set(booked[0])
    balances = client.get(
        f"/mock-aspsp/NDEAFIHH/v1/accounts/{rid}/balances", **headers
    ).json()
    assert balances["balances"][0]["balanceType"] == "closingBooked"


def test_mock_aspsp_needs_an_active_consent(client, aino, synthetic):
    res = client.get("/mock-aspsp/NDEAFIHH/v1/accounts", HTTP_CONSENT_ID="999")
    assert res.status_code == 403


@pytest.mark.parametrize(
    "method, url",
    [
        ("get", "/api/banks/"),
        ("post", "/api/consents/"),
        ("post", "/api/consents/1/authorise/"),
        ("delete", "/api/consents/1/"),
        ("get", f"/api/accounts/{AINO}/"),
        ("get", "/mock-aspsp/NDEAFIHH/v1/accounts"),
    ],
)
def test_unauthenticated_calls_are_rejected(anon_client, method, url):
    assert getattr(anon_client, method)(url).status_code == 401
