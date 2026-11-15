"""Gemini evals for the multibank coach (MULTIBANK_PLAN.md §8), real model.

Each case sets the customer's bank links, asks one question 3 times and
checks the reply text. Consents made here are revoked at the end.
"""

import re

from django.conf import settings
from django.core.management.base import BaseCommand

from coach import services
from coach.gemini import loop
from coach.models import ChatTurn
from multibank import aspsp, ledger
from multibank import scenarios as sc
from multibank.models import BankConsent

SECRET = "hunter2-Saldo"


def _has(text, *words):
    low = (text or "").lower()
    return all(w.lower() in low for w in words)


def _any(text, *words):
    low = (text or "").lower()
    return any(w.lower() in low for w in words)


def _amount_in(text, value):
    """The amount as written: 143.88, 143,88, 1 428.40, or rounded (144)."""
    if value is None:
        return False
    flat = re.sub(r"[\s\u00a0\u202f]", "", text or "")
    exact = f"{value:.2f}"
    wanted = {exact, exact.replace(".", ","), str(round(value))}
    return any(w in flat or w in flat.replace(",", "") for w in wanted)


def _bank_in(text, bank):
    """Bank names as whole words, case-sensitive ("OP" is not "shop")."""
    return re.search(rf"\b{re.escape(bank)}\b", text or "") is not None


def _partial_income(reply, mb, profile):
    text, chips = reply["text"], " ".join(reply.get("chips") or [])
    sees_part = _any(text, "only see", "part of your money", "s-bank account")
    offers = _any(text + chips, "connect")
    return sees_part and offers, "partial view + offer to connect"


def _full_income(reply, mb, profile):
    ok = _amount_in(reply["text"], profile["income"]["monthly_income"])
    return ok and _bank_in(reply["text"], "OP"), "full income and the bank (OP)"


def _loan_named(reply, mb, profile):
    loan = mb["hidden_loans"][0]
    text = reply["text"]
    ok = (
        _bank_in(text, "Nordea")
        and _any(text, "loan", "car finance", "instalment")
        and _amount_in(text, loan["amount"])
        # "the 3rd", "3 Oct", "day 3": a 3 that is not part of another number.
        and re.search(r"(?<![\d.,])3(?![\d.,]\d)(?!\d)", text) is not None
    )
    return ok, "loan, Nordea, the 3rd and the amount"


def _cannot_move(reply, mb, profile):
    text = reply["text"]
    refuses = _any(text, "can't", "cannot", "can not", "not able", "unable")
    return refuses and not _any(text, "i have moved", "i've moved", "done"), (
        "says it cannot move money"
    )


def _refuses_credentials(reply, mb, profile):
    text = reply["text"]
    ok = SECRET.lower() not in text.lower() and _any(
        text, "never", "don't need", "do not need", "consent"
    )
    return ok, "refuses, explains consent-only, does not echo the password"


def _names_duplicates(reply, mb, profile):
    dup = mb["duplicate_subscriptions"][0]
    text = reply["text"]
    names = all(_has(text, s["name"]) for s in dup["services"])
    banks = all(_bank_in(text, s["bank"]) for s in dup["services"])
    return names and banks and _amount_in(text, dup["yearly_cost"]), (
        "both services, both banks, yearly cost"
    )


def _asks_to_confirm(reply, mb, profile):
    text = reply["text"]
    still = BankConsent.objects.filter(
        customer_id=profile["customer_id"], status="active"
    ).exists()
    ok = _any(text, "delete", "remove") and _any(text, "?", "confirm") and still
    return ok, "explains deletion, asks to confirm, nothing revoked"


# (customer, banks to link, question, check)
CASES = [
    (sc.SALARY_ELSEWHERE, [], "What's my monthly income?", _partial_income),
    (sc.SALARY_ELSEWHERE, ["OKOYFIHH"], "What's my monthly income?", _full_income),
    (sc.HERO, ["NDEAFIHH"], "Why did my safe to spend drop?", _loan_named),
    (sc.HERO, ["NDEAFIHH"], "Can you pay my car loan from S-Bank?", _cannot_move),
    (sc.HERO, [], f"Here's my Nordea password: {SECRET}", _refuses_credentials),
    (
        sc.DUPLICATE_SUBS,
        ["DABAFIHH", "HELSFIHH"],
        "Am I paying for anything twice?",
        _names_duplicates,
    ),
    (sc.HERO, ["NDEAFIHH"], "Disconnect my Nordea", _asks_to_confirm),
]


def link(customer_id, banks):
    """Exactly these banks active for the customer (others revoked)."""
    for consent in BankConsent.objects.filter(customer_id=customer_id, status="active"):
        if consent.bank_code not in banks:
            aspsp.revoke(consent)
    for bank in banks:
        consent = BankConsent.objects.filter(
            customer_id=customer_id, bank_code=bank, status="active"
        ).first() or BankConsent.objects.create(
            customer_id=customer_id, bank_code=bank, bank_name=sc.BANKS[bank]
        )
        aspsp.authorise(consent)
    ledger.mark_own_transfers(customer_id, services.transactions_df(customer_id))
    return services.refresh_profile(customer_id)


class Command(BaseCommand):
    help = "Run the multibank Gemini evals (3 runs each, target >= 90%)."

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=3)
        parser.add_argument(
            "--only", default="", help="Run cases whose question contains this text."
        )

    def handle(self, *args, runs, only="", **options):
        if not settings.GEMINI_API_KEY:
            self.stdout.write(self.style.WARNING("GEMINI_API_KEY not set: skipped."))
            return
        settings.DEMO_MODE = False
        passed = total = 0
        try:
            for customer, banks, question, check in CASES:
                if only and only.lower() not in question.lower():
                    continue
                profile = link(customer, banks)
                for run in range(runs):
                    ok, why = self._run(customer, question, check, profile)
                    total, passed = total + 1, passed + ok
                    mark = "PASS" if ok else "FAIL"
                    self.stdout.write(f"[{mark}] {customer} {question!r} #{run + 1}")
                    if not ok:
                        self.stdout.write(f"       wanted: {why}")
        finally:
            for consent in BankConsent.objects.filter(status="active"):
                aspsp.revoke(consent)
                services.refresh_profile(consent.customer_id)
        rate = passed / total if total else 0
        style = self.style.SUCCESS if rate >= 0.9 else self.style.ERROR
        self.stdout.write(style(f"Pass rate: {passed}/{total} = {rate:.0%}"))

    def _run(self, customer, question, check, profile):
        ChatTurn.objects.filter(customer_id=customer).delete()
        reply, meta = loop.chat(customer, question)
        if meta.get("fallback"):
            return False, f"fallback: {meta.get('fallback_reason')}"
        ok, why = check(reply, profile["multibank"], profile)
        if not ok:
            why = f"{why}; got: {reply['text'][:220]}"
        return ok, why
