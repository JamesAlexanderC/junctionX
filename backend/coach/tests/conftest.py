"""Shared fixtures: a scripted fake Gemini client, and Test Aino loaded into
the test database as a real customer (no runtime fixture fallback exists)."""

from datetime import date, timezone
from pathlib import Path

import pytest
from google.genai import types

from coach import services
from coach.models import Account, Customer, Transaction

TODAY = date(2026, 10, 18)
AINO = "C-AINO"
FIXTURES = Path(__file__).parent / "fixtures"


def response(*calls):
    parts = [types.Part.from_function_call(name=n, args=a) for n, a in calls]
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))]
    )


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": list(contents)})
        if len(self.script) > 1:
            return self.script.pop(0)
        return self.script[0]


class FakeClient:
    """Returns scripted function calls; the last response repeats forever."""

    def __init__(self, *script):
        self.models = FakeModels(script)


def load_customer(df, customer_id, age=24, postal_code="00510"):
    """Insert a transactions DataFrame (CLAUDE.md columns) as a customer."""
    Customer.objects.create(customer_id=customer_id, age=age, postal_code=postal_code)
    for acc in df["bank_account_id"].unique():
        Account.objects.create(
            bank_account_id=f"{customer_id}-{acc}", customer_id=customer_id
        )
    Transaction.objects.bulk_create(
        [
            Transaction(
                tx_id=f"{customer_id}-{r.tx_id}",
                customer_id=customer_id,
                account_id=f"{customer_id}-{r.bank_account_id}",
                tx_date=r.tx_date.date(),
                tx_timestamp=r.tx_timestamp.to_pydatetime().replace(
                    tzinfo=timezone.utc
                ),
                category=r.category,
                tx_amount_eur=float(r.tx_amount_eur),
                balance_after_eur=float(r.balance_after_eur),
                transaction_type=r.transaction_type,
                merchant_id=r.merchant_id,
                mcc_code=r.mcc_code,
            )
            for r in df.itertuples()
        ]
    )


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch, settings):
    settings.AS_OF_DATE = TODAY.isoformat()
    settings.DEMO_MODE = False
    settings.GEMINI_API_KEY = ""
    services.inference_version.cache_clear()
    services.reset_as_of_cache()


@pytest.fixture
def aino(db):
    """Test Aino (inferences/tests/fixtures.py) as customer C-AINO."""
    from inferences.tests.fixtures import aino_df

    load_customer(aino_df(until=TODAY), AINO)
    return AINO


@pytest.fixture
def fake_gemini(monkeypatch):
    """Install a FakeClient as the Gemini client: fake_gemini(*responses)."""

    def install(*script):
        client = FakeClient(*script)
        monkeypatch.setattr("coach.gemini.loop.get_client", lambda: client)
        return client

    return install


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user("demo", password="demo-pass-123")


@pytest.fixture
def anon_client():
    """An API client with no token: every endpoint but login answers 401."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def client(user):
    """API client logged in with a real token, as the frontend sends it."""
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return api
