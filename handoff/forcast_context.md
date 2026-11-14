# Forecasting (#17 to #23): context

Everything needed to work on the forecast without rereading the whole repo.
The spec is `context.md` "Forecasts (#17 to #23)"; cite inference numbers in
code comments. Python computes every number; Gemini only reads them.

## What it produces

`inferences/forecast.py: compute_forecast(df, today, income, baskets)` builds
`profile["forecast"]`. It runs after income and baskets in
`inferences/profile.py`, and its output feeds goals, mortgage and alerts.

| Key | # | How it is calculated |
|---|---|---|
| `balance` | | Latest `balance_after_eur` (`common.latest_balance`) |
| `buffer` | | `max(EUR 50, 10% of monthly essentials)` (`common.buffer_amount`) |
| `daily_discretionary` | #19 | `{stat, value, std}`: d and sigma over the last 60 days of non-bill spend, with days without spend counted as 0 |
| `safe_to_spend_week` | #17 | `(B - bills due before payday - planned saving x share of cycle left - buffer) x min(7, days to payday) / days to payday`, floored at 0 |
| `safe_to_save_today` | #18 | `max(0, lowest low bound before payday - buffer)` |
| `end_of_month` | #19 | `{expected, low, high}` on the last day of the month (an 80% band) |
| `daily_path` | #19, #20 | `[{date, expected, low, high}]` for each day from tomorrow to `max(month end, payday)` |
| `danger_days` | #20 | Dates before the next payday where `low < EUR 50` |
| `upcoming_bills` | #21 | `[{date, name, merchant_id, amount}]` in the next 30 days. Next date = last payment + median gap; amount = median |
| `surprise_fund_monthly` | #22 | Surprises over the last 12 months / min(12, months of data) |
| `seasonal` | #23 | `{next_month, ratio, warn, pot}`: ratio = next month last year / mean month last year; warn when > 1.25, pot = (ratio - 1) x mean |

### The projection (model 6)

`inferences/models.py: project_balance(b0, start, end, d, sigma, scheduled)`
is a random walk with drift:

```
balance(t) = balance(t-1) - d + income(t) - bills(t)
band       = +/- BAND_Z x sigma x sqrt(t)      (BAND_Z = 1.28, an 80% band)
```

`scheduled` holds signed `(date, amount)` flows from `forecast._scheduled`:
- Each bill repeats by its median gap (`scheduled_bills`).
- The salary repeats monthly from `next_payday`. Only the retained part is
  added: the payday amount minus whatever the `salary_sweep` moves out the
  next day (P1.1, see `test_real_vocab.test_forecast_payday_inflow_is_retained_income`).

## Thresholds (`inferences/thresholds.py`)

| Name | Value | Use |
|---|---|---|
| `BUFFER_MIN_EUR`, `BUFFER_ESSENTIALS_SHARE` | 50, 0.10 | buffer |
| `DISCRETIONARY_DAYS` | 60 | window for d and sigma |
| `FORECAST_DAILY_STAT` | `"mean"` | **differs from the spec (median)**, see below |
| `BAND_Z` | 1.28 | 80% band |
| `DANGER_BALANCE_EUR` | 50 | #20 |
| `UPCOMING_BILLS_DAYS` | 30 | #21 |
| `NO_PAYDAY_HORIZON_DAYS` | 30 | horizon when no payday was found |
| `DEFAULT_CYCLE_DAYS` | 30 | pay cycle when there is no last payday |
| `SEASONAL_WARN_RATIO` | 1.25 | #23 |

**Mean, not median (calibration).** On the real S-Bank data most days have no
spend, so the median daily spend is EUR 0 for many customers and the balance
never moved. The mean matches real monthly spend. Danger days rose from 17% to
23% of customers as a result. See `docs/calibration.md` #4 and
`handoff/inference-calibration.md`.

## When it is available

`inferences/availability.py` decides when each item is available. Tools return
`{"available": false, "reason"}` instead of a default.

| Item | Needs |
|---|---|
| `forecast.safe_to_spend_week`, `.safe_to_save_today`, `.end_of_month`, `.danger_days` | a balance **and** a detected payday |
| `forecast.upcoming_bills` | at least one bill due in 30 days |
| `forecast.surprise_fund` | surprise spend > 0 in the last 12 months |
| `forecast.seasonal` | a full year of history (ratio not None) |

## Where it is used

- **Gemini tools** (`coach/gemini/tools/read.py`):
  - `get_safe_to_spend` (#17, plus bills before payday)
  - `get_safe_to_save` (#18, #20)
  - `forecast_balance` (#19, #20, #21, #23)
- **Catalogue** (`coach/gemini/catalogue.py`): every forecast item can be read
  with `get_inference`.
  - `forecast.daily_path` can be charted: `get_chart` returns a line card of
    `expected` titled "Expected balance until payday".
- **Insights** (`coach/insights.py`): safe to spend, end of month and danger
  days rows in the Forecast section of the home screen.
- **Alerts** (`inferences/alerts.py`):
  - #20 danger days
  - #23 seasonal
  - #78 mortgage payment at risk (`daily_path[].low`)
  - #99 low balance now (`buffer`)
  - #102 big bill coming (`buffer`, `upcoming_bills`)
- **Goals and mortgage**: `goals.evaluate_goals` and the mortgage features
  take the forecast as input.
- **Frontend**:
  - The insight rows in `components/Insights.jsx` (section `forecast`).
  - Chart cards in chat (`components/Chart.jsx`).
  - The `before_after` card shows `safe_to_spend` (`components/Cards.jsx`).

## Known gaps and quirks

1. **There is no range band on the chart.** The spec asks for an
   "end-of-month line with range band", but `get_chart` and the chart card
   only carry `expected`; `low`/`high` are dropped. A band needs:
   - optional `low`/`high` per point in `ChartCard` (`coach/gemini/cards.py`)
     and in `CARD_SCHEMA` (`tools/declarations.py`);
   - a band-aware `Chart` spec in the catalogue;
   - an area between low and high in `Chart.jsx`.
2. **The no-payday fallback never shows.** Without a payday,
   `safe_to_spend_week` falls back to `balance - buffer`, but availability
   requires a payday, so tools report it as unavailable anyway.
3. **The salary is assumed to be monthly.** `_scheduled` repeats the salary
   with `DateOffset(months=1)`, whatever cycle was detected. Weekly or
   fortnightly pay would be off.
4. **The horizon is `max(month end, payday)`, not "until payday".**
   `daily_path` can run past payday. Danger days and safe to save cut it at
   `days_to_payday - 1`.
5. **d excludes bills by merchant.** Any spend at a bill's merchant is
   dropped from d, including one-off purchases there.
6. **Seasonal needs 12 full months.** Most customers in the sample data get
   `ratio: None`, so #23 is unavailable.
7. **There is no Forecast screen yet.** `context.md` P3.5 lists a Forecast
   section (safe to spend and save, end-of-month line with band, danger zone,
   bill timeline, surprise fund, seasonal banner). Today it only appears as
   insight rows and chat cards.
8. **The tests are thin.** There is no `test_forecast.py`. The forecast is
   covered by:
   - `inferences/tests/test_core.py::test_forecast_shape`
   - `inferences/tests/test_edge_cases.py`
   - `inferences/tests/test_real_vocab.py`
   - `coach/tests/test_insights.py`
   - the forecast alert tests in `test_alerts.py`

## Working on it

```bash
scripts/bin/check --backend-only                       # black, Django, pytest
cd backend && ../.venv/bin/python -m pytest -q inferences/tests/test_core.py -k forecast
cd backend && ../.venv/bin/python manage.py build_profiles  # rebuild cached profiles
```

- Profiles are cached in the Profile table. Rebuild after changing the maths,
  or the API keeps serving old numbers.
- Changing a threshold changes alert rates. Check `docs/calibration.md`, and
  use the `real-data-handoff` skill when touching real-data vocabulary.
- Formatting rules: max line length 88, run `black` before a PR, branch from
  `develop` (`lucas-forecasting` exists for this).