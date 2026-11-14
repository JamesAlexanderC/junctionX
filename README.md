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

## Money Coach

A mobile-first chat coach that lets an S-Pankki customer talk to their own
banking data: a dashboard (safe to spend, three spending baskets, 12-month
cashflow, spender persona, home readiness) and a streaming chat whose every
number comes from analytics over the customer's real transactions.

### Run the demo

Prerequisites: Python 3.12+, Node.js, Docker, and the dataset at
`../dataset/Junction-2026-S-pankki/` (or set `DATASET_DIR` in `.env`).

```sh
scripts/bin/setup                                   # .env, virtualenv, npm install
docker compose up -d                                # Postgres
cd backend
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py load_dataset          # ~3.6M transactions, a few minutes
../.venv/bin/python manage.py build_profiles        # per-customer personas
cd ..
scripts/bin/demo                                    # API :8000 + app :5173
```

Open <http://localhost:5173>. `scripts/bin/demo` simply runs
`manage.py runserver 8000` and `npm --prefix frontend run dev -- --port 5173`
side by side (the Vite dev server proxies `/api` to Django); start them by hand
if you prefer.

- **Gemini:** put a Google AI Studio key in `.env` as `GEMINI_API_KEY=...`
  (optionally `GEMINI_MODEL`) and restart the backend. Without a key the
  built-in **offline coach** answers with the same tools, charts and
  follow-ups, so the demo never depends on the network.
- **Demo mode:** add `?demo=1` to the URL to run the frontend on mock data
  only. It also kicks in automatically when the backend is unreachable.
- **Tests and checks:**

  ```sh
  cd backend && ../.venv/bin/python manage.py test   # backend tests
  .venv/bin/black --check backend                    # formatting
  npm --prefix frontend run lint                     # frontend lint
  npm --prefix frontend run build                    # production build
  ```

### Architecture

- `backend/finance/`: data models, the `load_dataset` / `build_profiles`
  commands, `analytics.py` (pure functions over one customer's transactions:
  baskets, safe to spend, personas, insights, affordability) and the REST API
  (`/api/health/`, `/api/customers/`, `/api/customers/<id>/overview/`).
- `backend/coach/`: LLM-callable tools wrapping the analytics, the Gemini
  provider (function calling) and the deterministic offline provider, served
  as Server-Sent Events from `POST /api/chat/`.
- `frontend/`: React (Vite) app with a customer picker, the Home dashboard and
  the Coach chat. Dashboard cards and insights hand a question straight to the
  coach.

See [docs/design.md](docs/design.md) for the product pillars, the API contract
and data notes.
