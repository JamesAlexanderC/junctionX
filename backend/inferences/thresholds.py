"""Every threshold and constant used by the inferences (context.md #1 to #33).

All values are starting points from context.md: tune them on the demo customers.
Category, transaction_type and MCC sets marked TODO are guesses until P1.1 has
profiled the real S-Bank data and the S-Bank data scientist has confirmed them.
"""

# --- Data vocabulary (TODO confirm with S-Bank data) ---------------------------

# transaction_type values that mark a transfer between the customer's own
# accounts (savings, investments, other own current accounts).
# TODO confirm with S-Bank data.
OWN_TRANSFER_TYPES = frozenset(
    {"own_transfer", "internal_transfer", "savings_transfer", "own_account"}
)

# Categories counted as Essentials (#7). TODO confirm with S-Bank data.
ESSENTIAL_CATEGORIES = frozenset(
    {
        "housing",
        "rent",
        "utilities",
        "insurance",
        "loans",
        "loan",
        "groceries",
        "health",
        "public_transport",
        "public transport",
        # Car repairs are the doc's own Surprise example, so vehicle upkeep
        # is treated as essential. TODO confirm with S-Bank data.
        "vehicle",
    }
)

# MCCs counted as Saver (#75): security brokers and other investment codes.
# TODO confirm with S-Bank data.
INVESTMENT_MCCS = frozenset({"6211", "6012"})

# Loan / credit categories and MCCs (#42, #76-#84). TODO confirm with S-Bank data.
LOAN_CATEGORIES = frozenset({"loans", "loan", "credit", "mortgage", "bnpl"})
LOAN_MCCS = frozenset({"6141", "6051"})

# --- Shared definitions --------------------------------------------------------

WINDOW_FULL_MONTHS = 3  # default window: last 3 full months
BUFFER_MIN_EUR = 50.0  # buffer = max(EUR 50, 10% of monthly essentials)
BUFFER_ESSENTIALS_SHARE = 0.10

# --- Recurrence detection (model 1) --------------------------------------------

RECURRENCE_MIN_MONTHS = 3  # seen in at least 3 ...
RECURRENCE_WINDOW_MONTHS = 4  # ... of the last 4 months
RECURRENCE_GAP_MIN_DAYS = 25
RECURRENCE_GAP_MAX_DAYS = 35

# --- Income and bills (#1 to #6) ----------------------------------------------

SALARY_CV_MAX = 0.15  # #1
INCOME_MEDIAN_MONTHS = 3  # #2
STABILITY_MONTHS = 6  # #3
STABILITY_STEADY_CV = 0.10
STABILITY_VARIES_CV = 0.30
BILL_CV_MAX = 0.20  # #4
SUBSCRIPTION_MAX_EUR = 30.0  # #5
SUBSCRIPTION_CV_MAX = 0.02
UNUSED_SUBSCRIPTION_DAYS = 90  # #6

# --- Baskets (#7 to #10, #75) ---------------------------------------------------

LEAKY_MAX_EUR = 25.0  # #9
SURPRISE_IQR_K = 1.5  # #8: Q3 + 1.5 x IQR
SURPRISE_MIN_HISTORY = 8  # below this, use 3 x category median
SURPRISE_MEDIAN_MULT = 3.0
# With no earlier payment in the category at all, the doc gives no rule; a
# one-off essential payment above this is called a Surprise. Tune on demo data.
SURPRISE_NO_HISTORY_MIN_EUR = 100.0
BASKET_TREND_MONTHS = 3  # #10 trend vs mean of previous 3 months

# --- Habits (#11 to #16) --------------------------------------------------------

WEEKEND_EXPECTED_SHARE = 2 / 7
WEEKEND_FLAG_SHARE = 1.5 * WEEKEND_EXPECTED_SHARE  # ~43%
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 5
NIGHT_FLAG_SHARE = 0.15
BURST_SIZE = 3  # #13: 3 or more purchases ...
BURST_WINDOW_MINUTES = 60  # ... within 60 minutes
IMPULSE_FLAG_BURSTS = 4  # bursts per month
PAYDAY_SPLURGE_DAYS = 3  # days 0 to 3 after payday
PAYDAY_SPLURGE_FLAG = 1.4
LOYAL_HHI = 0.15
EXPLORER_HHI = 0.05
EXPLORER_MERCHANTS_PER_MONTH = 25
STEADY_PLANNER_MAX_SCORE = 0.5
STEADY_PLANNER_SAVER_SHARE = 0.10

# --- Anomalies (#38 to #41) -----------------------------------------------------

ROBUST_Z_CONST = 0.6745
ROBUST_Z_FLAG = 3.5
UNUSUAL_MIN_HISTORY = 3
UNUSUAL_CATEGORY_MULT = 3.0
DUPLICATE_WINDOW_MINUTES = 10
SPIKE_MULT = 1.5
SPIKE_MIN_DIFF_EUR = 20.0
OWN_TRANSFER_MATCH_DAYS = 1

# --- Forecasts (#17 to #23) -----------------------------------------------------

DISCRETIONARY_DAYS = 60  # #19 window for d and sigma
BAND_Z = 1.28  # 80% band
DANGER_BALANCE_EUR = 50.0  # #20
UPCOMING_BILLS_DAYS = 30  # #21
NO_PAYDAY_HORIZON_DAYS = 30  # horizon when no payday was found
SEASONAL_WARN_RATIO = 1.25  # #23
DEFAULT_CYCLE_DAYS = 30

# --- What-ifs (#24 to #27) ------------------------------------------------------

# #27 reference prices in EUR. Rough 2026 Finnish prices; tune if needed.
HABIT_REFERENCES = (
    ("month of gym", 45.0),
    ("train ticket Helsinki-Tampere", 30.0),
    ("cinema ticket", 14.0),
)

# --- Levels (#28 to #33) --------------------------------------------------------

LEVEL_NAMES = {
    1: "Getting started",
    2: "In control",
    3: "Safety net",
    4: "Goal setter",
    5: "Mortgage ready",
    6: "Wealth builder",
}
SAFETY_NET_MONTHS = 1.0  # #30
MORTGAGE_READY_SCORE = 0.75  # #32
WEALTH_BUFFER_MONTHS = 3.0  # Level 6
WEALTH_SAVER_SHARE = 0.10
WEALTH_SAVER_MONTHS = 3
NEXT_STEP_CUTS = (0.10, 0.20, 0.30)  # #33
NEXT_STEP_MONTHS = 3

# --- Goals helpers (#49, #52, #65) -------------------------------------------------

GOAL_EASY_MONTHS = 2  # <= 2 Easy, 3 to 6 Stretch, > 6 Hard
GOAL_STRETCH_MONTHS = 6
GOAL_ROUND_EUR = 5
ON_TRACK_FACTOR = 0.9

# --- Loans (#77, #82) -----------------------------------------------------------

STRESS_ANNUAL_RATE = 0.06
STRESS_MONTHS = 300
