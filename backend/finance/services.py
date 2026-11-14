"""Database access for the analytics layer.

The coach (and the REST views) should go through these helpers::

    from finance import analytics, services

    data = services.load_customer("CUST04457")   # raises Customer.DoesNotExist
    analytics.taxi_stats(data.txns, "last_3_months")
    analytics.what_if(data.txns, "Restaurants", 20, years=5)
    analytics.mortgage_timeline(data.application, data.events)
    services.overview(data)                      # full dashboard payload
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.forms.models import model_to_dict

from . import analytics
from .analytics import Tx
from .models import Customer, CustomerProfile, MortgageApplication, Transaction

TX_FIELDS = (
    "tx_date",
    "tx_timestamp",
    "category",
    "tx_amount_eur",
    "balance_after_eur",
    "transaction_type",
    "merchant_id",
    "mcc_code",
)


def row_to_tx(row):
    """Convert a ``TX_FIELDS`` tuple into an analytics :class:`Tx`."""
    d, ts, cat, amount, balance, kind, merchant, mcc = row
    return Tx(d, ts, cat, float(amount), float(balance), kind, merchant, mcc)


@dataclass
class CustomerData:
    """Everything analytics needs about one customer."""

    customer: Customer
    txns: list
    application: dict | None = None
    events: list = field(default_factory=list)


def load_transactions(customer_id):
    rows = (
        Transaction.objects.filter(customer_id=customer_id)
        .order_by("tx_date", "tx_timestamp")
        .values_list(*TX_FIELDS)
    )
    return [row_to_tx(r) for r in rows]


def load_mortgage(customer_id):
    """Return ``(application_dict, [event_dict])`` or ``(None, [])``."""
    app = MortgageApplication.objects.filter(customer_id=customer_id).first()
    if app is None:
        return None, []
    events = [model_to_dict(e) for e in app.events.order_by("timestamp")]
    data = model_to_dict(app)
    data["mortgage_customer_id"] = app.mortgage_customer_id
    return data, events


def load_customer(customer_id):
    """Load a customer with transactions and mortgage data in 3 queries."""
    customer = Customer.objects.select_related("profile").get(pk=customer_id)
    application, events = load_mortgage(customer_id)
    return CustomerData(
        customer=customer,
        txns=load_transactions(customer_id),
        application=application,
        events=events,
    )


def customer_summary(customer, profile=None):
    """The ``CustomerSummary`` shape from the API contract."""
    if profile is None:
        profile = getattr(customer, "profile", None)
    out = {
        "customer_id": customer.customer_id,
        "customer_age": customer.customer_age,
        "customer_postal_code": customer.customer_postal_code,
        "persona": None,
        "monthly_income": None,
        "monthly_spend": None,
        "savings_rate": None,
        "balance": None,
        "has_mortgage_application": False,
        "mortgage_decision": None,
    }
    if profile is not None:
        out.update(
            {
                "persona": {
                    "key": profile.persona_key,
                    "label": profile.persona_label,
                },
                "monthly_income": round(profile.monthly_income, 2),
                "monthly_spend": round(profile.monthly_spend, 2),
                "savings_rate": round(profile.savings_rate, 4),
                "balance": round(profile.balance, 2),
                "has_mortgage_application": profile.has_mortgage_application,
                "mortgage_decision": profile.mortgage_decision,
            }
        )
    return out


def overview(data):
    """Full ``/overview/`` payload for a :class:`CustomerData`."""
    body = analytics.overview(data.txns, data.application, data.events)
    summary = customer_summary(data.customer)
    if summary["persona"] is None:
        # Profiles not built yet: derive the summary on the fly.
        summary.update(
            {
                "persona": {
                    "key": body["persona"]["key"],
                    "label": body["persona"]["label"],
                },
                "monthly_income": body["income_monthly_avg"],
                "monthly_spend": body["spend_monthly_avg"],
                "savings_rate": body["savings_rate"],
                "balance": body["balance"],
                "has_mortgage_application": data.application is not None,
                "mortgage_decision": (
                    data.application["final_decision"] if data.application else None
                ),
            }
        )
    return {"customer": summary, **body}


def profile_for(customer_id, txns, application=None):
    """Build an unsaved :class:`CustomerProfile` from transactions."""
    values = analytics.profile_summary(txns)
    return CustomerProfile(
        customer_id=customer_id,
        has_mortgage_application=application is not None,
        mortgage_decision=application["final_decision"] if application else None,
        **values,
    )
