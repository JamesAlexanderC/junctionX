"""The same goal boundary cases run in Python and JavaScript."""

import json
from pathlib import Path

import pytest

from inferences.whatif import goal_date

CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "shared/tests/goal_cases.json").read_text()
)


@pytest.mark.parametrize("case", CASES)
def test_shared_goal_cases(case):
    result = goal_date(case["target"], case["saved"], case["rate"], case["today"])
    assert result["months"] == case["months"]
    assert result["date"] == case["date"]
