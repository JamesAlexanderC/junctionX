# Handoff: calibrate core inferences on the real S-Bank data

> **Implemented on jamie-implementation.** Real vocabulary filled in
> `thresholds.py` (see `docs/vocabulary.md`); calibrated on 200 real
> customers (`docs/calibration.md`): pseudo merchants for salary / housing /
> utilities (payday found 83.5% -> 98%, rent detected as a bill), Transportation
> split by MCC, salary sweeps kept out of the baskets, forecast uses the
> **mean** daily spend (median was EUR 0 for most customers), #6 only flags
> on a price rise until chat opens are tracked, spender scores measure excess
> over the expected value, and every profile item now carries an
> `availability` flag (`inferences/availability.py`) so the app shows only
> insights the data supports. Still needs a human: mentor answers to the
> questions at the end of `docs/vocabulary.md`, and re-tuning on the final
> demo customers once they are picked.

## What is missing
The core inferences (#1-#33, `backend/inferences/`) are built and tested on
the hand-made "Test Aino" customer only. The real CSVs are not in the repo
(Git LFS, `data/` is gitignored), so P1.1's data profiling has not been run and
none of the data vocabulary is confirmed.

## Why it is out of scope here
It needs the real `tx_junction_transactions.csv` (~346 MB via Git LFS) and
answers from the S-Bank data scientist about category / transaction_type
values. Guessing them would make every basket and income number wrong.

## What exists
- `inferences/thresholds.py`: every set and threshold; guesses are marked
  `TODO confirm with S-Bank data`:
  `OWN_TRANSFER_TYPES`, `ESSENTIAL_CATEGORIES` (incl. `vehicle`),
  `INVESTMENT_MCCS`, `LOAN_CATEGORIES`, `LOAN_MCCS`.
- `SURPRISE_NO_HISTORY_MIN_EUR = 100`: our own rule for #8 when a category has
  no earlier payment (the doc gives none).
- `common.prepare()` lower-cases `category`, so put lower-case values in the
  sets.
- Own-account transfers are found by type and by #41 matching
  (`common.matched_own_transfers`, only when a customer has 2+ accounts).

## Known judgement calls to revisit with real data
- #19/#20 use the doc's *median* daily discretionary spend. With weekly
  groceries the median badly underestimates spend (Aino: d = 3.50 a day while
  the mean is ~13). If forecasts look too rosy, switch to the mean in
  `forecast.discretionary_stats`.
- Basket `other` (non-essential, EUR 25 or more) is a fifth key in
  `baskets.totals/shares`; the four doc baskets do not cover it.
- `income.possibly_unused` (#6) treats every subscription as "never opened in
  chat" until chat opens are tracked, so it flags often. Pass
  `opened_in_chat` from the chat log once Person 2 stores it.
- Test Aino: the doc's B = 500 and lowest balance 445 cannot both hold with
  a running balance; the fixture keeps 445 (see `tests/fixtures.py`).

## Next steps
1. `git lfs pull` the S-Bank repo into `data/`, run P1.1's exploration and
   save `docs/data_profile.md`.
2. Fill the TODO sets in `thresholds.py`; check the sign convention of
   `tx_amount_eur` (code assumes inflow > 0).
3. Run `compute_income` / `compute_baskets` on the 3-5 demo customers and tune
   thresholds until the stories (payday splurger, secret saver, ...) show.
