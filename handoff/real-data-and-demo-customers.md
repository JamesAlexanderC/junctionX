# Handoff: real S-Bank data, category mapping and demo customers

## What is missing
- The four S-Bank CSVs (Junction-2026-S-pankki repo) are not in this checkout,
  so nothing on `jamie-implementation` has run against real data. All
  inferences are built and tested against the hand-made "Test Aino" fixture
  and `shared/fixtures/profile_demo.json`.
- `inferences/thresholds.py` guesses at `category`, `transaction_type` and MCC
  values (ESSENTIAL set, own-account transfer types, savings/investment,
  loan/credit, fee, gambling). These are marked `TODO confirm`.
- Demo customers (`settings.DEMO_CUSTOMERS`) are not picked yet.

## Why it wasn't done here
Needs the Git LFS download (~346 MB) and answers from the S-Bank data
scientist about what the category and transaction_type values mean. Neither
can be done well from this session.

## Next steps
1. Download the data into `data/` (gitignored), with Git LFS:
   `git lfs install && git clone <S-pankki repo> && git lfs pull`, then copy
   the four CSVs to `data/`. Check `head -c 200 data/tx_junction_transactions.csv`
   shows CSV rows, not a `version https://git-lfs...` pointer.
2. `cd backend && ../.venv/bin/python manage.py explore_data` (writes
   `docs/data_profile.md`, P1.1). Confirm the sign convention of
   `tx_amount_eur`.
3. Ask the mentors which values mark: savings/investment transfers, own-account
   transfers, loan and credit-card payments, fees. Update `thresholds.py` and
   remove the TODOs. If loan payments exist, alerts #76 to #84 switch on.
4. `manage.py rank_demo_customers`, pick 3 to 5 (payday splurger, secret saver,
   nearly mortgage-ready, multi-account), set `DEMO_CUSTOMERS=` in `.env`.
5. `manage.py load_data && manage.py build_profiles`, then retune thresholds
   (EUR 25 leaky, CVs, etc.) on those customers.
6. Fit the mortgage readiness model (#34/#35) on the real mortgage files and
   check cross-validated AUC.
