"""Check every step of handoff/real-data-and-demo-customers.md passes.

Run: ``manage.py verify_handoff`` (all steps) or ``--step 3``. Exits 1 if any
selected check fails, so it can gate a PR.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from coach.management import csvdata

REPO = Path(settings.BASE_DIR).parent
PROFILE_MD = REPO / "docs" / "data_profile.md"
THRESHOLDS_PY = Path(settings.BASE_DIR) / "inferences" / "thresholds.py"
MODEL_REPORT = REPO / "docs" / "mortgage_model.json"
LFS_POINTER = b"version https://git-lfs"
TX_COLUMNS = {
    "customer_id",
    "bank_account_id",
    "tx_date",
    "tx_timestamp",
    "category",
    "tx_amount_eur",
    "balance_after_eur",
    "transaction_type",
    "merchant_id",
    "mcc_code",
}
DEMO_MIN, DEMO_MAX = 3, 5
AUC_TARGET = 0.70
MODEL_MAX_FEATURES = 6
MODEL_MODES = {"model", "percentile_fallback"}


@dataclass(frozen=True)
class Result:
    step: int
    name: str
    ok: bool
    detail: str


def _data_dir():
    return Path(csvdata.data_path(csvdata.TX_FILE)).parent


def check_data_files():
    """Step 1: four real CSVs, not LFS pointers, expected tx columns."""
    names = (
        csvdata.TX_FILE,
        csvdata.CUSTOMERS_FILE,
        csvdata.MTG_HISTORY_FILE,
        csvdata.MTG_LINK_FILE,
    )
    for name in names:
        path = _data_dir() / name
        if not path.exists():
            return False, f"missing {path}"
        with open(path, "rb") as fh:
            if fh.read(200).startswith(LFS_POINTER):
                return False, f"{name} is a Git LFS pointer: run git lfs pull"
    with open(_data_dir() / csvdata.TX_FILE, encoding="utf-8-sig") as fh:
        header = set(fh.readline().strip().split(","))
    missing = TX_COLUMNS - header
    if missing:
        return False, f"transactions missing columns {sorted(missing)}"
    return True, "4 CSVs present with expected columns"


def check_profile_and_sign():
    """Step 2: data_profile.md written; inflows positive, purchases negative."""
    if not PROFILE_MD.exists():
        return False, "run manage.py explore_data"
    text = PROFILE_MD.read_text()
    shares = dict(re.findall(r"^\| (\w+) \| \d+ \| ([\d.]+) \|$", text, re.M))
    if not shares:
        return False, "no transaction_type table in data_profile.md"
    if shares.get("salary") != "1.00" or shares.get("purchase") != "0.00":
        return False, f"unexpected sign convention: {shares}"
    return True, "salary 100% positive, purchase 100% negative (inflow > 0)"


def _profile_values(section):
    text = PROFILE_MD.read_text() if PROFILE_MD.exists() else ""
    block = text.split(f"## {section}", 1)[-1].split("\n## ", 1)[0]
    values = re.findall(r"^\| ([^|]+?) \|", block, re.M)
    return {v.strip().lower() for v in values} - {"value"}


def check_vocabulary():
    """Step 3: no TODOs left and every vocab value exists in the real data."""
    from inferences import thresholds as th

    if "TODO confirm" in THRESHOLDS_PY.read_text():
        return False, "thresholds.py still has 'TODO confirm' markers"
    cats = _profile_values("category")
    types_ = _profile_values("transaction_type")
    unknown = sorted(
        (set(th.ESSENTIAL_CATEGORIES) - cats)
        | ({t.lower() for t in th.OWN_TRANSFER_TYPES} - types_)
    )
    if unknown:
        return False, f"values not in real data: {unknown}"
    return True, "vocabulary sets match values seen in the data"


def _demo_ids():
    return list(settings.DEMO_CUSTOMERS)


def check_demo_customers():
    """Step 4: 3 to 5 DEMO_CUSTOMERS, all real customer ids."""
    ids = _demo_ids()
    if not DEMO_MIN <= len(ids) <= DEMO_MAX:
        return False, f"DEMO_CUSTOMERS has {len(ids)} ids, need {DEMO_MIN}-{DEMO_MAX}"
    known = set(csvdata.read_small(csvdata.CUSTOMERS_FILE)["customer_id"])
    unknown = [c for c in ids if c not in known]
    if unknown:
        return False, f"not in customers CSV: {unknown}"
    return True, f"{len(ids)} demo customers: {','.join(ids)}"


def _csv_counts(ids):
    counts = dict.fromkeys(ids, 0)
    for chunk in csvdata.iter_transactions(customers=ids):
        for cid, n in chunk["customer_id"].value_counts().items():
            counts[cid] += int(n)
    return counts


def check_loaded_and_served():
    """Step 5: DB rows match CSV, timestamps parsed, profile served by API."""
    from django.test import Client

    from coach.models import Transaction

    ids = _demo_ids()
    if not ids:
        return False, "no DEMO_CUSTOMERS (step 4 first)"
    for cid, expected in _csv_counts(ids).items():
        txs = Transaction.objects.filter(customer_id=cid)
        got = txs.count()
        if got != expected:
            return False, f"{cid}: {got} rows in DB, {expected} in CSV"
        if not txs.exclude(tx_timestamp__hour=0, tx_timestamp__minute=0).exists():
            return False, f"{cid}: every tx_timestamp is midnight (SAS parse failed)"
    client = Client()
    for cid in ids:
        resp = client.get(f"/api/home/{cid}/")
        if resp.status_code != 200:
            return False, f"GET /api/home/{cid}/ -> {resp.status_code}"
    return True, "rows match CSV, timestamps parsed, /api/home/ 200 for all"


def check_mortgage_model():
    """Step 6: model report with AUC, mode chosen by the 0.70 rule."""
    if not MODEL_REPORT.exists():
        return False, f"missing {MODEL_REPORT.name}: run fit_mortgage_model"
    report = json.loads(MODEL_REPORT.read_text())
    auc, mode = report.get("cv_auc"), report.get("mode")
    features = report.get("features", [])
    if auc is None or mode not in MODEL_MODES:
        return False, f"report needs cv_auc and mode in {sorted(MODEL_MODES)}"
    expected = "model" if auc >= AUC_TARGET else "percentile_fallback"
    if mode != expected:
        return False, f"AUC {auc:.3f} should use mode {expected}, got {mode}"
    if not 1 <= len(features) <= MODEL_MAX_FEATURES:
        return False, f"{len(features)} features, need 1-{MODEL_MAX_FEATURES}"
    return True, f"5-fold CV AUC {auc:.3f} -> {mode} ({len(features)} features)"


CHECKS = (
    (1, "data files", check_data_files),
    (2, "explore + sign", check_profile_and_sign),
    (3, "vocabulary", check_vocabulary),
    (4, "demo customers", check_demo_customers),
    (5, "load + serve", check_loaded_and_served),
    (6, "mortgage model", check_mortgage_model),
)


def run_checks(steps=None):
    results = []
    for step, name, fn in CHECKS:
        if steps and step not in steps:
            continue
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 - a crash is a failed check
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        results.append(Result(step, name, ok, detail))
    return results


class Command(BaseCommand):
    help = "Verify each step of the real-data handoff."

    def add_arguments(self, parser):
        parser.add_argument("--step", type=int, action="append")

    def handle(self, *args, **opts):
        results = run_checks(opts["step"])
        for r in results:
            style = self.style.SUCCESS if r.ok else self.style.ERROR
            mark = "PASS" if r.ok else "FAIL"
            self.stdout.write(style(f"[{mark}] {r.step}. {r.name}: {r.detail}"))
        if not all(r.ok for r in results):
            raise CommandError("handoff not complete")
