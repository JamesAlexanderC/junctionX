"""P1.2: rank customers for demo stories and suggest 5.

Stories: payday splurger (#14), secret saver (#75), nearly mortgage-ready
(#30 buffer 1-3 months, applied for a mortgage), multi-bank (#41-#43).
The scan is chunked and keeps only per-customer daily totals.

Coverage = salary_sweep / salary (P1.1). Story picks prefer coverage below
0.3 (we see most of their money); the multi-bank pick is the customer with the
highest coverage, whose money mostly sits at another bank.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from coach.management import csvdata

FULL_VIEW_MAX_COVERAGE = 0.3
SHORTLIST_ROWS = 10
STORIES = (
    ("payday splurger", "payday_ratio"),
    ("secret saver", "saver_share"),
    ("nearly mortgage-ready", "mortgage_score"),
)


class Command(BaseCommand):
    help = "Suggest demo customers with clear stories."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir")
        parser.add_argument("--top", type=int, default=5)

    def handle(self, *args, **opts):
        import pandas as pd

        data_dir = Path(opts["data_dir"]) if opts["data_dir"] else None
        from inferences import thresholds as th

        daily_parts, accounts = [], {}
        for chunk in csvdata.iter_transactions(data_dir):
            amt = chunk["tx_amount_eur"]
            ttype = chunk["transaction_type"].str.lower()
            is_own = ttype.isin(th.OWN_TRANSFER_TYPES)
            chunk = chunk.assign(
                inflow=amt.where((amt > 0) & ~is_own, 0.0),
                spend=(-amt).where((amt < 0) & ~is_own, 0.0),
                saved=(-amt).where(ttype.isin(th.SAVER_TYPES), 0.0),
                salary=amt.where(ttype.isin(th.SALARY_TYPES), 0.0),
                sweep=(-amt).where(ttype.isin(th.NEUTRAL_TRANSFER_TYPES), 0.0),
                day=chunk["tx_date"].dt.normalize(),
            )
            daily_parts.append(
                chunk.groupby(["customer_id", "day"]).agg(
                    inflow=("inflow", "sum"),
                    spend=("spend", "sum"),
                    saved=("saved", "sum"),
                    salary=("salary", "sum"),
                    sweep=("sweep", "sum"),
                    balance=("balance_after_eur", "last"),
                )
            )
            for cid, acc in chunk[["customer_id", "bank_account_id"]].values:
                accounts.setdefault(cid, set()).add(acc)
        daily = (
            pd.concat(daily_parts)
            .groupby(level=[0, 1])
            .agg(
                {
                    "inflow": "sum",
                    "spend": "sum",
                    "saved": "sum",
                    "salary": "sum",
                    "sweep": "sum",
                    "balance": "last",
                }
            )
        )
        try:
            link = csvdata.read_small(csvdata.MTG_LINK_FILE, data_dir)
            applicants = set(link["customer_id"].astype(str))
        except Exception:  # noqa: BLE001 - optional file
            applicants = set()

        rows = []
        for cid, d in daily.groupby(level=0):
            d = d.droplevel(0)
            rows.append(self._score(cid, d, accounts.get(cid, set()), applicants))
        scores = pd.DataFrame(rows).set_index("customer_id")
        full = scores[scores["coverage"] < FULL_VIEW_MAX_COVERAGE]
        self.stdout.write(
            f"{len(full)} of {len(scores)} customers have coverage < "
            f"{FULL_VIEW_MAX_COVERAGE}"
        )
        picks = []
        shortlists = [(s, c, full) for s, c in STORIES]
        shortlists.append(("multi-bank (high sweep)", "coverage", scores))
        for story, col, pool in shortlists:
            top = pool.sort_values(col, ascending=False).head(SHORTLIST_ROWS)
            self.stdout.write(f"\n== {story} ({col}) ==")
            self.stdout.write(top.round(3).to_string())
            for cid in top.index:
                if cid not in [p[0] for p in picks]:
                    picks.append((cid, story))
                    break
        for cid in full.sort_values("payday_ratio", ascending=False).index:
            if len(picks) >= opts["top"]:
                break
            if cid not in [p[0] for p in picks]:
                picks.append((cid, "extra"))
        self.stdout.write("\nSuggested DEMO_CUSTOMERS:")
        for cid, story in picks:
            self.stdout.write(f"  {cid}  ({story})")
        self.stdout.write("DEMO_CUSTOMERS=" + ",".join(p[0] for p in picks))

    @staticmethod
    def _score(cid, d, accs, applicants):
        months = d.groupby(d.index.to_period("M"))
        income = months["inflow"].sum()
        spend_m = months["spend"].sum()
        # Payday = most common day of the month with the biggest inflow (#1).
        pay_days = d.loc[months["inflow"].idxmax().values].index.day
        ratio = 1.0
        if len(pay_days):
            pay = int(pay_days.to_series().mode().iloc[0])
            offset = (d.index.day - pay) % 31
            near = d["spend"][offset <= 3].mean()
            rest = d["spend"][offset > 3].mean()
            ratio = float(near / rest) if rest else 1.0
        saver = float(d["saved"].sum() / income.sum()) if income.sum() else 0.0
        salary = float(d["salary"].sum())
        coverage = float(d["sweep"].sum() / salary) if salary else 0.0
        last30 = d["balance"].iloc[-30:].min()
        mean_spend = float(spend_m.mean()) if len(spend_m) else 0.0
        buffer = float(last30 / mean_spend) if mean_spend else 0.0
        mortgage = (1.0 if cid in applicants else 0.0) + (
            1.0 if 1 <= buffer <= 3 else 0
        )
        return {
            "customer_id": cid,
            "payday_ratio": ratio,
            "saver_share": saver,
            "buffer_months": buffer,
            "mortgage_score": mortgage + min(saver, 0.3),
            "accounts": len(accs),
            "coverage": coverage,
        }
