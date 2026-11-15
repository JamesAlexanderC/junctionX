"""Fix 4 (demo hardening): DEBUG from the environment, JSON error pages.

With DEBUG hard-coded on, a wrong URL answered with Django's HTML page that
lists every route. pytest-django runs with DEBUG off, like the demo.
"""

import pytest
from django.test import RequestFactory
from django.utils.module_loading import import_string

from conf.settings import env_flag


@pytest.mark.parametrize(
    "value, expected",
    [("1", True), ("true", True), ("Yes", True), ("0", False), ("", False)],
)
def test_env_flag_reads_true_values(monkeypatch, value, expected):
    monkeypatch.setenv("SALDO_TEST_FLAG", value)
    assert env_flag("SALDO_TEST_FLAG") is expected


def test_env_flag_defaults_to_off(monkeypatch):
    monkeypatch.delenv("SALDO_TEST_FLAG", raising=False)
    assert env_flag("SALDO_TEST_FLAG") is False


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/no-such-route/", "/nowhere/"])
def test_unknown_url_is_a_json_404_without_routes(client, path):
    res = client.get(path)
    assert res.status_code == 404
    assert res["Content-Type"].startswith("application/json")
    assert res.json() == {"error": "Not found"}
    assert b"api/home" not in res.content


def test_server_error_is_json():
    from conf.urls import handler500

    res = import_string(handler500)(RequestFactory().get("/api/x/"))
    assert res.status_code == 500
    assert res["Content-Type"].startswith("application/json")
