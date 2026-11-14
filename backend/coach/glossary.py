"""Short explainers for money concepts, sent as ``concept`` chat events."""

GLOSSARY = {
    "safe_to_spend": {
        "title": "Safe to spend",
        "text": (
            "Your balance minus the bills due before your next payday and a "
            "small safety reserve, spread over the days until salary arrives. "
            "Spend within it and the bills are always covered."
        ),
    },
    "savings_rate": {
        "title": "Savings rate",
        "text": (
            "The share of your income you keep: (income - spending) / income. "
            "Around 10% is a solid start; 20% or more builds wealth fast."
        ),
    },
    "three_baskets": {
        "title": "The three baskets",
        "text": (
            "Must-pay bills (rent, utilities, groceries, subscriptions), "
            "surprise essentials (health, tech, travel) and everyday leakage "
            "(eating out, fun, shopping, taxis). Leakage is where cuts are "
            "easiest."
        ),
    },
    "compound_interest": {
        "title": "Compound interest",
        "text": (
            "Interest that earns interest. Savings growing at 3% a year earn a "
            "little on top of every euro you add, and the effect snowballs "
            "the longer you leave it."
        ),
    },
    "ltv": {
        "title": "Loan-to-value (LTV)",
        "text": (
            "The loan as a share of the home's price. In Finland first-time "
            "buyers can borrow up to 90%, so you need at least a 10% deposit."
        ),
    },
    "stress_test": {
        "title": "Stress test",
        "text": (
            "Banks check you could still afford the loan if interest rose to "
            "about 6%. Payments should stay under roughly 35% of your net "
            "income even then."
        ),
    },
    "emergency_fund": {
        "title": "Emergency fund",
        "text": (
            "Cash set aside for surprises such as a broken laptop or a "
            "dentist bill. Aim for about three months of spending, kept "
            "somewhere easy to reach."
        ),
    },
}

# Phrases that identify a glossary entry in a user question.
TERMS = {
    "safe_to_spend": ("safe to spend", "safe-to-spend"),
    "savings_rate": ("savings rate", "saving rate"),
    "three_baskets": ("three baskets", "3 baskets", "baskets", "leakage"),
    "compound_interest": ("compound interest", "compounding", "interest"),
    "ltv": ("loan-to-value", "loan to value", "ltv"),
    "stress_test": ("stress test", "stress-test"),
    "emergency_fund": (
        "emergency fund",
        "rainy day fund",
        "buffer",
        "emergency savings",
    ),
}


def concept(key):
    """Return ``{"title","text"}`` for a glossary key (or None)."""
    entry = GLOSSARY.get(key)
    return dict(entry) if entry else None
