"""Every threshold and constant used by the inferences (context.md #1 to #102).

All values are starting points from context.md: tune them on the demo customers.
The data vocabulary below is mapped from the real S-Bank values profiled in
docs/data_profile.md and docs/vocabulary.md (P1.1). Categories are compared
lower-cased (common.prepare() lower-cases them). Values marked "unconfirmed:
ask S-Bank mentor" have no evidence in the data.
"""

# --- Data vocabulary (real S-Bank values, docs/data_profile.md) ----------------

# ~85-90% of salary leaves the day after payday to an account outside the data
# (6,189 rows, 264 customers). It is neutral: neither spending nor Saver.
# unconfirmed: ask S-Bank mentor whether the target account is the customer's.
NEUTRAL_TRANSFER_TYPES = frozenset({"salary_sweep"})
SALARY_TYPES = frozenset({"salary"})

# Saver (#75): deposits count positive, withdrawals negative (#94).
# Evidence: 35,668 "investment_deposit" rows (1,500 customers, monthly, right
# after payday) and 532 "investment_withdrawal" inflows (not income).
SAVER_DEPOSIT_TYPES = frozenset({"investment_deposit"})
SAVER_WITHDRAWAL_TYPES = frozenset({"investment_withdrawal"})
SAVER_TYPES = SAVER_DEPOSIT_TYPES | SAVER_WITHDRAWAL_TYPES

# Own-account transfers: never spending and never income (#2, #41).
OWN_TRANSFER_TYPES = NEUTRAL_TRANSFER_TYPES | SAVER_TYPES

# transaction_type values without a merchant_id that recur on their own. They
# get a pseudo merchant "type:<transaction_type>" in common.prepare(), so
# payday (#1) and bill detection (#4) can group them (salary, rent and
# utilities have no merchant_id in the data).
PSEUDO_MERCHANT_PREFIX = "type:"
# Real merchant ids look like "MRC-GRO-0016"; the middle code is the category
# (checked on all 3.6M rows: one category per code). Users never see the id.
MERCHANT_ID_RE = r"\bMRC-([A-Z]{3})-\d+\b"
MERCHANT_CODE_NAMES = {
    "ENT": "an entertainment merchant",
    "GRO": "a grocery shop",
    "HEA": "a health provider",
    "HMT": "a home and tech shop",
    "LIF": "a lifestyle shop",
    "RES": "a restaurant",
    "TRN": "a transport provider",
    "TRV": "a travel company",
}
UNKNOWN_MERCHANT_NAME = "a shop"

PSEUDO_MERCHANT_NAMES = {
    "salary": "Salary",
    "other_income": "Other income",
    "housing_payment": "Housing",
    "utilities_payment": "Utilities",
    "investment_deposit": "Investments",
    "investment_withdrawal": "Investment withdrawal",
    "salary_sweep": "Salary transfer",
}
# Only these types get a pseudo merchant; purchases keep an empty merchant_id.

# Categories that are always Essentials (#7). Evidence: Housing, Utilities,
# Groceries and Health rows; Housing is one payment a month (CV ~0.03).
ESSENTIAL_CATEGORIES = frozenset({"groceries", "housing", "utilities", "health"})

# Categories split by MCC: only these MCCs are essential. A blank MCC counts
# as essential. Transportation: public transport 4111/4112/4131, fuel
# 5541/5542, parking 7523; taxis and ride-hailing (4121) are other spending.
# unconfirmed: ask S-Bank mentor about fuel/parking and blank-MCC rows.
ESSENTIAL_MCCS_BY_CATEGORY = {
    "transportation": frozenset({"", "4111", "4112", "4131", "5541", "5542", "7523"}),
}

# MCCs counted as Saver (#75) when they appear on a purchase. MCC 6211
# (security brokers) never occurs in the data; investments arrive as
# SAVER_TYPES instead. unconfirmed: ask S-Bank mentor.
INVESTMENT_MCCS = frozenset({"6211"})

# #58 possible travel goal: category == travel (docs/data_profile.md).
TRAVEL_CATEGORY = "travel"
TRAVEL_GOAL_MIN_EUR = 300.0
TRAVEL_LOOKBACK_MONTHS = 12

# Loan / credit categories and MCCs (#42, #76-#84). No real rows use these
# values (no loan, mortgage or credit-card category, type or MCC), so the loan
# alerts match nothing in the S-Bank data and the profile reports them
# unavailable (inferences/availability.py) unless the user adds loan details.
# Standard names / MCCs kept for other banks' data (#42).
# unconfirmed: ask S-Bank mentor.
LOAN_CATEGORIES = frozenset(
    {
        "loan",
        "loans",
        "loan_payment",
        "mortgage",
        "credit",
        "credit_card",
        "consumer_credit",
        "bnpl",
    }
)
LOAN_MCCS = frozenset({"6012", "6051", "6141"})

# Fees (#86), cash (#96) and gambling (#98). None of these occur in the data
# (no fee category, MCC 7322, 6011 or 7995): the rules match no real rows and
# are reported unavailable. Standard values kept for other banks' data.
# unconfirmed: ask S-Bank mentor.
FEE_CATEGORIES = frozenset({"fee", "fees", "bank_fee", "late_fee", "collection"})
FEE_MCCS = frozenset({"7322"})  # collection agencies
ATM_MCC = "6011"
GAMBLING_MCC = "7995"

# Coverage = salary_sweep / salary. Above this, most money lives at another
# bank: the profile is a "partial view" and is excluded from peer benchmarks.
PARTIAL_VIEW_COVERAGE = 0.5

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
# Calibration (docs/calibration.md): on the real data the robust z alone
# flagged 56% of customers every month (merchant amounts are wide). A charge
# must also be > 3 x the merchant median and > EUR 50 above it (doc test:
# 89 vs median 20 still flags).
UNUSUAL_MIN_MULT = 3.0
UNUSUAL_MIN_EXCESS_EUR = 50.0
DUPLICATE_WINDOW_MINUTES = 10
SPIKE_MULT = 1.5
SPIKE_MIN_DIFF_EUR = 20.0
# Calibration: only categories with spend in each of the previous 3 months
# (a first purchase in a rarely used category is not a spike): 82% -> 39%.
SPIKE_REQUIRE_FULL_HISTORY = True
OWN_TRANSFER_MATCH_DAYS = 1

# --- Forecasts (#17 to #23) -----------------------------------------------------

DISCRETIONARY_DAYS = 60  # #19 window for d and sigma
# #19/#20 daily spend statistic: "mean" (calibrated) or "median" (the doc).
FORECAST_DAILY_STAT = "mean"
BAND_Z = 1.28  # 80% band
DANGER_BALANCE_EUR = 50.0  # #20
UPCOMING_BILLS_DAYS = 30  # #21
NO_PAYDAY_HORIZON_DAYS = 30  # horizon when no payday was found
# #19 (FC-1): with fewer days than this left in the month, "end of month"
# means next month's last day, so the forecast always looks ahead.
MONTH_END_ROLLOVER_DAYS = 3
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

# --- Goals (#44 to #74) ---------------------------------------------------------

SAFETY_NET_ROUND_EUR = 50  # #45 target rounded up to EUR 50
WEALTH_GOAL_INCOME_SHARE = 0.10  # #48
GOAL_PRIORITY_WEIGHTS = {"high": 3, "medium": 2, "low": 1}  # #69
GOAL_SUCCESS_EASIER_BELOW = 0.5  # #55
MILESTONES = (25, 50, 75, 100)  # #73
GOAL_LEVEL = {"safety_net": 3}  # #71: other on-track goals count towards 4
FUNDING_CUT_PCT = 0.20  # #67
DETECT_SAVER_MIN_TRANSFERS = 2  # #56
DETECT_SAVER_CV_MAX = 0.3
DETECT_SAVER_DAYS = 90
DETECT_CATEGORY_DROP = 0.20  # #57
# #58 travel: TRAVEL_CATEGORY / TRAVEL_GOAL_MIN_EUR above (category == travel).
HOME_AGE_MIN, HOME_AGE_MAX = 25, 40  # #59
HOME_READINESS_MIN = 0.4
HOME_DEPOSIT_SHARE = 0.10
# #59 has no home-price data: the deposit target is only computed once the
# user enters a target price (no guessed price table).
DEBT_EXTRA_EUR = 50.0  # #60 "what if you paid EUR x more"
SEASONAL_POT_START_MONTHS = 3  # #61 pot from September for December
NEW_BILL_DAYS = 62  # #62 first seen in the last 2 months
NEW_BILL_INCOME_SHARE = 0.10
# #68 goal words -> categories / MCC ranges for a smart default amount.
GOAL_KEYWORDS = {
    "holiday": "travel",
    "trip": "travel",
    "travel": "travel",
    "vacation": "travel",
    "loma": "travel",
    "matka": "travel",
    "christmas": "christmas",
    "joulu": "christmas",
}

# --- Mortgage readiness (#34, #35) ------------------------------------------------

READINESS_FEATURES = (
    "buffer_months",
    "saver_share",
    "income_cv",
    "leaky_share",
    "essentials_share",
    "debt_share",
)
# Features where a higher value is better; the rest are better when lower.
READINESS_HIGHER_BETTER = frozenset({"buffer_months", "saver_share"})
READINESS_MIN_APPLICANTS = 30  # below this (or < 5 per class) use percentiles
READINESS_MIN_PER_CLASS = 5
READINESS_FEATURE_MONTHS = 6  # features from the 6 months before applying
READINESS_NOTE = "Guidance only, not a loan decision."

# --- Benchmarks (#36, #37) --------------------------------------------------------

AGE_BANDS = ((18, 24), (25, 29), (30, 39), (40, 54), (55, 200))
PEER_MIN_CUSTOMERS = 20
PEER_ABOVE = 1.2
PEER_BELOW = 0.8


# --- Demo customer picks (landing page) ----------------------------------------

# Income bands on the landing page, one typical customer each.
DEMO_LEVELS = 5
# Shorter histories give noisy monthly averages.
DEMO_MIN_HISTORY_MONTHS = 6
