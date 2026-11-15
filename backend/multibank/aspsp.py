"""Mock ASPSP (the other bank's AIS API) and consent actions.

Authorising is a single "Allow" in our own UI: no credentials exist anywhere.
Data comes only from the synthetic file; nothing is invented on the fly.
"""

from __future__ import annotations

from django.db import transaction as db_transaction

from . import data, mapping
from .models import BankConsent, ExternalTransaction, LinkedAccount

NO_ACCOUNTS = "No accounts found at this bank"


def berlin_accounts(consent: BankConsent) -> list[dict]:
    return data.bank_accounts(consent.customer_id, consent.bank_code)


def account_view(account: dict) -> dict:
    keys = ("resourceId", "iban", "name", "cashAccountType", "currency")
    return {k: account[k] for k in keys}


def balances_view(account: dict) -> dict:
    return {
        "account": {"iban": account["iban"]},
        "balances": [
            {
                "balanceAmount": {
                    "amount": f"{account['balance']:.2f}",
                    "currency": account["currency"],
                },
                "balanceType": "closingBooked",
                "referenceDate": account["balanceDate"],
            }
        ],
    }


def transactions_view(account: dict) -> dict:
    return {
        "account": {"iban": account["iban"]},
        "transactions": {"booked": account["transactions"], "pending": []},
    }


@db_transaction.atomic
def authorise(consent: BankConsent) -> int:
    """Activate the consent and copy the bank's accounts in. Returns how many
    accounts were found (0 is fine: nothing is made up)."""
    consent.status = "active"
    consent.save(update_fields=["status"])
    consent.delete_linked_data()
    accounts = berlin_accounts(consent)
    for account in accounts:
        linked = LinkedAccount.objects.create(
            consent=consent, **mapping.account_fields(account)
        )
        ExternalTransaction.objects.bulk_create(
            ExternalTransaction(linked_account=linked, **mapping.transaction_fields(t))
            for t in account["transactions"]
        )
    return len(accounts)


@db_transaction.atomic
def revoke(consent: BankConsent) -> None:
    consent.delete_linked_data()
    consent.status = "revoked"
    consent.save(update_fields=["status"])
