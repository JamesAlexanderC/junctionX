"""Thresholds and category/MCC sets for the alert rules (context.md #6 to #102).

All values are starting points: tune them on the demo customers. Category and
MCC sets come from inferences/thresholds.py, profiled on the real data
(docs/vocabulary.md).
"""

# Priority weights: priority = weight / max(1, days until impact).
SEVERITY_WEIGHT = {"red": 3, "amber": 2, "blue": 1}

from inferences.thresholds import (  # noqa: F401  shared with the inferences
    BUFFER_ESSENTIALS_SHARE,
    BUFFER_MIN_EUR,
    ATM_MCC,
    FEE_CATEGORIES,
    FEE_MCCS,
    GAMBLING_MCC,
    LOAN_CATEGORIES,
    LOAN_MCCS,
    OWN_TRANSFER_TYPES,
    SAVER_TYPES,
    SAVER_WITHDRAW_TYPES,
    ROBUST_Z_CONST,
    ROBUST_Z_FLAG,
    STRESS_MONTHS,
    SPIKE_MIN_DIFF_EUR,
    SPIKE_MULT,
    SPIKE_REQUIRE_FULL_HISTORY,
    UNUSUAL_CATEGORY_MULT,
    UNUSUAL_MIN_EXCESS_EUR,
    UNUSUAL_MIN_HISTORY,
    UNUSUAL_MIN_MULT,
)

# Buffer: max(EUR 50, 10% of monthly essentials) (#17, #99, #102) and the
# own-transfer / loan sets live in inferences/thresholds.py.

# Fee, ATM and gambling sets also live in thresholds.py (docs/vocabulary.md).
GAMBLING_SUPPORT_URL = "https://www.peluuri.fi/en"

# #38 unusual charge
RECENT_DAYS = 30

# #39 duplicate charge
DUPLICATE_MINUTES = 10

# #40 category spike
SPIKE_RATIO = SPIKE_MULT  # thresholds.py is the single source

# #62 life change / #83 new credit: "new" = first seen in the last 2 months.
NEW_RECURRING_DAYS = 62
LIFE_CHANGE_INCOME_SHARE = 0.10

# Recurrence (context.md model 1).
RECUR_GAP_MIN = 25
RECUR_GAP_MAX = 35
RECUR_CV_MAX = 0.20

# #76 loan burden (DSTI)
DSTI_AMBER = 0.40
DSTI_RED = 0.50

# #77 / #82 FIN-FSA stress test
STRESS_RATE = 0.06  # == thresholds.STRESS_ANNUAL_RATE
STRESS_DSTI_MAX = 0.60
AFFORD_FITS_MAX = 0.50

# #79 payment changed, #80 missed payment
PAYMENT_CHANGE_PCT = 0.05
MISSED_PAYMENT_GRACE_DAYS = 5

# #84 many lenders
MANY_LENDERS_MIN = 3
MANY_LENDERS_DAYS = 90

# #87 income dropped
INCOME_DROP_RATIO = 0.8
INCOME_DROP_CHECK_DAYS = 5

# #88 spending pace
PACE_MIN_DAY = 7

# #89 lifestyle creep: leaky share up this many months in a row.
CREEP_MONTHS = 3

# #90 subscription creep
SUB_CREEP_RATIO = 1.20
SUB_CREEP_MONTHS_BACK = 6

# #91 free trial turned paid
TRIAL_MAX_EUR = 1.0
TRIAL_GAP_MIN = 25
TRIAL_GAP_MAX = 35
TRIAL_RECENT_DAYS = 45

# #93 annual bill
ANNUAL_GAP_MIN = 350
ANNUAL_GAP_MAX = 380
ANNUAL_LOOKAHEAD_DAYS = 30

# #95 saving streak broken
SAVING_STREAK_GRACE_DAYS = 5
SAVING_STREAK_MIN_TRANSFERS = 2

# #96 cash withdrawals up
CASH_UP_RATIO = 1.5

# #97 small leaks
SMALL_LEAK_EUR = 3.0
SMALL_LEAK_COUNT = 15

# #100 payday missed
PAYDAY_MISSED_DAYS = 3

# #101 bill went up
BILL_UP_RATIO = 1.10

# #102 big bill coming
BIG_BILL_DAYS = 3

# #52 goal off track: re-check horizon used as its impact date.
GOAL_REVIEW_DAYS = 30
