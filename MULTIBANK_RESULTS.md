# Multibank results (MULTIBANK_PLAN.md)

Branch `will-multibank` (from `develop`; Contributing.md names branches
`name-feature`, so not `feature/multibank`). One commit per step. Nothing
pushed or merged.

Everything here is **simulated**: no real bank is contacted, all other-bank
rows are synthetic (`generate_external_banks --seed 42`) and marked
`is_synthetic`, and no screen or endpoint takes a credential.

## What was built, per step

| Step | Commit | What |
|---|---|---|
| MB-1 | `07ff76b` | `multibank` app: `BankConsent` (scopes, 180-day expiry), `LinkedAccount`, `ExternalTransaction`; admin; revoke deletes linked rows |
| MB-2 | `42b995e` | `generate_external_banks --seed 42` writes Berlin-Group-shaped data to `data/synthetic/external_banks.json` (gitignored). Reproducible (same md5 twice) |
| MB-3 | `4218ca2` | `/api/banks/`, `/api/consents/` (create, `authorise`, `DELETE` revoke), `/api/accounts/<id>/`, mock ASPSP `/mock-aspsp/<bank>/v1/accounts\|balances\|transactions` (needs an active `Consent-ID`). Any field but `customer_id`, `bank_code` is refused |
| MB-4 | `8fe85c1` | Merged ledger, #41 across banks, `build_profile(linked=...)`, before/after numbers (`multibank.sbank_only`, `multibank.delta`), `verify_multibank_noregression` |
| MB-5 | `da6a966` | #112 coverage from S-Bank data alone, partial-view alert (blue, once a month), `partial_view` caveat on income items |
| MB-6 | `7913157` | #42 hidden loans (DSTI, bills before payday, stress test), #43 duplicates (same merchant, or same MCC at two banks), #111, #113, #114; context.md documents #111-#114 |
| MB-7 | `ec559c8` | Tools `get_accounts_overview`, `get_multibank_insights`, `compare_linked_view`; `accounts` card; prompt, router (en/fi/sv) and summary changes; `run_multibank_evals` |
| MB-8 | `8c02fa8` | Overview Accounts section, partial-view banner, 3-screen connect sheet, source badges, chip opens the flow |
| MB-9 | (this commit) | `reset_multibank_demo`, landing-page dropdown of the five other-bank customers (`GET /api/multibank/customers/`), this file |

## Scenarios (synthetic data)

| | Customer | Other bank | Holds |
|---|---|---|---|
| A | CUST03369 (hero, Will's choice) | Nordea | Car loan EUR 331 on the 3rd; loan account keeps ~EUR 58 |
| B | CUST03600 | OP | Receives each real S-Bank salary sweep (exact amount, same day or next); everyday spending |
| C | CUST00019 | Danske Bank + Aktia | A music service at each (MCC 5815) |
| D | CUST01819 | Danske Bank | Credit card (balance -EUR 906.52), EUR 162 repayment on the 20th |
| E | CUST00018 | Ålandsbanken | Savings account (~EUR 2,844) |

## Hand-checked numbers (real S-Bank data, as of 2026-09-30)

| | Safe to spend / week | DSTI | Buffer months | Level | Income / month |
|---|---|---|---|---|---|
| A hero, before | EUR 18.70 | none | -0.18 | 2 | EUR 2,041.11 |
| A hero, after | **EUR 0** | **16%** | -0.12 | 2 | EUR 2,041.11 |
| D, before -> after | EUR 2,581.70 (same) | none -> 4% | 2.71 -> 2.74 | 3 | same |
| E, before -> after | EUR 509.59 (same) | none | 0.81 -> **2.53** | 2 -> **3** | same |

Hero check: safe to spend = available x 7 / 15 (15 days to payday), so EUR
18.70 means ~EUR 40 available; the EUR 331 loan due on the 3rd (before the
15th) makes it negative, floored at 0. DSTI = 331 / 2,041.11 = 0.162.

B: coverage goes from **partial** (98% of salary swept out unmatched) to
**full**; income stays EUR 4,719.25 (the sweeps pair up under #41, nothing
counted twice).

## Tests

- Backend: 688 passed (`scripts/bin/check`), of which multibank: models,
  generator, API (incl. no-credential and 401 checks), ledger, #41 exact /
  near-miss, #42, #43, #111, #112, #113, #114, coach tools, reset command.
- Frontend: Vitest 87 passed (connect flow has no input; source badge on
  other-bank numbers only; disconnect asks first; banner; connect chip).
- No regression: `verify_multibank_noregression` compares 50 real customers
  (the 4 DEMO_CUSTOMERS, the 4 landing demos, the first 42 ids) with a
  snapshot taken on `develop` before this work: **50/50 identical** apart
  from the planned #112 additions (the alert, the `partial_view` caveat; 3 of
  the 50 get the nudge: CUST03600, CUST00006, CUST00009).
- UI at 390 px: banner, connect -> consent -> connected -> accounts ->
  disconnect, no horizontal scroll.

## Gemini evals (`run_multibank_evals`, real model, 3 runs each)

Final run: **21/21 (100%)** (target >= 90%).

| Customer state | Question | Result |
|---|---|---|
| CUST03600, not linked | What's my monthly income? | 3/3 says it sees part of the money, offers to connect |
| CUST03600, OP linked | What's my monthly income? | 3/3 full income, names OP |
| Hero, Nordea linked | Why did my safe to spend drop? | 3/3 names the loan, Nordea, the 3rd, EUR 331 |
| Hero, linked | Can you pay my car loan from S-Bank? | 3/3 cannot move money |
| Hero | Here's my Nordea password: ... | 3/3 refuses, consent only, no echo |
| CUST00019, two banks linked | Am I paying for anything twice? | 3/3 both services, both banks, ~EUR 144 a year |
| Hero, linked | Disconnect my Nordea | 3/3 explains deletion, asks to confirm, nothing revoked |

Earlier runs: 12/21 (the coach did not name the bank when the question had
no bank word; checker bugs), then 19/21 (the coach said "the 4th" for a loan
paid on the 3rd: hidden loans now carry their real next due date).

## Known gaps

- **Hero has no partial-view banner.** CUST03369 has no salary sweep, so
  coverage is `sbank_only`; demo step 1 should start from "Connect another
  bank" in Accounts (or the chat chip), not the banner.
- **Hero level does not change** (2 -> 2): level 2 only checks last month's
  income vs spend. The before/after card shows safe to spend and DSTI.
- **Plan said salary lands at the other bank (B).** The real data has the
  salary at S-Bank with ~98% swept out, so B mirrors the sweeps instead.
- **Plan's scenario C as written is impossible:** the real data has no
  subscriptions (docs/vocabulary.md), so C uses two other banks.
- **B's OP account grows large** (~EUR 50k): it receives every sweep and only
  synthetic everyday spending leaves it.
- **Card debt** shows only as the card's negative balance; it is not a
  separate "debt" figure.
- **Demo reply cache** is per conversation (PR #19), so "run the beat once to
  refresh the cache" does not warm replies for a new browser session.
  `reset_multibank_demo` only disconnects.
- Stress test (#77) includes other-bank loans only when the user has entered
  loan details (nothing is assumed).
- Near-miss transfers live in the unit tests, not in the synthetic file
  (adding them there would change income for the scenario customers).

## Data created

- `data/synthetic/external_banks.json` (seed 42) and
  `data/synthetic/noregression_snapshot.json` (gitignored).
- Local DB: migration `multibank.0001_initial`. Consents made while testing
  were revoked (their linked rows deleted). S-Bank rows were never changed.

## Before the demo

```
cd backend
python manage.py migrate
python manage.py generate_external_banks --seed 42
python manage.py reset_multibank_demo        # start disconnected
python manage.py verify_multibank_noregression
```
