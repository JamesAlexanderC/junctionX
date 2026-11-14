"""Shared helpers to read the S-Bank CSVs (context.md "The data")."""

from django.conf import settings
from django.core.management.base import CommandError

TX_FILE = "tx_junction_transactions.csv"
CUSTOMERS_FILE = "tx_customers_junction.csv"
MTG_HISTORY_FILE = "mtg_negotiation_history.csv"
MTG_LINK_FILE = "mtg_tx_customer_link_and_final_mtg_infio.csv"
ENCODING = "utf-8-sig"  # the CSVs start with a UTF-8 BOM
CHUNK_ROWS = 500_000
SAS_TIMESTAMP_FORMAT = "%d%b%y:%H:%M:%S"  # e.g. 03OCT24:09:04:04
MAX_TIMESTAMP_FAILURE_SHARE = 0.01


def data_path(name, data_dir=None):
    path = (data_dir or settings.DATA_DIR) / name
    if not path.exists():
        raise CommandError(
            f"{path} not found. Put the S-Bank CSVs in DATA_DIR (see README.md)."
        )
    head = path.read_bytes()[:200] if path.stat().st_size < 1024 else None
    if head is None:
        with path.open("rb") as fh:
            head = fh.read(200)
    if head.lstrip(b"\xef\xbb\xbf").startswith(b"version https://git-lfs"):
        raise CommandError(
            f"{path} is a Git LFS pointer, not data. Use 'Download raw file' or "
            "clone with Git LFS and run `git lfs pull`."
        )
    return path


def read_small(name, data_dir=None):
    import pandas as pd

    return pd.read_csv(data_path(name, data_dir), encoding=ENCODING)


def iter_transactions(data_dir=None, customers=None, chunksize=CHUNK_ROWS):
    """Yield cleaned chunks of the transactions file, optionally filtered.

    Adds ``tx_id`` = ``<customer_id>-<row number>`` (the CSV has no id).
    """
    import pandas as pd

    path = data_path(TX_FILE, data_dir)
    keep = {str(c) for c in customers} if customers else None
    offset = 0
    for chunk in pd.read_csv(
        path,
        encoding=ENCODING,
        chunksize=chunksize,
        dtype={
            "customer_id": str,
            "bank_account_id": str,
            "merchant_id": str,
            "mcc_code": str,
            "category": str,
            "transaction_type": str,
        },
    ):
        chunk["tx_id"] = [f"r{offset + i}" for i in range(len(chunk))]
        offset += len(chunk)
        if keep is not None:
            chunk = chunk[chunk["customer_id"].isin(keep)]
            if chunk.empty:
                continue
        yield clean(chunk)


def parse_timestamp(values, strict=False, column="tx_timestamp"):
    """Parse the CSVs' SAS datetimes (03OCT24:09:04:04) into naive timestamps.

    Falls back to ISO parsing for any value that is not SAS formatted, so
    hand-made test CSVs keep working. Unparseable values become NaT. With
    ``strict``, raises CommandError when more than 1% of non-empty values
    still fail, so a format change cannot silently turn every timestamp into
    midnight (P1.2).
    """
    import pandas as pd

    if values is None:
        return pd.Series(dtype="datetime64[ns]")
    raw = pd.Series(values).astype("string").str.strip()
    ts = pd.to_datetime(raw, format=SAS_TIMESTAMP_FORMAT, errors="coerce")
    missing = ts.isna() & raw.notna() & (raw != "")
    if missing.any():
        iso = pd.to_datetime(raw[missing], format="ISO8601", errors="coerce", utc=True)
        ts.loc[missing] = iso.dt.tz_localize(None)
    if strict:
        present = raw.notna() & (raw != "")
        failed = ts.isna() & present
        n_present, n_failed = int(present.sum()), int(failed.sum())
        if n_present and n_failed / n_present > MAX_TIMESTAMP_FAILURE_SHARE:
            sample = raw[failed].head(3).tolist()
            raise CommandError(
                f"{n_failed} of {n_present} {column} values do not match "
                f"{SAS_TIMESTAMP_FORMAT}, e.g. {sample}"
            )
    return ts


def parse_timestamps(values, column="tx_timestamp"):
    """Strict parse_timestamp: fails above 1% unparseable values."""
    return parse_timestamp(values, strict=True, column=column)


def clean(df):
    import pandas as pd

    df = df.copy()
    df["tx_id"] = df["customer_id"].astype(str) + "-" + df["tx_id"].astype(str)
    df["tx_date"] = pd.to_datetime(df["tx_date"], errors="coerce")
    df["tx_timestamp"] = parse_timestamps(df.get("tx_timestamp")).fillna(df["tx_date"])
    for col in ("tx_amount_eur", "balance_after_eur"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["mcc_code"] = (
        df["mcc_code"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    )
    for col in ("category", "transaction_type", "merchant_id"):
        df[col] = df[col].fillna("").astype(str)
    return df.dropna(subset=["tx_date", "tx_amount_eur"])
