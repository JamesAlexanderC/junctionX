"""P1.2: rank customers for demo stories and suggest 5.

Stories: payday splurger (#14), secret saver (#75), nearly mortgage-ready
(#30 buffer 1-3 months, applied for a mortgage), multi-account (#41-#43).
The scan is chunked and keeps only per-customer daily totals.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from coach.management import csvdata


def _own_types():
    try:
        from inferences.thresholds import OWN_TRANSFER_TYPES

        return {t.lower() for t in OWN_TRANSFER_TYPES}
    except ImportError:
        return {"own_transfer", "savings_transfer"}


class Command(BaseCommand):
    help = "Suggest demo customers with clear stories."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir")
        parser.add_argument("--top", type=int, default=5)

    def handle(self, *args, **opts):
        import pandas as pd

        data_dir = Path(opts["data_dir"]) if opts["data_dir"] else None
        own = _own_types()
        daily_parts, accounts = [], {}
        for chunk in csvdata.iter_transactions(data_dir):
            amt = chunk["tx_amount_eur"]
            is_own = chunk["transaction_type"].str.lower().isin(own)
            chunk = chunk.assign(
                inflow=amt.where((amt > 0) & ~is_own, 0.0),
                spend=(-amt).where((amt < 0) & ~is_own, 0.0),
                saved=(-amt).where((amt < 0) & is_own, 0.0),
                day=chunk["tx_date"].dt.normalize(),
            )
            daily_parts.append(
                chunk.groupby(["customer_id", "day"]).agg(
                    inflow=("inflow", "sum"),
                    spend=("spend", "sum"),
                    saved=("saved", "sum"),
                    balance=("balance_after_eur", "last"),
                )
            )
            for cid, acc in chunk[["customer_id", "bank_account_id"]].values:
                accounts.setdefault(cid, set()).add(acc)
        daily = (
            pd.concat(daily_parts)
            .groupby(level=[0, 1])
            .agg({"inflow": "sum", "spend": "sum", "saved": "sum", "balance": "last"})
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
        picks = []
        for story, col, asc in (
            ("payday splurger", "payday_ratio", False),
            ("secret saver", "saver_share", False),
            ("nearly mortgage-ready", "mortgage_score", False),
            ("multi-account", "accounts", False),
        ):
            top = scores.sort_values(col, ascending=asc).head(10)
            self.stdout.write(f"\n== {story} ({col}) ==")
            self.stdout.write(top.round(3).to_string())
            for cid in top.index:
                if cid not in [p[0] for p in picks]:
                    picks.append((cid, story))
                    break
        for cid in scores.sort_values("payday_ratio", ascending=False).index:
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
        }
