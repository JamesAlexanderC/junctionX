## The three musketeers: Saldo

Saldo is an AI money coach for S-Bank's "Personal Economic Trainer" challenge
(Junction 2026). Python (pandas) computes every number, and Gemini (via
`google-genai`) picks tools and explains the results. The full spec is
`context.md`; the shared contract every part follows is in `CLAUDE.md`.

```
backend/inferences/  pure pandas inferences #1-#102 (DataFrame in, dicts out)
backend/coach/       Django app: models, API, Gemini loop, alert coach, commands
frontend/            React + Vite chat client
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

Everything runs on the real S-Bank data; there is no demo or mock data.
Without loaded data the API knows no customers, and without
`GEMINI_API_KEY` the chat endpoint answers 503.

### Real S-Bank data (once)

Put the four CSVs in the folder named by `DATA_DIR` in `.env` (default
`data/dataset/Junction-2026-S-pankki`; `data/` is gitignored). The
transactions file is Git LFS: check `head -c 200` shows CSV rows. Start
Postgres (`docker compose up -d`), then in `backend/`:

```
python manage.py migrate
python manage.py load_data      # all 5,100 customers, 3.6M rows (~3 min, COPY)
                                # then build_artifacts (~3 min): peer table
                                # (#36/#37) and mortgage model (#34, AUC ~0.73)
```

`load_data --replace` reloads; `--customers ID,ID` loads a subset;
`--skip-artifacts` skips the second step (run `build_artifacts` later).

Profiles are built on demand the first time a customer is asked for (1 to 5
s), as of `AS_OF_DATE` (default: the date of the last transaction,
2026-09-30), and cached. They rebuild when the inference code changes or the
customer's goals or loan details change. To prebuild:
`python manage.py build_profiles --customers CUST00001,CUST00002` (or `--all`).

Other commands:

```
python manage.py explore_data           # data profile -> docs/data_profile.md
python manage.py rank_demo_customers    # customers with clear stories
python manage.py run_evals --customer CUST00001   # Gemini eval set (needs a key)
```

Endpoints: `GET /api/customers/?q=`, `GET /api/insights/<id>/` (only the
insights the data supports), `GET /api/home/<id>/` (full profile),
`POST /api/chat/`. See `CLAUDE.md` for the contract and `docs/vocabulary.md`
for what the category / transaction_type / MCC values mean.

### Checks (before every PR)

```
check            # black, django check, migrations, pytest, vitest, lint, build
check --fix      # reformat with black first
```

Backend tests (via `check`) run on SQLite with Gemini mocked, so they need
neither Postgres nor an API key. Test-only fixtures live under `*/tests/`. See `Contributing.md` for branching and style rules.
