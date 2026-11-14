@AGENTS.md

# Saldo: shared contract

Full spec: `context.md` (inference and alert numbers #1 to #102 are stable; cite
them in code comments). Everything below is binding for every teammate.

## Rules
- The app's model is **Gemini via `google-genai`**. Claude Code is only used to build it.
- Python (pandas) computes every number. Gemini only picks tools and explains results.
- Every Gemini turn ends with a `send_reply` function call; Django validates it.
- Max line length 88, run `black` before a PR (see Contributing.md).

## Layout
- `backend/inferences/` pure functions: DataFrame in, plain dicts out. Thresholds in
  `inferences/thresholds.py`, shared maths in `inferences/models.py`.
  `inferences/profile.py: build_profile(df, customer, today, goals=None, loans=None)`
  returns the profile dict below. `inferences/alerts.py: run_all_alerts(df, profile,
  today)` returns alert dicts.
- `backend/coach/` Django app: models, `load_data` / `build_profiles` commands, API,
  Gemini loop (`coach/gemini/`), alert coach planner.
- `frontend/` React + Vite (JSX), chat-first. No mock or fixture data at runtime:
  if the API is down it says so.
- No demo data anywhere at runtime. Fixtures live only under `*/tests/`
  (`backend/coach/tests/fixtures/profile_demo.json` is a test sample).
- Profile shape = whatever `build_profile` returns: top-level keys
  `customer_id, today, customer, balance, income, baskets, spending, habits,
  forecast, whatif, mortgage, levels, goals, benchmarks, multibank, alerts,
  availability` (`availability[item] = {available, reason, inferences}`).
  Profiles are built on demand from the DB as of `AS_OF_DATE` (default: date
  of the last transaction) and cached in the Profile table.
- `handoff/` notes for work too far out of scope to finish here.
- `scripts/bin/`: `setup`, `dev` (run everything), `check` (all PR checks).

## Transaction DataFrame columns
`tx_id, customer_id, bank_account_id, tx_date (datetime64), tx_timestamp
(datetime64), category, tx_amount_eur (float, inflow > 0), balance_after_eur,
transaction_type, merchant_id, mcc_code (str)`.
Own-account transfers: `transaction_type` in `OWN_TRANSFER_TYPES`
(thresholds.py), to be confirmed against real data.

## API
- Auth: every endpoint needs `Authorization: Token <key>` (DRF TokenAuthentication,
  401 without). `POST /api/auth/login/ {username, password}` -> `{token, user}`
  (400 on wrong credentials), `POST /api/auth/logout/` deletes the token,
  `GET /api/auth/me/` -> `{user}`. Users are Django users (`createsuperuser`);
  any logged-in user may open any customer. `/api/schema/` and docs stay public.
- `GET /api/home/<customer_id>/` -> full profile JSON (404 if unknown).
- `GET /api/insights/<customer_id>/` -> `{customer_id, as_of, insights: [{key,
  inference, title, value, unit, text, section, severity?}]}`: only insights
  the data supports, alerts first.
- `POST /api/chat/` `{customer_id, message, history, depth?}` -> send_reply JSON;
  503 `{"error": ...}` without `GEMINI_API_KEY`.
- `GET /api/goals/?customer_id=` -> `{customer_id, as_of, active: [{id, name,
  emoji, type, priority, paused, target, saved, progress_pct, expected_pct,
  on_track, target_date, projected_date, months_needed, difficulty,
  monthly_needed, realistic, suggested_monthly, suggested_date, tip: {text,
  shortfall}|null, milestones_hit}], completed: [{id, name, type}], clash:
  {clash, total_needed, safe_to_save_monthly}|null}` (`insights.goal_summary`,
  fields as `profile["goals"]` computed them; 400 without `customer_id`, 404 if
  unknown). Active goals are shown here, not in `/api/insights/`.
- `POST /api/goals/`, `PATCH /api/goals/<id>/`, `POST /api/goals/<id>/rate/`.
- `GET /api/spending/?customer_id=` -> `{customer_id, as_of, month, is_current,
  total, categories: [{category, total, share, count, usual, vs_usual}],
  savings: [{category, total, count}], savings_total}`
  (`insights.spending_summary` of `profile["spending"]`, built by
  `inferences/spending.py`): spending per data `category`, names spelt as in
  the data, this month else last month (`is_current`). Spending = outflows
  minus own-account and Saver transfers (`common.spend`). `usual` = the #24
  mean monthly spend over the last 3 full months (`whatif.category_means`),
  null without history; `vs_usual = total - usual`. Saver deposits (#75, e.g.
  "Invest Deposit") are listed under `savings`, not in `total`. 400 without
  `customer_id`, 404 if unknown.
- `POST /api/loans/` `{customer_id, balance, interest_rate, years_left}`.
- `GET /api/customers/?q=&limit=50` -> `[{customer_id, customer_age,
  customer_postal_code}]` (real customers only).
- `GET /api/customers/demo/` -> `{built, as_of, demos: [{demo, customer_id,
  income_level, income_label, spender_type, clarity}], customers: [{customer_id,
  income_level (0-5), income_label, spender_type}]}`: one
  demo per spender type (#16) spread over the income fifths, plus every
  customer for the landing page (`inferences/demo.py`). Cached by
  `manage.py build_customer_index`; `built: false` until it has run.
- Tools return `{"available": false, "reason": ...}` when the data does not
  support an inference; Gemini must say so, never substitute a default.

## send_reply
```json
{"text": "You can safely spend EUR 64 this week.",
 "depth": 2,
 "cards": [{"type": "number", "label": "Safe to spend", "value": 64},
           {"type": "basket_bar", "essential": 820, "surprise": 120,
            "leaky": 212, "saver": 150}],
 "chips": ["Show me why", "What can I do?", "Make it a goal"]}
```
Card types (whitelist): number, chart, basket_bar, slider, goal, level_progress,
question, alert, plan, before_after. Max 3 chips. Depth 1 Quick, 2 Explain,
3 What-if, 4 Plan.

Card payloads:
- number `{label, value, unit?: "EUR"}`
- chart `{kind: "bar"|"line", title, unit?, data: [{label, value}]}`
- basket_bar `{essential, surprise, leaky, saver}`
- slider `{category, monthly_spend, min_pct: 0, max_pct: 50, pct, goal?: {target,
  saved, monthly_rate}}` (frontend recomputes #24 / #26 locally)
- goal `{name, target, saved, target_date, difficulty, monthly_needed}`
- level_progress `{level, name, progress, euros_to_go, next_step, ladder?:
  [{level, name, reached}]}` (`get_level` returns it ready as `card`)
- question `{question, options: [str], quick_answer?: str}`
- alert `{id, severity, title, text}`
- plan `{steps: [{text, monthly_impact, clears: [alert_id]}]}`
- before_after `{before: {safe_to_spend, buffer_months, goal_date}, after: {...}}`

## Gemini tools
get_category_spend, get_safe_to_spend, get_safe_to_save, get_baskets, get_level,
simulate_cut, forecast_balance, get_spender_type, list_goals, create_goal,
rate_goal, get_detected_goals, get_mortgage_readiness, get_explainer,
get_benchmark, get_alerts, explain_alert, suggest_fixes, simulate_plan,
accept_plan, snooze_alert, list_inferences, get_inference, get_chart, manage_goal,
save_loan_details, dismiss_suggestion, send_reply.
- Code in `coach/gemini/tools/` (one module per area, `registry.py` maps
  names). Every profile item Gemini can read is one entry in
  `coach/gemini/catalogue.py`; add an entry to expose a new inference.
- Writes are proposed first and run only on a yes to the same proposal;
  `manage_goal add_saved` may run at once when Python sees the amount in the
  message and one goal fits. See `docs/gemini_tools.md`.
- Card payloads are validated (`coach/gemini/cards.py`); numbers in cards
  must come from tool results, like the reply text.

## Shared formulas the frontend copies
- #24 monthly saving = p * mean monthly category spend; yearly = 12x.
- #26 months = ceil((target - saved) / r); r <= 0 -> "not reachable".
