"""Simulated PSD2 multi-bank tools (MULTIBANK_PLAN.md MB-7). Read-only:
nothing here moves money or changes a consent.

Numbers come from profile["multibank"] (inferences/multibank.py); names are
the readable merchant names, never raw IDs.
"""

from .context import unavailable

SIMULATED_NOTE = (
    "Accounts at other banks are simulated data from a PSD2-style consent "
    "(read-only). Say so when you use these numbers."
)
NOT_CONNECTED = (
    "No other bank is connected yet. The user can connect one from the "
    "Overview (consent screen, no password)."
)
DELTA_ITEMS = ("safe_to_spend", "buffer_months", "dsti", "level", "monthly_income")


def _mb(ctx):
    return ctx.profile.get("multibank") or {}


def _connected(ctx):
    return bool(_mb(ctx).get("connected_banks"))


def _account_rows(ctx):
    rows = [
        {
            "bank": "S-Bank",
            "name": "S-Bank account",
            "type": "current",
            "balance": ctx.profile.get("balance"),
            "simulated": False,
        }
    ]
    for a in _mb(ctx).get("linked_accounts") or []:
        rows.append(
            {
                "bank": a["bank"],
                "name": a["name"],
                "type": a["type"],
                "balance": a.get("balance_eur"),
                "iban_masked": a.get("iban_masked"),
                "simulated": True,
            }
        )
    return rows


def _simulated(out, ctx):
    if _connected(ctx):
        out["simulated"] = True
        out["note"] = SIMULATED_NOTE
    else:
        out["simulated"] = False
    return out


def get_accounts_overview(ctx):
    """Banks, account types, balances, coverage (#112) and consent expiry."""
    mb, rows = _mb(ctx), _account_rows(ctx)
    coverage = mb.get("coverage", "sbank_only")
    out = {
        "connected_banks": mb.get("connected_banks", []),
        "coverage": coverage,
        "accounts": rows,
        "consent_expiries": mb.get("consents", []),
        "total_liquid_balance": mb.get("total_liquid_balance"),
        "card": {"type": "accounts", "accounts": rows, "coverage": coverage},
    }
    return _simulated(out, ctx)


def _loan(loan):
    keys = ("name", "bank", "amount", "day_of_month", "next_date", "evidence")
    return {k: loan.get(k) for k in keys}


def _duplicate(dup):
    keys = ("name", "services", "monthly_total", "yearly_cost")
    return {k: dup.get(k) for k in keys}


def get_multibank_insights(ctx):
    """#41, #42, #43, #111 and #113 with evidence rows."""
    mb = _mb(ctx)
    if not _connected(ctx):
        return unavailable(NOT_CONNECTED, coverage=mb.get("coverage", "sbank_only"))
    levels = ctx.profile.get("levels") or {}
    income = ctx.profile.get("income") or {}
    out = {
        "connected_banks": mb["connected_banks"],
        "coverage": mb.get("coverage"),
        "own_transfers_found": mb.get("own_transfers_found", 0),
        "hidden_loans": [_loan(x) for x in mb.get("hidden_loans") or []],
        "duplicate_subscriptions": [
            _duplicate(x) for x in mb.get("duplicate_subscriptions") or []
        ],
        "real_income": {
            "monthly_income": income.get("monthly_income"),
            "sbank_only_monthly_income": (mb.get("sbank_only") or {}).get(
                "monthly_income"
            ),
        },
        "total_buffer": {
            "buffer_months": levels.get("buffer_months"),
            "external_liquid": mb.get("external_liquid"),
            "total_liquid_balance": mb.get("total_liquid_balance"),
        },
    }
    return _simulated(out, ctx)


def compare_linked_view(ctx):
    """Before (S-Bank only) and after (all connected banks), as a card."""
    delta = _mb(ctx).get("delta")
    if not _connected(ctx) or not delta:
        return unavailable(NOT_CONNECTED + " There is nothing to compare yet.")
    side = {
        when: {k: delta[k][when] for k in DELTA_ITEMS if k in delta}
        for when in ("before", "after")
    }
    changed = [
        k for k in DELTA_ITEMS if k in delta and side["before"][k] != side["after"][k]
    ]
    out = {
        "before": side["before"],
        "after": side["after"],
        "changed": changed,
        "card": {"type": "before_after", **side},
    }
    return _simulated(out, ctx)
