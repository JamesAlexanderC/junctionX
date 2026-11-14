"""Every profile item Gemini can read with get_inference (P2.2).

One entry per readable path in the build_profile output. ``gate`` names the
inferences/availability.py item that decides whether the customer's data
supports it; entries without a gate are unavailable when the value is empty
and then return ``missing_reason``. To expose a new inference, add one entry.

Inference numbers come from the gate's availability item when there is one,
otherwise from ``inferences`` here (context.md numbering).
"""

from dataclasses import dataclass

MISSING = object()


@dataclass(frozen=True)
class Chart:
    """How to turn a value into chart card data: a list of {label, value}.

    For a list value, ``label_key`` / ``value_key`` pick the fields of each
    row; for a dict value they are None and keys become labels.
    """

    kind: str  # "bar" or "line", as in the chart card
    label_key: str | None = None
    value_key: str | None = None
    title: str = ""  # chart card title (get_chart)
    unit: str | None = None  # "EUR", "%" or None for plain numbers


@dataclass(frozen=True)
class Entry:
    path: str
    about: str
    gate: str | None = None
    inferences: tuple[int, ...] = ()
    missing_reason: str = "The data does not support this."
    chart: Chart | None = None
    keep: str = "first"  # which end of a long list the summary keeps


# Availability items deliberately not exposed through get_inference.
NOT_EXPOSED = {
    "alerts": "Read with get_alerts / explain_alert (priority and snoozes).",
    "whatif.goal_date": "Computed per goal by simulate_cut and list_goals.",
}

_ENTRIES = [
    # --- balance and income (#1 to #6, #17, #41) ---
    Entry("balance", "Current account balance in EUR.", gate="balance"),
    Entry(
        "income.payday",
        "Detected payday: amount, last and next date, days to go.",
        gate="income.payday",
        keep="last",
    ),
    Entry(
        "income.monthly_income",
        "Average monthly income over the last 3 full months.",
        gate="income.monthly_income",
    ),
    Entry(
        "income.monthly_income_series",
        "Income for each month.",
        gate="income.monthly_income",
        chart=Chart("bar", "month", "value", "Income by month", "EUR"),
        keep="last",
    ),
    Entry(
        "income.stability",
        "How steady income is month to month (variation and a label).",
        gate="income.stability",
    ),
    Entry(
        "income.retained_income",
        "Monthly income that stays in this bank after transfers out.",
        gate="income.monthly_income",
    ),
    Entry(
        "income.coverage",
        "Share of salary swept to other accounts (0 to 1).",
        gate="income.monthly_income",
    ),
    Entry(
        "income.partial_view",
        "True when most money leaves for another bank, so this view is partial.",
        inferences=(41,),
    ),
    Entry(
        "income.bills",
        "Regular bills: amount, how steady, last and next date.",
        gate="income.bills",
    ),
    Entry(
        "income.subscriptions",
        "Subscriptions found in the transactions.",
        gate="income.subscriptions",
    ),
    Entry(
        "income.possibly_unused",
        "Subscriptions that show signs of being unused.",
        gate="income.possibly_unused",
    ),
    # --- baskets (#7 to #10, #75) ---
    Entry(
        "baskets.totals",
        "This month's spending per basket in EUR.",
        gate="baskets",
        chart=Chart("bar", title="Spending by basket this month", unit="EUR"),
    ),
    Entry(
        "baskets.shares",
        "This month's spending per basket as a percent of the total.",
        gate="baskets",
        chart=Chart("bar", title="Share of spending by basket", unit="%"),
    ),
    Entry(
        "baskets.trend",
        "Change of each basket against earlier months, in percent.",
        gate="baskets.trend",
    ),
    Entry(
        "baskets.history",
        "Basket totals for each recent month.",
        gate="baskets",
        keep="last",
    ),
    Entry(
        "baskets.monthly_saving",
        "Average monthly transfers to savings and investments.",
        gate="baskets.saver",
    ),
    Entry(
        "baskets.monthly_essentials",
        "Average monthly essential spending.",
        gate="baskets",
    ),
    Entry(
        "baskets.leaky_categories",
        "Categories with small everyday leaky spending.",
        gate="baskets",
    ),
    # --- habits (#11 to #16) ---
    Entry("habits.weekend", "Weekend share of spending.", gate="habits.weekend"),
    Entry("habits.night", "Share of spending 22:00 to 05:00.", gate="habits.night"),
    Entry(
        "habits.impulse",
        "Bursts of small purchases close together, per month.",
        gate="habits.impulse",
    ),
    Entry(
        "habits.payday_splurge",
        "Non-essential spending just after payday vs the rest of the month.",
        gate="habits.payday_splurge",
    ),
    Entry(
        "habits.loyalty",
        "How concentrated spending is across merchants.",
        gate="habits.loyalty",
    ),
    Entry(
        "habits.spender_type",
        "Spender type label and the score of each trait (0 to 1).",
        gate="habits.spender_type",
    ),
    # --- forecast (#17 to #23) ---
    Entry(
        "forecast.safe_to_spend_week",
        "Safe to spend this week.",
        gate="forecast.safe_to_spend_week",
    ),
    Entry(
        "forecast.safe_to_save_today",
        "Safe to move to savings today.",
        gate="forecast.safe_to_save_today",
    ),
    Entry(
        "forecast.buffer",
        "Cushion kept aside for surprises.",
        gate="forecast.safe_to_spend_week",
    ),
    Entry(
        "forecast.end_of_month",
        "Expected balance range at the end of the month.",
        gate="forecast.end_of_month",
    ),
    Entry(
        "forecast.daily_path",
        "Expected balance (with low and high) for each day until payday.",
        gate="forecast.end_of_month",
        chart=Chart("line", "date", "expected", "Expected balance until payday", "EUR"),
    ),
    Entry(
        "forecast.danger_days",
        "Days the balance may drop below the buffer.",
        gate="forecast.danger_days",
    ),
    Entry(
        "forecast.upcoming_bills",
        "Bills due in the next 30 days.",
        gate="forecast.upcoming_bills",
    ),
    Entry(
        "forecast.surprise_fund_monthly",
        "Monthly amount to set aside for irregular costs.",
        gate="forecast.surprise_fund",
    ),
    Entry(
        "forecast.seasonal",
        "Next month's expected seasonal spending vs usual.",
        gate="forecast.seasonal",
    ),
    Entry(
        "forecast.daily_discretionary",
        "Typical daily spending outside bills.",
        gate="forecast.end_of_month",
    ),
    # --- what-if (#24 to #27) ---
    Entry(
        "whatif.category_means",
        "Average monthly spend per category (base for cuts).",
        gate="whatif.category_cut",
        chart=Chart("bar", title="Average monthly spend by category", unit="EUR"),
    ),
    Entry(
        "whatif.subscription_savings",
        "What dropping each subscription would save.",
        gate="whatif.subscription_savings",
        chart=Chart(
            "bar", "name", "yearly_saving", "Yearly saving per subscription", "EUR"
        ),
    ),
    Entry(
        "whatif.habit_translation",
        "Leaky habits translated into yearly euros.",
        gate="whatif.habit_translation",
    ),
    # --- levels (#28 to #33) ---
    Entry("levels", "Level, progress, ladder and safety net months.", gate="levels"),
    Entry(
        "levels.easiest_next_step",
        "Smallest cut that reaches the next level.",
        gate="levels.easiest_next_step",
    ),
    # --- goals (#44 to #74) ---
    Entry(
        "goals.active",
        "Active goals with progress, on track and monthly needed.",
        gate="goals.active",
    ),
    Entry(
        "goals.completed",
        "Goals already reached.",
        missing_reason="No goals completed yet.",
    ),
    Entry(
        "goals.recommended",
        "The goal recommended for the current level.",
        gate="goals.recommended",
    ),
    Entry(
        "goals.detected",
        "Saving patterns found in the data, as suggestions.",
        gate="goals.detected",
    ),
    Entry(
        "goals.clash",
        "Whether all goals together fit what is safe to save each month.",
        inferences=(70,),
        missing_reason="No goals to compare.",
    ),
    Entry(
        "goals.funding_cuts",
        "Category cuts that would fund the recommended goal.",
        inferences=(67,),
        missing_reason="No cuts needed or no leaky spending to cut.",
    ),
    Entry(
        "goals.success_score",
        "Share of past goals completed rather than abandoned.",
        inferences=(55,),
        missing_reason="No finished or abandoned goals yet.",
    ),
    Entry(
        "goals.priority_split",
        "How safe-to-save splits across goals by priority.",
        inferences=(69,),
        missing_reason="Needs active goals to split saving across.",
    ),
    Entry(
        "goals.suggestion_weights",
        "How much each goal type is liked, from thumbs up and down.",
        inferences=(54, 74),
    ),
    # --- mortgage (#34, #35, #76, #77, #82) ---
    Entry(
        "mortgage.readiness",
        "Mortgage readiness score and the gaps to close.",
        gate="mortgage.readiness",
    ),
    Entry(
        "mortgage.features",
        "The inputs to the readiness score.",
        gate="mortgage.readiness",
    ),
    Entry(
        "mortgage.monthly_loan_payments",
        "Loan payments found in the transactions, per month.",
        gate="mortgage.loan_burden",
    ),
    Entry(
        "mortgage.dsti",
        "Share of net income going to loan payments.",
        inferences=(76,),
        missing_reason="Needs loan payments or loan details.",
    ),
    Entry(
        "mortgage.stress_test",
        "Loan payment at a 6% stress rate and whether it fits.",
        gate="mortgage.stress_test",
    ),
    Entry(
        "mortgage.loan_details",
        "Loan balance, rate and years left that the user entered.",
        inferences=(77, 82),
        missing_reason="No loan details entered yet. Ask the user for them.",
    ),
    # --- benchmarks (#36, #37) and multibank (#41 to #43) ---
    Entry(
        "benchmarks.age",
        "Spending per category vs the user's age group.",
        gate="benchmarks.age",
    ),
    Entry(
        "benchmarks.area",
        "Spending per category vs the user's postcode area.",
        gate="benchmarks.area",
    ),
    Entry(
        "multibank",
        "Accounts at other banks, true income, hidden loans, duplicates.",
        gate="multibank",
    ),
]

CATALOGUE = {e.path: e for e in _ENTRIES}


def get_path(profile: dict, path: str):
    """The value at a dotted path, or MISSING when a key is absent."""
    node = profile
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return MISSING
        node = node[key]
    return node


def section(item: str) -> str:
    return item.split(".", 1)[0]
