## The three musketeers

### Setup

With direnv installed and configured, run `setup` from the repo root. It:

- creates `.env` from `.env.example` if you don't have one yet (placeholder
  passwords are replaced with random values)
- creates the Python virtualenv and installs backend dependencies
- installs the frontend dependencies

Use `setup --backend-only` or `setup --frontend-only` to set up one half, and
`--clean` to reinstall from scratch. Then start Postgres with
`docker compose up -d`.