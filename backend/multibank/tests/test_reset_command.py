"""MB-9: reset_multibank_demo disconnects so the beat starts S-Bank only."""

from io import StringIO

import pytest
from django.core.management import call_command

from multibank import scenarios as sc
from multibank.models import BankConsent, ExternalTransaction

from .conftest import AINO

pytestmark = pytest.mark.django_db


def _connect(client):
    consent = client.post(
        "/api/consents/", {"customer_id": AINO, "bank_code": "NDEAFIHH"}, format="json"
    ).json()
    client.post(f"/api/consents/{consent['consent_id']}/authorise/")


def test_reset_all_revokes_and_deletes_linked_rows(client, aino, synthetic):
    _connect(client)
    assert ExternalTransaction.objects.exists()
    out = StringIO()
    call_command("reset_multibank_demo", "--all", stdout=out)
    assert not BankConsent.objects.filter(status="active").exists()
    assert not ExternalTransaction.objects.exists()
    assert f"{AINO}: disconnected (sbank_only)" in out.getvalue()


def test_reset_by_default_only_touches_scenario_customers(client, aino, synthetic):
    _connect(client)
    call_command("reset_multibank_demo", stdout=StringIO())
    assert AINO not in sc.BANKS  # sanity: the test customer is not a scenario
    assert BankConsent.objects.filter(customer_id=AINO, status="active").exists()
