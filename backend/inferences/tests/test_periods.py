"""F8 (handoff/Gemini_fix.md): "last month" is the latest complete month.

The data ends on 30 Sep 2026, so September is complete and "last month"
must be September (tests 1, 21, 30, 31 said August).
"""

from datetime import date

import pytest

from inferences.common import last_complete_month


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 9, 30), "2026-09"),  # last day: this month is complete
        (date(2026, 10, 5), "2026-09"),  # early October: September
        (date(2026, 9, 15), "2026-08"),  # mid-month: the month before
        (date(2026, 2, 28), "2026-02"),  # February's last day
        (date(2026, 1, 1), "2025-12"),  # new year
    ],
)
def test_last_complete_month(today, expected):
    assert last_complete_month(today) == expected
