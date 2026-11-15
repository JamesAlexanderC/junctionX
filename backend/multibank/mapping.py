"""External (Berlin Group) data -> our model and category vocabulary, in one
place (MULTIBANK_PLAN.md §2, docs/vocabulary.md)."""

from __future__ import annotations

from datetime import date

ACCOUNT_TYPES = {"CACC": "current", "SVGS": "savings", "CARD": "credit", "LOAN": "loan"}

# proprietaryBankTransactionCode -> category (inferences/thresholds.py
# LOAN_CATEGORIES holds loan_payment and credit_card, so #4 / #76 see them).
CODE_CATEGORIES = {
    "LOAN": "loan_payment",
    "CARD_REPAYMENT": "credit_card",
    "TRANSFER": "transfer",
}
# MCC -> our purchase categories (as prepare() lower-cases them).
MCC_CATEGORIES = {
    "5411": "groceries",
    "5812": "restaurants",
    "5814": "restaurants",
    "5815": "entertainment",
    "4111": "transportation",
}
DEFAULT_PURCHASE = "lifestyle"
INFLOW_CATEGORY = "other income"

# category -> transaction_type for the merged ledger (inferences/multibank.py).
CATEGORY_TYPES = {
    "loan_payment": "loan_payment",
    "credit_card": "loan_payment",
    "transfer": "transfer",
    INFLOW_CATEGORY: "other_income",
}


def category(tx: dict) -> str:
    code = tx.get("proprietaryBankTransactionCode", "")
    if code in CODE_CATEGORIES:
        return CODE_CATEGORIES[code]
    if float(tx["transactionAmount"]["amount"]) > 0:
        return INFLOW_CATEGORY
    return MCC_CATEGORIES.get(tx.get("merchantCategoryCode") or "", DEFAULT_PURCHASE)


def transaction_type(category_name: str) -> str:
    return CATEGORY_TYPES.get(category_name, "purchase")


def account_fields(account: dict) -> dict:
    """Berlin Group account -> LinkedAccount fields."""
    return {
        "iban_masked": account["iban"],
        "name": account["name"],
        "type": ACCOUNT_TYPES.get(account["cashAccountType"], "current"),
        "currency": account.get("currency", "EUR"),
        "balance_eur": float(account["balance"]),
        "balance_date": date.fromisoformat(account["balanceDate"]),
    }


def transaction_fields(tx: dict) -> dict:
    """Berlin Group transaction -> ExternalTransaction fields."""
    party = tx.get("creditorAccount") or tx.get("debtorAccount") or {}
    return {
        "booking_date": date.fromisoformat(tx["bookingDate"]),
        "amount_eur": float(tx["transactionAmount"]["amount"]),
        "creditor_name": tx.get("creditorName", ""),
        "debtor_name": tx.get("debtorName", ""),
        "counterparty_iban_masked": party.get("iban", ""),
        "remittance_info": tx.get("remittanceInformationUnstructured", ""),
        "mcc": tx.get("merchantCategoryCode"),
        "category": category(tx),
    }
