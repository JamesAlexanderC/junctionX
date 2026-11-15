"""Where the synthetic other-bank data lives (data/ is gitignored)."""

import json
from functools import lru_cache

from django.conf import settings

SYNTHETIC_DIR = settings.BASE_DIR.parent / "data" / "synthetic"
EXTERNAL_BANKS_FILE = SYNTHETIC_DIR / "external_banks.json"


@lru_cache(maxsize=1)
def _load(mtime):
    return json.loads(EXTERNAL_BANKS_FILE.read_text())


def external_data() -> dict:
    """The generated file, or an empty dataset if it was never generated."""
    if not EXTERNAL_BANKS_FILE.exists():
        return {"customers": {}, "banks": {}}
    return _load(EXTERNAL_BANKS_FILE.stat().st_mtime)


def bank_accounts(customer_id: str, bank_code: str) -> list[dict]:
    """Berlin-Group-shaped accounts this customer holds at this bank."""
    banks = external_data()["customers"].get(customer_id, {})
    return (banks.get(bank_code) or {}).get("accounts", [])
