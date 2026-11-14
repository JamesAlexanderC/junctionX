"""Root pytest config: tests run on SQLite so Postgres is not required."""

import os

os.environ.setdefault("USE_SQLITE", "1")
