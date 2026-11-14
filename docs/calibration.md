# Inference calibration on real S-Bank customers

Sample: 200 random customers (seed 42) from `tx_junction_transactions.csv`,
`today = 2026-09-30` (last day of the data), each run through
`inferences.profile.build_profile` and `inferences.alerts.run_all_alerts`.
No peer table or mortgage model was passed, so benchmarks (#36, #37) and
readiness (#35) are unavailable in this run by construction. Vocabulary
behind the changes: `docs/vocabulary.md`.

Runs: **before** = code as delivered by waves 1 and 2; **vocab** = real
vocabulary and pseudo merchants only; **final** = all changes below.

## Results

| Metric | before | vocab | final |
|---|---|---|---|
| Errors | 0 | 0 | 0 |
| Payday found (#1) | 83.5% | 98% | 98% |
| Regular bills per customer (#4), mean | 0.01 | 0.92 | 0.92 |
| Subscriptions per customer (#5) | 0 | 0 | 0 (none exist in the data) |
| Essentials share, mean | 59.4% | 66.5% | 66.5% |
| Leaky share, mean | 2.6% | 3.0% | 3.0% |
| Saver share, mean | 0.0% | 3.8% | 3.8% |
| "Other" share, mean | 36.3% | 24.6% | 24.6% |
| Safe to spend this week (#17), median EUR | 3,209 | 2,393 | 2,393 |
| Safe to save today (#18), median EUR | 4,730 | 4,415 | 4,078 |
| Customers with danger days (#20) | 15.5% | 17% | 23% |
| Level 0 / 1 / 2 / 3 | 198 / 1 / 0 / 1 | 22 / 60 / 29 / 89 | 22 / 60 / 29 / 89 |
| Spender types | 52% Payday Splurger, 48% Weekend Treater | 47% / 51% | 35% Payday Splurger, 32% Balanced, 24% Weekend Treater, 8% Steady Planner, 2% Night Owl |
| Alerts per customer, median | 5 | 4 | 2 |

### Alert firing rate (share of customers)

| Alert | before | vocab | final |
|---|---|---|---|
| #20 danger days | 15.5% | 17% | 23% |
| #23 seasonal | 12% | 13.5% | 13.5% |
| #38 unusual charge | **98%** | 69% | 41.5% |
| #40 category spike | **80%** | 80% | 40% |
| #85 overdraft | 18% | 18% | 18% |
| #87 income dropped | 0.5% | 1% | 1% |
| #88 spending pace | 38% | 32.5% | 32.5% |
| #89 lifestyle creep | 3% | 2.5% | 2.5% |
| #93 annual bill | 5.5% | 5.5% | 5.5% |
| #94 savings withdrawn | 0% | 0.5% | 0.5% |
| #99 low balance | 3.5% | 3.5% | 3.5% |
| #101 bill went up | 24% | 25.5% | 6% |
| #102 big bill coming | 0.5% | 1.5% | 1.5% |

Loan (#76-#84), fee (#86), cash (#96), gambling (#98) and subscription
(#6, #90-#92) alerts never fire: the data has no such transactions.

### Availability on the sample (final)

Share of customers whose data supports each item (`profile["availability"]`):
balance, income, baskets, habits, levels, seasonal, category cut 100%;
payday and forecast 98%; payday splurge 97%; surprise fund 94.5%; bills and
upcoming bills 91%; detected goals 89.5%; recommended goal 89%; alerts 78.5%;
habit translation 75.5%; easiest next step 40.5%; Saver and goal date 31%;
subscriptions, subscription savings, possibly unused, loan burden, stress
test, multibank 0%; readiness and benchmarks 0% here (no model / peer table
passed).

## Changes and why

1. **Pseudo merchants** (`common.fill_pseudo_merchants`). Salary, housing
   and utilities rows have no `merchant_id`; they all grouped under `""`, so
   salary mixed with other income and rent with utilities. They now get
   `type:<transaction_type>` with display names in
   `thresholds.PSEUDO_MERCHANT_NAMES`. Purchases without a merchant stay
   empty and have no merchant history in #38.
2. **Real vocabulary** in `thresholds.py` (single source; `alert_thresholds`
   imports it): Saver = `investment_deposit`, withdrawals =
   `investment_withdrawal`, `salary_sweep` = own transfer kept out of spend
   and baskets. #94 and #95 use the savings types only.
3. **Essentials by MCC** for Transportation: public transport 4111, fuel
   5541/5542 and parking 7523 are essential; taxis 4121 are not
   (`ESSENTIAL_MCCS`, `common.essential_mask`).
4. **Forecast daily spend = mean** (`FORECAST_DAILY_STAT`). The doc's median
   was EUR 0 for most customers (most days have no spend), so the balance
   never moved. Danger days rose from 17% to 23% as a result.
5. **#38 unusual charge**: robust z > 3.5 **and** > 3 x the merchant median
   **and** > EUR 50 above it (`UNUSUAL_MIN_MULT`, `UNUSUAL_MIN_EXCESS_EUR`).
   The doc test (89 vs median 20) still flags.
6. **#40 category spike**: needs spend in each of the previous 3 months
   (`SPIKE_REQUIRE_FULL_HISTORY`); ratio 1.5 and EUR 20 kept so the doc test
   holds.
7. **#101 bill went up**: only stable payments (CV < 0.20 over the previous
   three). Restaurants visited about monthly were being treated as bills.
8. **#16 spender type**: scores measure excess over the expected value
   (weekend 2/7, payday ratio 1.0). With value / threshold an average
   customer scored ~0.7 and nobody was ever a Steady Planner. A new label
   **Balanced** is used when no trait stands out (all scores < 0.5) and
   saving is under 10%, so no trait is claimed without evidence.
9. **#6 possibly unused**: while chat opens are not tracked
   (`opened_in_chat=None`) only a price rise counts as evidence.
10. **No placeholders**: empty-data habits return `None` labels, balance is
    `None` without data, Level 2 needs income in the month, the #59 home goal
    no longer guesses a price (target `None`, `needs: "target_price"`; the
    `TYPICAL_HOME_PRICE` table is gone), and every item has an availability
    flag (`inferences/availability.py`).

## Left for a human

- Mentor answers to the questions at the end of `docs/vocabulary.md`.
- #38 still fires for ~40% of customers and #88 for ~33%. The synthetic
  amounts are wide and many customers do overspend (spend / income median
  0.88, p90 1.24). Re-check on the chosen demo customers before the demo.
- Re-run with the fitted mortgage model and peer table from the data owner's
  build step to calibrate #35 to #37.
- **#1 payday CV window (scan of all 5,100 customers, as of 2026-09-30).**
  Payday is found for 5,009 (98.2%). Of the 91 without one, 77 fail the
  amount check (CV >= 0.15, measured over all salary history) and 14 have no
  income source in 3 of the last 4 months. Measuring the CV over the 4-month
  window only would find 33 more and lose 16 (net +17, 0.3%), and never
  picks a different income source. Example: CUST05085 is paid every month
  (Jun to Sep: 903, 821, 1,048, 922, window CV ~0.09) but has a two-year CV
  of 0.22, so safe-to-spend and the forecast are unavailable. The missing
  payday reason now says which check failed (`income.payday.reason`).
