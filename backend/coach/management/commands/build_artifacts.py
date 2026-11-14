"""Compute the dataset-wide artifacts once, after load_data.

- peer table for #36 / #37 (median monthly category spend per age band and
  postcode area, groups of 20+ customers are used by the inference)
- mortgage readiness model for #34 / #35, fitted on the real applicants in
  the mortgage files (application date = first application_created event)
"""

import pickle
import time

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min

from coach import services
from coach.models import Customer, MortgageEvent, MortgageOutcome


class Command(BaseCommand):
    help = "Build the peer table and mortgage model from the loaded data."

    def handle(self, *args, **opts):
        from inferences import benchmarks, mortgage

        started = time.monotonic()
        all_df = services.all_transactions_df()
        if not len(all_df):
            raise CommandError("No transactions loaded. Run load_data first.")
        today = services.as_of_date()
        self.stdout.write(f"Read {len(all_df)} transactions; as of {today}")

        meta = [
            {
                "customer_id": c["customer_id"],
                "customer_age": c["age"],
                "customer_postal_code": c["postal_code"],
            }
            for c in Customer.objects.values("customer_id", "age", "postal_code")
        ]
        table = benchmarks.compute_peer_table(all_df, meta, today)
        services.save_artifact(services.PEER_TABLE_KEY, data=table)
        self.stdout.write(
            f"Peer table: {len(table['age'])} age bands, {len(table['area'])} areas "
            f"({time.monotonic() - started:.0f}s)"
        )

        applied = dict(
            MortgageEvent.objects.filter(event_type="application_created")
            .values_list("mortgage_customer_id")
            .annotate(first=Min("timestamp"))
        )
        applicants = [
            (o.customer_id, applied[o.mortgage_customer_id].date(), o.approved)
            for o in MortgageOutcome.objects.exclude(customer=None)
            if applied.get(o.mortgage_customer_id)
        ]
        if not applicants:
            self.stderr.write("No mortgage applicants with transactions: no model.")
            return
        ids = {a[0] for a in applicants}
        sub = all_df[all_df["customer_id"].isin(ids)]
        sub = sub.assign(customer_id=sub["customer_id"].astype(str))
        features = mortgage.applicant_features(sub, applicants)
        model = mortgage.fit_readiness_model(features, features["approved"])
        summary = {k: model.get(k) for k in ("method", "auc", "n_applicants", "coef")}
        services.save_artifact(
            services.MORTGAGE_MODEL_KEY, data=summary, blob=pickle.dumps(model)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Mortgage model: {summary['method']}, AUC {summary['auc']}, "
                f"{summary['n_applicants']} applicants "
                f"({time.monotonic() - started:.0f}s total)"
            )
        )
        services.reset_as_of_cache()
