"""Who holds what at another bank in the synthetic data (MULTIBANK_PLAN.md §3).

Bank names are plain text only: no logos, colours or login pages.
"""

HERO = "CUST03369"  # A: hidden car loan (Will chose 2026-11-15)
SALARY_ELSEWHERE = "CUST03600"  # B: most income swept out of S-Bank
DUPLICATE_SUBS = "CUST00019"  # C: a music service at each of two banks
CREDIT_CARD = "CUST01819"  # D: credit card balance and repayment
SAVINGS_ELSEWHERE = "CUST00018"  # E: level 2, buffer 0.81 months

BANKS = {
    "NDEAFIHH": "Nordea",
    "OKOYFIHH": "OP",
    "DABAFIHH": "Danske Bank",
    "HELSFIHH": "Aktia",
    "AABAFI22": "Ålandsbanken",
}

# One line per scenario for the landing page's other-bank dropdown.
STORIES = {
    HERO: "Hidden car loan",
    SALARY_ELSEWHERE: "Salary swept to another bank",
    DUPLICATE_SUBS: "Two music services",
    CREDIT_CARD: "Credit card at another bank",
    SAVINGS_ELSEWHERE: "Savings at another bank",
}
