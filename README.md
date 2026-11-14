## The three musketeers: Saldo

Saldo is an AI money coach for S-Bank's "Personal Economic Trainer" challenge
(Junction 2026). Python (pandas) computes every number, and Gemini (via
`google-genai`) picks tools and explains the results. The full spec is
`context.md`; the shared contract every part follows is in `CLAUDE.md`.

```
backend/inferences/  pure pandas inferences #1-#102 (DataFrame in, dicts out)
backend/coach/       Django app: models, API, Gemini loop, alert coach, commands
frontend/            React + Vite phone-frame app (Home, Explore, Chat, Alerts)
shared/fixtures/     profile_demo.json, the canonical profile shape
handoff/             work too far out of scope for the implementation branch
docs/                data vocabulary, calibration notes, platform guides
```

### Setup

With direnv installed and configured (`scripts/bin` goes on your PATH), run
`setup` from the repo root. Without direnv, use `scripts/bin/setup`. It:

- creates `.env` from `.env.example` (placeholder passwords become random
  values), or adds any keys `.env.example` gained since your `.env` was made
- creates the Python virtualenv and installs backend + dev dependencies
- installs the frontend dependencies

Use `setup --backend-only` or `setup --frontend-only` for one half, and
`--clean` to reinstall from scratch.

`.env` is not tracked by git. Never commit it: it holds `GEMINI_API_KEY`.

### Run

```
dev              # Postgres (docker) + migrate + Django :8000 + Vite :5173
dev --sqlite     # same, but backend/db.sqlite3 instead of Postgres
dev --frontend-only
```

Open http://localhost:5173. Vite proxies `/api` to Django. API docs are at
http://localhost:8000/api/docs/.

What you get today:

- With no data loaded, the backend serves the demo customer `demo-aino` from
  `shared/fixtures/profile_demo.json`.
- With no `GEMINI_API_KEY`, chat returns canned offline replies built from
  the profile. Set the key in `.env` for real Gemini answers.
- If the API is down, the frontend falls back to the fixture and a local mock
  coach, so the UI always works.

### Real S-Bank data

Put the four CSVs in the folder named by `DATA_DIR` in `.env` (default
`data/dataset/Junction-2026-S-pankki`; `data/` is gitignored). The
transactions file is Git LFS: check `head -c 200` shows CSV rows. Then, in
`backend/`:

```
python manage.py explore_data           # data profile -> docs/data_profile.md
python manage.py rank_demo_customers    # suggests 5 demo customers
# set DEMO_CUSTOMERS=CUST...,CUST... in .env
python manage.py load_data              # load those customers into the DB
python manage.py build_profiles         # run every inference, store profiles
python manage.py run_evals              # Gemini eval set (needs a key)
```

See `docs/vocabulary.md` for what the real category / transaction_type / MCC
values mean, and `handoff/real-data-and-demo-customers.md` for the open
issues.

### Checks (before every PR)

```
check            # black, django check, migrations, pytest, vitest, lint, build
check --fix      # reformat with black first
```

Backend tests run on SQLite with Gemini mocked, so they need neither Postgres
nor an API key. See `Contributing.md` for branching and style rules.
