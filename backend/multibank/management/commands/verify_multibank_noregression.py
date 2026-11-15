"""No-regression check (MULTIBANK_PLAN.md MB-4): customers without a linked
bank must get exactly the profile they got before the multibank feature.

The snapshot (data/synthetic/noregression_snapshot.json) was taken on develop
before any multibank change. Every section except generated_at and the
multibank section itself must be identical.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from coach import services
from multibank.data import SYNTHETIC_DIR
from multibank.models import BankConsent

SNAPSHOT = SYNTHETIC_DIR / "noregression_snapshot.json"
IGNORED = {"generated_at", "multibank"}


NEW_ALERTS = {112}  # #112 partial-view nudge: planned for unlinked customers


def _sections(profile):
    """Profile minus what the plan adds on purpose for unlinked customers:
    the multibank section, the #112 nudge and the partial_view caveat."""
    out = {k: v for k, v in profile.items() if k not in IGNORED}
    out["alerts"] = [
        a for a in out.get("alerts", []) if a.get("inference") not in NEW_ALERTS
    ]
    # availability["alerts"] only says whether any alert exists; the alert
    # list itself is compared above (without #112).
    out["availability"] = {
        item: {k: v for k, v in rule.items() if k != "caveat"}
        for item, rule in (out.get("availability") or {}).items()
        if item != "alerts"
    }
    return out


def _nudged(profile):
    return any(a.get("inference") in NEW_ALERTS for a in profile.get("alerts", []))


def _diff(old, new):
    keys = sorted(set(old) | set(new))
    return [k for k in keys if old.get(k) != new.get(k)]


class Command(BaseCommand):
    help = "Compare unlinked customers' profiles with the pre-multibank snapshot."

    def handle(self, *args, **options):
        if not SNAPSHOT.exists():
            raise CommandError(f"No snapshot at {SNAPSHOT}")
        snap = json.loads(SNAPSHOT.read_text())
        linked = set(
            BankConsent.objects.filter(status="active").values_list(
                "customer_id", flat=True
            )
        )
        checked, failed, nudged = 0, [], []
        for customer_id in snap["customers"]:
            if customer_id in linked:
                self.stdout.write(f"skip {customer_id}: has a linked bank")
                continue
            profile = services.build(customer_id)
            if _nudged(profile):
                nudged.append(customer_id)
            new = _sections(profile)
            changed = _diff(_sections(snap["profiles"][customer_id]), new)
            checked += 1
            if changed:
                failed.append((customer_id, changed))
        for customer_id, changed in failed:
            self.stdout.write(f"CHANGED {customer_id}: {', '.join(changed)}")
        self.stdout.write(f"{checked - len(failed)}/{checked} identical")
        self.stdout.write(f"partial-view nudge (#112): {', '.join(nudged) or 'none'}")
        if failed:
            raise CommandError("Unlinked profiles changed")
