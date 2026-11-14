# Handoff: real S-Bank data, category mapping and demo customers

**Implemented on `jamie-implementation`** (2026-11-14). A teammate's branch
`will-real-data` covers the same loading work; the data-loading changes here
are kept in their own commit to make reconciling easy.

## What was done
- `coach/management/csvdata.py` reads the CSVs from `DATA_DIR` (`.env`,
  default `data/dataset/Junction-2026-S-pankki`) with `utf-8-sig`, parses the
  SAS timestamps (`03OCT24:09:04:04`, `%d%b%y:%H:%M:%S`) as naive local time,
  and gives every row a stable `tx_id` (`<customer>-r<row number>`).
- `manage.py load_data` loads **all** 5,100 customers, 3,626,755 transactions
  (Postgres COPY) and both mortgage files (200 outcomes, 3,452 events, with
  their real columns: `final_decision`, `rejection_reason`, prices, LTV, ...)
  in about 3 minutes. `--replace` reloads, `--customers` loads a subset.
- `manage.py build_artifacts` (run by `load_data`) computes the #36/#37 peer
  table and fits the #34 mortgage readiness model on the 200 real applicants
  (application date = first `application_created` event): logistic
  regression, cross-validated AUC 0.73. About 3 minutes.
- Profiles are built on demand from the DB (`coach/services.get_profile`) as
  of `AS_OF_DATE` (default: last transaction date, 2026-09-30) and cached;
  they rebuild when the inference code, the as-of date, goals or loan details
  change.
- Category, transaction_type and MCC meanings are in `docs/vocabulary.md`;
  `inferences/thresholds.py` uses them (calibration by agent E,
  `docs/calibration.md`).
- `rank_demo_customers` works on the real data. The multi-account story was
  dropped: every customer has exactly one account.
- All runtime demo data was removed (no `demo-aino`, no fixture fallback, no
  canned chat replies).

## Still needs a human
Ask the S-Bank mentors (from `docs/vocabulary.md`):
1. Is `salary_sweep` a transfer to the customer's own account elsewhere?
2. Are fuel and parking essential for this exercise, or everyday spending?
3. Do any customers have loans or credit cards in data we were not given?
   (Without them alerts #76 to #84 only work after "Add loan details".)
4. Is the 15th / month-end salary day a modelling choice we can rely on?
5. Are negative balances real overdrafts or an artefact of the generator?

Then pick the demo customers for the pitch from `rank_demo_customers`.
