# S-Bank data vocabulary (P1.1 findings)

Profiled from `tx_junction_transactions.csv` (Junction-2026-S-pankki), read in
chunks with `utf-8-sig`. Evidence counts are rows over the whole file. Values
marked **unconfirmed** come from the data alone: ask the S-Bank data scientist.

## Shape

| Fact | Value |
|---|---|
| Rows | 3,626,755 |
| Customers | 5,100 (all appear in `tx_customers_junction.csv`) |
| Date range | 2024-10-01 to 2026-09-30 (24 full months for every customer) |
| Transactions per customer | median 700 (min 148, max 1,543) |
| Accounts per customer | **1 for every customer** (no multi-account customers) |
| Sign convention | inflow `tx_amount_eur > 0`, outflow `< 0` (confirmed: salary always +, purchases always -) |
| `balance_after_eur` chain | consistent for 99.86% of rows (prev balance + amount) |
| Negative balances | 89,398 rows, 3,526 customers ever; 800 in the last 30 days |
| Latest balance | median EUR 6,161 (p5 835, p95 29,563); 37 customers below 0 |
| `tx_timestamp` format | SAS datetime `03OCT24:09:04:04` -> `format="%d%b%y:%H:%M:%S"`; date part always equals `tx_date` |
| Hours | 05:00 to 23:59 only; no transactions between 00:00 and 04:59 |
| Zero-amount rows | none |

## Categories and transaction types

Every category maps to exactly one `transaction_type`. `merchant_id` and
`mcc_code` are only set on `purchase` rows (and even then ~3% are empty).

| category | transaction_type | sign | rows | median EUR | merchants | basket |
|---|---|---|---|---|---|---|
| Salary | salary | in | 121,725 | +3,147.63 | none | income (#1, #2) |
| Other Income | other_income | in | 6,299 | +2,154.23 | none | income (#2), irregular |
| Invest Withdraw | investment_withdrawal | in | 532 | +1,341.19 | none | Saver withdrawn (#94), not income |
| Housing | housing_payment | out | 112,903 | -1,047.78 | none | Essentials, regular bill (#4) |
| Utilities | utilities_payment | out | 342,728 | -50.35 | none | Essentials (not a #4 bill: ~3 a month, CV ~0.38) |
| Groceries | purchase | out | 868,519 | -63.91 | 81 | Essentials |
| Health | purchase | out | 151,912 | -51.84 | 56 | Essentials (Surprises if outlier #8) |
| Transportation | purchase | out | 626,930 | -41.02 | 66 | split by MCC, see below |
| Restaurants | purchase | out | 759,280 | -23.13 | 91 | Leaky when < EUR 25 |
| Entertainment | purchase | out | 302,691 | -35.09 | 56 | non-essential |
| Lifestyle | purchase | out | 110,916 | -96.52 | 66 | non-essential |
| Home & Tech | purchase | out | 115,086 | -105.77 | 61 | non-essential |
| Travel | purchase | out | 65,377 | -125.72 | 46 | non-essential (#58 travel) |
| Invest Deposit | investment_deposit | out | 35,668 | -296.44 | none | **Saver (#75)** |
| Salary Sweep | salary_sweep | out | 6,189 | -3,877.26 | none | own-account transfer (excluded from spend) |

`prepare()` lower-cases categories, so the code uses `housing`, `utilities`,
`groceries`, `health`, `transportation`, `restaurants`, `entertainment`,
`lifestyle`, `home & tech`, `travel`, `invest deposit`, `invest withdraw`,
`salary`, `other income`, `salary sweep`.

### Spend share (all customers, excluding sweeps and investments)

Housing 34.4%, Groceries 16.9%, Restaurants 8.6%, Transportation 8.0%,
Home & Tech 7.0%, Lifestyle 6.3%, Utilities 5.5%, Entertainment 5.1%,
Travel 4.4%, Health 3.8%. Monthly spend / income: median 0.88 (p10 0.48,
p90 1.24).

## Patterns behind the types

| type | customers | per month | amount CV (median) | day of month |
|---|---|---|---|---|
| salary | 5,100 | exactly 1 | 0.079 | 15th for 5,002 customers (modal share ~79%); other months land on the last day of the month. Weekends are **not** moved. |
| housing_payment | 4,882 | exactly 1 | 0.029 | days 1 to 8 |
| utilities_payment | 4,922 | usually 3 | 0.381 | spread over the month |
| investment_deposit | 1,500 | exactly 1 | 0.080 | days 16 to 20 or 31st, i.e. right after payday |
| salary_sweep | 264 | exactly 1 | 0.083 | the day after salary; moves ~85 to 90% of the salary out |
| other_income | 2,401 | 1 to 4, irregular | 0.50 | anywhere |
| investment_withdrawal | 435 | rare | 0.33 | anywhere |

- **Salary has no merchant_id.** Payday (#1) must group inflows by
  `transaction_type` (or a pseudo merchant) when `merchant_id` is empty;
  grouping on the empty string mixes salary with other_income.
- **Housing and utilities have no merchant_id** either. Bill detection (#4)
  needs the same pseudo-merchant fallback, or rent is never found.
- **No subscriptions exist in the data**: no customer pays the same merchant
  the same amount three or more times. #5, #6, #25, #90 to #92 and #101
  (subscriptions part) stay silent on real customers. Demo stories need
  synthetic subscriptions (clearly labelled) if those moments are shown.
- **Salary sweep** looks like an own-account (or other-bank) transfer: one
  outflow the day after salary, no matching inflow in the data (every
  customer has one account). Treat as own transfer, and as the natural
  multi-bank (#41 to #43) demo story: "your salary goes on to another bank".
- **Own-account matching (#41)** finds nothing: no customer has two accounts.

## MCC codes (all 37, by rows)

Every MCC belongs to exactly one category. Amounts do not vary by MCC within a
category (synthetic data), so MCCs only matter for sub-typing.

| MCC | rows | category | meaning |
|---|---|---|---|
| (empty) | 786,668 | Utilities, Salary, Housing, Transportation, ... | non-purchase rows plus ~3% of purchases |
| 5411 | 709,071 | Groceries | grocery stores |
| 5812 | 438,738 | Restaurants | restaurants |
| 5814 | 254,588 | Restaurants | fast food |
| 5542 | 133,716 | Transportation | automated fuel |
| 7523 | 133,629 | Transportation | parking |
| 4111 | 112,751 | Transportation | commuter / public transport |
| 5541 | 112,293 | Transportation | service stations |
| 5499 | 96,321 | Groceries | misc food stores |
| 5912 | 82,258 | Health | pharmacies |
| 7922 | 79,728 | Entertainment | theatre / tickets |
| 7999 | 70,140 | Entertainment | recreation services |
| 4121 | 59,201 | Transportation | taxis |
| 7832 | 58,146 | Entertainment | cinemas |
| 7991 | 54,977 | Entertainment | tourist attractions |
| 5813 | 47,003 | Restaurants | bars |
| 5200 | 44,838 | Home & Tech | home supply |
| 5941 | 35,864 | Lifestyle | sporting goods |
| 8011 | 33,281 | Health | doctors |
| 5422 | 30,861 | Groceries | meat shops |
| 7996 | 27,584 | Entertainment | amusement parks |
| 5651 | 25,815 | Lifestyle | clothing |
| 5732 | 25,485 | Home & Tech | electronics |
| 5451 | 19,254 | Groceries | dairy |
| 5251 | 19,170 | Home & Tech | hardware |
| 4722 | 18,023 | Travel | travel agencies |
| 4511 | 15,779 | Travel | airlines |
| 7011 | 15,391 | Travel | hotels |
| 5999 | 15,132 | Lifestyle | misc retail |
| 5712 | 13,996 | Home & Tech | furniture |
| 8099 | 12,513 | Health | health services |
| 5691 | 11,869 | Lifestyle | clothing |
| 5942 | 7,918 | Lifestyle | books |
| 5945 | 7,605 | Lifestyle | toys / games |
| 7512 | 6,983 | Travel | car rental |
| 8021 | 5,524 | Health | dentists |
| 5734 | 4,642 | Home & Tech | software |

### Transportation split (proposed)

| MCC | basket |
|---|---|
| 4111 public transport | Essentials (doc lists public transport as essential) |
| 5541, 5542 fuel; 7523 parking | Essentials (unconfirmed: commuting by car) |
| 4121 taxis | non-essential (doc's own leaky example) |
| empty | non-essential (unconfirmed) |

## Signals the alerts look for

| Signal | Found? | Evidence | Effect |
|---|---|---|---|
| Savings / investment | yes | `investment_deposit` (1,500 customers, monthly) | Saver (#75), #56, levels 3 and 6 |
| Savings withdrawn | yes | `investment_withdrawal` (435 customers) | #94 |
| Own-account transfer | partly | `salary_sweep` (264 customers) | excluded from spend; multi-bank story |
| Loan / mortgage payments | **no** | no loan category, type or MCC 6012/6051/6141 | #76 to #84 silent unless the user enters loan details (#77, #82) |
| Credit-card bills | **no** | none | - |
| Fees / late charges | **no** | no fee category, no MCC 7322 | #86 silent |
| ATM cash (MCC 6011) | **no** | none | #96 silent |
| Gambling (MCC 7995) | **no** | none | #98 silent |
| Subscriptions | **no** | no repeated identical merchant amounts | #5, #6, #90 to #92 silent |
| Overdraft | yes | 800 customers below 0 in the last 30 days | #85 fires often; tune or soften |
| Travel MCCs for #58 | yes | 4511, 4722, 7011, 7512 | the doc's ranges 3000-3350 / 3501-3999 never occur; use these |

## Mortgage files

- 200 applicants linked to customers: 150 approved, 50 rejected
  (insufficient_collateral 34, insufficient_income 8, insufficient_equity 6,
  existing_debt 2). Enough for a logistic regression (#34) but small; check
  cross-validated AUC.
- `mtg_negotiation_history.csv`: 3,452 events (`application_created`,
  `customer_contact`, ...), timestamps in the same SAS format.

## Ask the S-Bank mentors

1. Is `salary_sweep` a transfer to the customer's own account elsewhere?
2. Are fuel and parking essential for this exercise, or everyday spending?
3. Do any customers have loans or credit cards in data we were not given?
4. Is the 15th / month-end salary day a modelling choice we can rely on?
5. Are negative balances real overdrafts or an artefact of the generator?
