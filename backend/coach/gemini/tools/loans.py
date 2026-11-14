"""save_loan_details: the loan balance, rate and years the user tells the
coach (P2.8, used by #77 and #82). Same rules as POST /api/loans/."""

from ... import services
from ...models import LoanDetails
from ...serializers import LoanSerializer
from .context import ToolError, form_errors, is_confirmed, propose

MORTGAGE_KEYS = ("loan_details", "stress_test", "dsti")


def save_loan_details(ctx, balance, interest_rate, years_left):
    form = LoanSerializer(
        data={
            "customer_id": ctx.customer_id,
            "balance": balance,
            "interest_rate": interest_rate,
            "years_left": years_left,
        }
    )
    if not form.is_valid():
        raise ToolError(form_errors(form.errors))
    proposal = {
        "balance": balance,
        "interest_rate": interest_rate,
        "years_left": years_left,
    }
    if not is_confirmed(ctx, "save_loan_details", proposal):
        return propose(
            ctx,
            "save_loan_details",
            proposal,
            "Ask the user to confirm these loan details. Nothing was saved.",
        )
    LoanDetails.objects.create(**form.validated_data)
    profile = services.refresh_profile(ctx.customer_id)
    ctx.reload()
    mortgage = profile.get("mortgage", {})
    return {
        "status": "saved",
        "mortgage": {key: mortgage.get(key) for key in MORTGAGE_KEYS},
    }
