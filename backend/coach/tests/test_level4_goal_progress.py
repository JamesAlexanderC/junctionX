"""#31: a new goal counts towards Level 4 only once money is saved."""

from datetime import timedelta

import pytest

from coach import services
from coach.models import Goal

from .conftest import AINO

pytestmark = pytest.mark.django_db


def _level_4(customer_id):
    ladder = services.get_profile(customer_id)["levels"]["ladder"]
    return next(step for step in ladder if step["level"] == 4)["reached"]


def test_an_accepted_plan_counts_only_after_money_is_saved(aino):
    on = services.today()
    goal = Goal.objects.create(
        customer_id=AINO,
        name="My money plan",
        type="plan",
        target=30,
        start_date=on,
        target_date=on + timedelta(days=90),
    )
    services.refresh_profile(AINO)
    assert _level_4(AINO) is False
    goal.saved = 10
    goal.save()
    services.refresh_profile(AINO)
    assert _level_4(AINO) is True
