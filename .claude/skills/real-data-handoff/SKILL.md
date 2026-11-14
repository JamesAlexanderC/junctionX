---
name: real-data-handoff
description: Use when working on handoff/real-data-and-demo-customers.md, loading or profiling the S-Bank CSVs, changing inferences/thresholds.py vocabulary, picking DEMO_CUSTOMERS, running load_data/build_profiles, or fitting the mortgage readiness model (#34/#35). Runs the verify_handoff gate before and after every change.
---

# Real-data handoff loop

The handoff has six steps. `manage.py verify_handoff` checks each one and
exits non-zero if any selected step fails. Never call a step done without a
PASS line from it.

## Loop for every step

1. `cd backend && ../.venv/bin/python manage.py verify_handoff --step N`
   and read the FAIL detail: it names exactly what is missing.
2. Write the failing test first (`inferences/tests/` for pure maths,
   `coach/tests/` for commands, DB and API). Run it, see it fail.
3. Implement the smallest change, then run `../.venv/bin/python -m pytest -q`.
4. Re-run `verify_handoff --step N` and continue only on PASS.
5. `black` the changed files (max line 88), commit one step per commit on
   the `<name>-feature` branch. Never merge without explicit direction.

## Fixed decisions (do not re-ask)

- `salary_sweep` is neutral. Budgeting uses `income.retained_income`;
  `coverage > 0.5` means `partial_view`, excluded from peer benchmarks.
- `investment_deposit` is Saver, `investment_withdrawal` negative Saver.
- Transportation is essential only for MCC 4111/4112/4131/5541/5542/7523 or
  blank; taxis (4121) are other spending.
- Reference date = max(tx_date) (`services.today()`), never the wall clock.
- `tx_timestamp` is SAS `%d%b%y:%H:%M:%S`; parsing fails above 1% bad rows.
- Loan/fee/gambling labels match no real rows; those alerts run on the
  synthetic credit register and injected events only.
- Demo customers: you pick from the `rank_demo_customers` shortlist; prefer
  coverage < 0.3, plus one high-sweep customer for the multi-bank demo.

## Step 6: mortgage model rules

Build it only after steps 1 to 5 pass. Features from the 6 months before each
application, at most 4 to 6, standardised, logistic regression with L2,
`class_weight="balanced"`, fixed `random_state`, 5-fold stratified CV AUC.
Write `docs/mortgage_model.json` as `{cv_auc, mode, features, ...}`:
`mode = "model"` if AUC >= 0.70, otherwise `"percentile_fallback"` (score =
mean percentile of the user's features within approved applicants; the
regression only ranks which gaps matter). Always report the AUC.

## Big-file hygiene

`data/tx_junction_transactions.csv` is 363 MB: read it with
`csvdata.iter_transactions` (chunked), never `pd.read_csv` whole. A full scan
takes about a minute. Run one-off exploration scripts from the scratchpad
with `python -I`.
