"""Token auth: every API endpoint needs a token from POST /api/auth/login/."""

import pytest
from rest_framework.authtoken.models import Token

pytestmark = pytest.mark.django_db

PROTECTED = [
    ("get", "/api/customers/"),
    ("get", "/api/home/C-AINO/"),
    ("get", "/api/insights/C-AINO/"),
    ("get", "/api/alerts/C-AINO/"),
    ("post", "/api/chat/"),
    ("post", "/api/goals/"),
    ("patch", "/api/goals/1/"),
    ("post", "/api/goals/1/rate/"),
    ("post", "/api/loans/"),
    ("post", "/api/alerts/a-1/snooze/"),
    ("get", "/api/auth/me/"),
    ("post", "/api/auth/logout/"),
]


@pytest.mark.parametrize("method,url", PROTECTED)
def test_every_endpoint_needs_a_token(anon_client, method, url):
    res = getattr(anon_client, method)(url, {}, format="json")
    assert res.status_code == 401


def test_a_bad_token_is_rejected(anon_client):
    anon_client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert anon_client.get("/api/customers/").status_code == 401


def test_login_returns_a_token_that_opens_the_api(anon_client, user, aino):
    res = anon_client.post(
        "/api/auth/login/",
        {"username": "demo", "password": "demo-pass-123"},
        format="json",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user"] == {"username": "demo"}
    anon_client.credentials(HTTP_AUTHORIZATION=f"Token {body['token']}")
    assert anon_client.get("/api/customers/").status_code == 200
    assert anon_client.get("/api/auth/me/").json() == {"user": {"username": "demo"}}


def test_login_twice_returns_the_same_token(anon_client, user):
    creds = {"username": "demo", "password": "demo-pass-123"}
    first = anon_client.post("/api/auth/login/", creds, format="json").json()
    second = anon_client.post("/api/auth/login/", creds, format="json").json()
    assert first["token"] == second["token"]


@pytest.mark.parametrize(
    "creds",
    [
        {"username": "demo", "password": "wrong"},
        {"username": "nobody", "password": "demo-pass-123"},
    ],
)
def test_wrong_credentials_are_refused(anon_client, user, creds):
    res = anon_client.post("/api/auth/login/", creds, format="json")
    assert res.status_code == 400
    assert res.json() == {"error": "Wrong username or password"}


def test_inactive_users_cannot_log_in(anon_client, user):
    user.is_active = False
    user.save()
    creds = {"username": "demo", "password": "demo-pass-123"}
    assert anon_client.post("/api/auth/login/", creds, format="json").status_code == 400


def test_logout_deletes_the_token(client, user):
    assert client.post("/api/auth/logout/").status_code == 204
    assert not Token.objects.filter(user=user).exists()
    assert client.get("/api/customers/").status_code == 401


def test_api_docs_stay_public(anon_client):
    assert anon_client.get("/api/schema/").status_code == 200
