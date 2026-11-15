"""#71: which goals count towards a level."""

import pytest

from inferences.goals import counts_towards_level


@pytest.mark.parametrize(
    "goal, level",
    [
        ({"type": "safety_net", "on_track": True, "progress_pct": 0.0}, 3),
        ({"type": "custom", "on_track": True, "progress_pct": 5.0}, 4),
        ({"type": "plan", "on_track": True, "progress_pct": 0.0}, None),
        ({"type": "custom", "on_track": False, "progress_pct": 5.0}, None),
    ],
)
def test_goals_count_towards_level_4_once_money_is_saved(goal, level):
    assert counts_towards_level(goal) == level
