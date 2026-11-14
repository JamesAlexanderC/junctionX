# Money Coach: prototype design

A mobile-first chat coach that lets an S-Pankki customer talk to their own
banking data. Django (REST + SSE) backend, React (Vite) frontend, Gemini as the
LLM. When no `GEMINI_API_KEY` is set, a deterministic **offline coach** answers
using the same analytics tools, so the demo always works.

## Product pillars

1. **Three baskets.** Every expense is sorted into:
   - `mandatory_regular` "Must-pay bills": Housing, Utilities, recurring
     subscriptions (same merchant, ~monthly, similar amount).
   - `mandatory_irregular` "Surprise essentials": Health, Home & Tech, Travel
     (one-off, needed, lumpy).
   - `leakage` "Everyday leakage": Restaurants, Entertainment, Lifestyle,
     Transportation (taxis = MCC 4121), small frequent optional spend.
   - Groceries is essential but frequent: counted as `mandatory_regular`.
   - Money movements (Invest Deposit/Withdraw, Salary Sweep) are **not** spend.
2. **Safe to spend.** Balance now, minus bills expected before next payday
   (derived from historical regular-bill timing), minus a small reserve, spread
   over the days until payday (derived from salary dates).
3. **What-if.** "Cut X by N%" projections over 1–5 years (monthly saving,
   compounded at a modest 3% p.a. savings rate).
4. **Spender persona.** Rule-based persona from savings rate, leakage share,
   balance volatility and investment habit, e.g. "Steady Saver",
   "Weekend Spender", "Paycheck-to-Paycheck", "Investor", "Comfortable".
5. **Home readiness.** For customers in the mortgage dataset: their real
   application timeline and outcome. For everyone: an affordability estimate
   (Finnish rules of thumb: 90% max LTV for first home, i.e. 10% deposit;
   stress-test at 6% interest over 25 years; loan payment ≤ ~35% of net income).
6. **Grounded answers.** Every number in a reply comes from a tool call over the
   customer's data. The LLM never invents figures.

"Today" in the prototype = the last transaction date in the dataset
(2026-09-30), so "last month" = September 2026.

## Data

Source: `../dataset/Junction-2026-S-pankki/` (CSV, UTF-8 BOM). Path is
configurable via `DATASET_DIR` env var. Loaded into Postgres (docker compose)
with `python backend/manage.py load_dataset` (COPY-based, ~3.6M transactions,
5,100 customers, 200 mortgage applications, 3,452 mortgage events), then
`python backend/manage.py build_profiles` precomputes a per-customer profile.

## Backend layout (`backend/`)

- `finance/` Django app: models (`Customer`, `Transaction`, `MortgageApplication`,
  `MortgageEvent`, `CustomerProfile`), loader commands, `analytics.py`
  (pure functions over one customer's transactions), REST views.
- `coach/` Django app: `tools.py` (LLM-callable tools wrapping analytics,
  returning JSON + optional chart), `providers/gemini.py` (google-genai with
  function calling), `providers/offline.py` (intent router + templates),
  `views.py` (SSE chat).

## API contract

All JSON. Money in EUR, floats rounded to 2 dp.

- `GET /api/health/` → `{"status":"ok","llm":{"provider":"gemini"|"offline",
  "model":str|null,"configured":bool},"data":{"customers":int,"transactions":int}}`
- `GET /api/customers/?search=&persona=&limit=50&offset=0` → `{"count":int,
  "results":[CustomerSummary]}`
- `GET /api/customers/featured/` → `[CustomerSummary]` (6–8 hand-picked:
  one per persona + a mortgage-approved + a mortgage-rejected customer)
- `CustomerSummary` = `{"customer_id","customer_age","customer_postal_code",
  "persona":{"key","label"},"monthly_income","monthly_spend","savings_rate",
  "balance","has_mortgage_application":bool,"mortgage_decision":str|null}`
- `GET /api/customers/<id>/overview/` →
  ```
  {
    "customer": CustomerSummary,
    "as_of": "2026-09-30",
    "balance": float,
    "income_monthly_avg": float, "spend_monthly_avg": float,
    "savings_rate": float,            // 0..1, (income-spend)/income
    "baskets": [{"key","label","monthly_avg","share",
                 "top_categories":[{"category","monthly_avg"}]}],
    "last_month": {"month":"2026-09","income","spend",
                   "baskets":{"mandatory_regular":f,"mandatory_irregular":f,
                              "leakage":f}},
    "monthly_cashflow": [{"month":"2025-10","income","spend","net"}],  // 12
    "safe_to_spend": {"amount","per_day","days_until_payday","next_payday",
                      "reserve","upcoming_bills":[{"label","amount","due"}]},
    "persona": {"key","label","description","traits":[str]},
    "insights": [{"title","text","tone":"good"|"warn"|"info"}],   // 3-5
    "home_readiness": {"has_application":bool, "decision":str|null,
                       "max_property_price":float, "deposit_needed":float,
                       "deposit_saved_estimate":float, "months_to_deposit":int|null,
                       "verdict":str}
  }
  ```
- `POST /api/chat/` body `{"customer_id", "messages":[{"role","content"}]}` →
  `text/event-stream`, one `data: <json>\n\n` per event:
  - `{"type":"meta","provider":"gemini"|"offline","model":str|null}` (first)
  - `{"type":"tool","name":str,"label":"Checking your transactions…"}`
  - `{"type":"token","text":str}` streamed answer (markdown subset: `**bold**`,
    `- ` lists, paragraphs)
  - `{"type":"chart","chart":{"kind":"bar"|"line"|"pie","title","unit":"€",
    "data":[{"label","value"}]}}`
  - `{"type":"concept","title","text"}` short explainer of a money concept
  - `{"type":"suggestions","items":[str]}` 2–3 follow-up questions
  - `{"type":"error","message"}`, `{"type":"done"}`

## Frontend (`frontend/`)

S-Pankki look (already in `App.css`). Screens: customer picker (featured +
search) → customer home (dashboard: balance, safe-to-spend hero, baskets donut,
12-month cashflow, persona card, insights, home readiness) → chat (existing,
plus tool-status line, follow-up chips, provider badge). Bottom tab bar
switches Home/Chat. Demo fallback (`mock.js`) when the backend is unreachable.

## Conventions

See `Contributing.md`: lines ≤ 88 chars, run `black` on Python, branch from
`develop`, never merge without the owner's say-so.
