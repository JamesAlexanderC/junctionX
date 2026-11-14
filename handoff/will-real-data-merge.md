# Merging `will-real-data` with `jamie-implementation`

For Will. `will-real-data` (up to `342ebb4`) is already merged into
`jamie-implementation` (merge commits `bab2842` and `e2f601b`). Nothing of
yours was dropped, and all your tests still exist and pass.

## If you have no new commits since `342ebb4`

Your branch fast-forwards with no conflicts:

```
git fetch origin
git switch will-real-data
git merge --ff-only origin/jamie-implementation
```

Or just carry on from `jamie-implementation`. Your branch has nothing it
lacks.

## If you made new commits since `342ebb4`

```
git fetch origin
git switch will-real-data
git merge origin/jamie-implementation
```

Expect conflicts only in files you touched again. Resolve them with the
rules we used for the first merge:

| Area | Keep |
|---|---|
| Vocabulary (`inferences/thresholds.py`, `common.py`) | Your names: `NEUTRAL_TRANSFER_TYPES`, `SALARY_TYPES`, `SAVER_DEPOSIT/WITHDRAWAL/_TYPES`, `ESSENTIAL_MCCS_BY_CATEGORY`, `PARTIAL_VIEW_COVERAGE`, your `essential_mask` / `saver_mask` / `neutral_mask`. `SWEEP_TYPES`, `SAVER_WITHDRAW_TYPES` and `ESSENTIAL_MCCS` are gone; don't bring them back. |
| Calibration constants | Ours: merchant stand-ins (`type:salary` etc.), `FORECAST_DAILY_STAT` (mean), `UNUSUAL_MIN_MULT`, `UNUSUAL_MIN_EXCESS_EUR`, `SPIKE_REQUIRE_FULL_HISTORY`. Reasons are in `docs/calibration.md`. |
| Availability | `inferences/availability.py`. Every profile has `availability[item] = {available, reason, inferences}`, and `/api/insights` plus the Gemini tools only show available items. Report a missing signal as unavailable, never as a default value. |
| #58 travel goal | Your `detected_goals.detect_travel_goal` (category == travel) is the only implementation. `goals.py` wraps it. |
| CSV loading (`coach/management/csvdata.py`) | One parser: `parse_timestamp` (SAS, ISO fallback, naive). `parse_timestamps` is the strict version, raising above 1% bad rows. |
| Loading into the DB | `load_data` (COPY, all 5,100 customers, about 3 min) followed by `build_artifacts` (peer table and mortgage model, stored in `ComputedArtifact`). Migration `0002_real_data`. |
| Reference date | `services.as_of_date()`, which defaults to max(tx_date) = 2026-09-30 and can be overridden with `AS_OF_DATE`. `services.today()` returns it. |
| `verify_handoff` | Kept. Step 6 now reads the model that `build_artifacts` stored, not `docs/mortgage_model.json`. |
| Tests | Plain `pytest` runs on SQLite. Set `USE_SQLITE=0` to force Postgres. |

Before you push, check the merge:

```
scripts/bin/check
cd backend && ../.venv/bin/python manage.py verify_handoff
```

Steps 1, 2, 3 and 6 pass now (AUC 0.73). Steps 4 and 5 wait for
`DEMO_CUSTOMERS`.

## Decisions made while merging (please sanity-check)

- **Transportation with no MCC counts as essential.** Your rule and your test;
  the calibration had proposed non-essential. There's no evidence either way,
  so it's on the mentor list.
- **Saver is net of withdrawals**, in both baskets and the demo-customer
  ranking.
- **`vehicle` is no longer an essential category.** Your Test Aino uses a
  dentist bill as the Surprise.

## The team rule this conflicts with

James's rule is binding: **no demo, mock, synthetic or injected data at
runtime.** Saldo is a chatbot over real inferences. If the data doesn't
support an insight, it says so. Three things in
`.claude/skills/real-data-handoff/SKILL.md` need updating (I left your file
untouched):

1. "Loan/fee/gambling labels match no real rows; those alerts run on the
   synthetic credit register and injected events only." These alerts are now
   reported unavailable. Please drop the synthetic register and injected
   events plan.
2. "...plus one high-sweep customer for the multi-bank demo." A mock second
   bank would be synthetic. `rank_demo_customers` still lists the high-sweep
   customer, labelled "partial view", for the story. The helpers
   `multibank.relabel_account_as_mock_bank` and `mock_second_account` exist
   but nothing calls them; they are likely to be deleted.
3. Step 6 says "run fit_mortgage_model". That command doesn't exist; it's
   `build_artifacts`.

## Still open on the handoff

- Pick 3 to 5 `DEMO_CUSTOMERS` from `manage.py rank_demo_customers` (steps 4
  and 5).
- Mentor questions: the end of `docs/vocabulary.md`.
- Inference issues seen on real customers. CUST00002 sits at level 0 because
  no regular bill is detected. Baskets fall back on an empty current month.
  The #19 band collapses on the last day of the month. The #58 pot is
  EUR 1,113 a month for CUST00037.
