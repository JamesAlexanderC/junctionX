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
  `customer_id, today, customer, balance, income, baskets, habits, forecast,
  whatif, mortgage, levels, goals, benchmarks, multibank, alerts,
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
- `GET /api/home/<customer_id>/` -> full profile JSON (404 if unknown).
- `GET /api/insights/<customer_id>/` -> `{customer_id, as_of, insights: [{key,
  inference, title, value, unit, text, section, severity?}]}`: only insights
  the data supports, alerts first.
- `POST /api/chat/` `{customer_id, message, history, depth?}` -> send_reply JSON;
  503 `{"error": ...}` without `GEMINI_API_KEY`.
- `POST /api/goals/`, `PATCH /api/goals/<id>/`, `POST /api/goals/<id>/rate/`.
- `POST /api/loans/` `{customer_id, balance, interest_rate, years_left}`.
- `GET /api/customers/?q=&limit=50` -> `[{customer_id, customer_age,
  customer_postal_code}]` (real customers only).
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
- level_progress `{level, name, progress, euros_to_go, next_step}`
- question `{question, options: [str], quick_answer?: str}`
- alert `{id, severity, title, text}`
- plan `{steps: [{text, monthly_impact, clears: [alert_id]}]}`
- before_after `{before: {safe_to_spend, buffer_months, goal_date}, after: {...}}`

## Gemini tools
get_category_spend, get_safe_to_spend, get_safe_to_save, get_baskets, get_level,
simulate_cut, forecast_balance, get_spender_type, list_goals, create_goal,
rate_goal, get_detected_goals, get_mortgage_readiness, get_explainer,
get_benchmark, get_alerts, explain_alert, suggest_fixes, simulate_plan,
accept_plan, snooze_alert, send_reply.

## Shared formulas the frontend copies
- #24 monthly saving = p * mean monthly category spend; yearly = 12x.
- #26 months = ceil((target - saved) / r); r <= 0 -> "not reachable".
