"""Root pytest config.

Tests run on SQLite so Postgres is not required: conf/settings.py picks
SQLite whenever pytest is running (set USE_SQLITE=0 to test on Postgres).
"""
