"""Reuse the coach fixtures (auth clients, test customer, fixed today)."""

import pytest

from coach.tests.conftest import (  # noqa: F401
    AINO,
    aino,
    anon_client,
    client,
    fixed_today,
    user,
)
from multibank import data as mb_data
from multibank import scenarios as sc
from multibank.synthetic import generate


@pytest.fixture
def synthetic(monkeypatch):
    """Synthetic data in which the test customer holds the hero's accounts."""
    generated = generate(seed=42)
    generated["customers"] = {AINO: generated["customers"][sc.HERO]}
    monkeypatch.setattr(mb_data, "external_data", lambda: generated)
    return generated
