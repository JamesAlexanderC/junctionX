# Forecast (#17–#23): live test results and fixes

Tested on Sat 14 Nov 2026 against http://localhost:5173 (data `as_of` = 2026-09-30).
Customers: CUST03369 (tight week), CUST00025, CUST01819 (comfortable), CUST05085 (no payday).
The spec is HANDOFF.md §6.1. Your notes are `docs/forecast-context.md` (the "Forecasting (#17 to #23): context" file).

**For Claude Code:** read this, then work through the Fixes section in order. Use TDD: write the failing test first. One commit per fix, `fix(FC-n): ...`. Rebuild profiles after any maths change (`manage.py build_profiles`). Don't push or merge without asking. Python calculates; Gemini only reads.

---

## 1. Spec vs implementation

| # | Item | Spec (HANDOFF §6.1) | Implementation | Live check | Verdict |
|---|---|---|---|---|---|
| 17 | Safe to spend | `(B − bills before payday − planned saving − buffer) × min(7,D)/D`, floor 0 | Planned saving × **share of cycle left** | CUST03369: (1,085.77 − 730.54 − 445.37×0.5 − 92.48) × 7/15 = **18.69** ✓ matches the app's 18.70. CUST00025: (1,103.89 − 622.19 − 116.11×0.5 − 107.15) × 7/15 = **147.69** ✓. Under the strict spec formula CUST03369 would be **0** | **DEVIATION**: decide which and document it (FC-5) |
| 18 | Safe to save | `max(0, lowest forecast before payday − buffer)` | Uses the **low** bound of the band | CUST03369 → €0 (has danger days) ✓ | OK (more conservative) |
| 19 | Month-end balance | `B + income due − bills due − d·days ± 1.28·σ·√days` | Computed on the last day of the *current* month | `as_of` is 30 Sep = month end, so the horizon is 0 days and it returns today's balance with no band. Chat said "€1,085.77 at the end of **October**" (wrong). CUST01819: "today is the final day of September" | **FAIL** (FC-1) |
| 19 | Daily spend stat | median | **mean** (`FORECAST_DAILY_STAT`) | Daily drop €24.44 for CUST03369, plausible | Justified deviation; update the spec |
| 20 | Danger days | days where low < €50 before payday | same | CUST03369: Oct 8–14 in Overview, chat and alert all agree ✓ | OK. Chat wording said "below your safety buffer" (buffer €92.48, rule €50) |
| 20 | Availability | needs a payday | alert path ignores it | CUST05085 (no payday): Overview shows a "Tight days ahead … before payday" alert with 26 dates (5–30 Oct); chat says the forecast is unavailable | **INCONSISTENT** (FC-4) |
| 21 | Upcoming bills | next date = last + median gap; median amount | same, 30 days | Housing €730.54 on 2 Oct; the chart drops exactly 730.54 + 24.44 ✓ | OK |
| 22 | Surprise fund | surprises over 12 months / 12 | / min(12, months of data) | CUST01819: €115.82 in chat = Overview ✓ | OK (sensible deviation) |
| 23 | Seasonal | ratio > 1.25 → warn | same, plus a pot; unavailable without 12 months | "Do I spend more at certain times of year?" → **"Sorry, I couldn't work that out"** | **FAIL** (FC-3) |
| — | Chart | end-of-month line **with range band** | `get_chart` sends `expected` only | Chart JSON: `kind:"line"`, `{label, value}` only, no `low`/`high` | **MISSING** (FC-2) |
| — | Forecast screen (P3.5) | safe to spend/save, line + band, danger zone, bill timeline, surprise fund, seasonal banner | not built | only insight rows and chat cards | **MISSING** (FC-6) |
| — | End-of-month insight row | listed in `coach/insights.py` | not shown | absent for CUST03369, 00025, 01819, 05085 | **MISSING** (probably FC-1) |

## 2. Raw live results

| Test | Customer | Question | Reply (short) | Secs | Verdict |
|---|---|---|---|---|---|
| F1 | 03369 | Show my balance until payday as a chart | Line card, 1–15 Oct: 1,061.33 → 306.35 (2 Oct) → 13.05 (14 Oct) → 2,005.83 (payday). No band | 0.1 (cached) | PARTIAL |
| F2 | 03369 | What will my balance be at the end of the month? | "1,085.77 € at the end of October" | 25.7 | **FAIL** |
| F3 | 03369 | How much can I safely save before payday? | €0 ✓, but attached a level card: level 3, progress **−0.18** for a level-2 user | 15.2 | PARTIAL |
| F4 | 03369 | When will money get tight? | Oct 8–14 ✓, no chart card | 22.1 | PASS |
| F5 | 03369 | Do I spend more at certain times of year? | Generic "Sorry…" fallback | 14.9 | **FAIL** |
| F6 | 05085 | How much can I spend this week? | Honest: no payday detected | 9.2 | PASS |
| F7 | 05085 | Show my balance for the next month as a chart | Honest: needs a detected payday | 10.6 | PASS |
| F8 | 01819 | What will my balance be at the end of the month? | 7,497.51 €, "today is the final day of September" | 24.2 | **FAIL** (same cause as F2) |
| F9 | 01819 | How much should I set aside for surprises? | 115.82 € ✓ | 10.1 | PASS |

Hand checks of the chart (CUST03369):
- Implied balance B = 1,061.33 + 24.44 = 1,085.77.
- Retained payday inflow = 2,005.83 − 13.05 + 24.44 = 2,017.22 (monthly income 2,041.11; the salary sweep is removed).
- Expected crosses €50 on 13 Oct, but danger starts 8 Oct. This needs a band half-width of about €110 at t=8, so σ ≈ €30/day. Consistent with the low-edge rule, but the chart can't show why without the band.

---

## 3. Fixes (in order)

### FC-1 Month-end horizon is zero on the last day of the month (#19) — HIGH
- **Symptom:** "end of month" = today's balance, with no band; Gemini calls it "end of October".
- **Cause:** `compute_forecast` targets the last day of `today`'s month. `as_of` = 2026-09-30, so the horizon is 0.
- **Fix:**
  - If `today` is within N days of month end (suggest N = 3, put it in `thresholds.py` as `MONTH_END_ROLLOVER_DAYS`), target the **next** month end.
  - Always return `{date, expected, low, high}` with `date` included, so Gemini says the right month.
  - Make sure `daily_path` reaches that date.
  - Add the end-of-month row to the insights Forecast section if it is missing.
- **Tests:**
  - `today=2026-09-30` → target 2026-10-31, horizon 31, `low < expected < high`.
  - `today=2026-09-15` → target 2026-09-30.
  - The insight row exists.
- **Done when** F2 says roughly "end of October: about €X (likely €low–€high)".

### FC-2 Range band on the forecast chart — HIGH (needed for the demo graph)
- **Steps:**
  1. Add optional `low`/`high` per point to `ChartCard` (`coach/gemini/cards.py`) and `CARD_SCHEMA` (`tools/declarations.py`).
  2. In the catalogue, make the `forecast.daily_path` chart spec pass `expected`, `low`, `high`. Title "Expected balance (likely range)".
  3. In `components/Chart.jsx`: draw a shaded area between low and high, with the expected line on top. Mark today, bill days, payday and danger days (low < €50) in red. Label lines directly, no legend; fit 390 px.
  4. `validate_reply`: low/high numbers come from the tool, so they must pass the number check.
- **Tests:** card schema accepts and rejects the right shapes; Vitest renders the band path when low/high are present and falls back to a plain line without them.
- **Done when** F1 shows a line plus a band, and danger days are visibly where the band dips under €50.

### FC-3 Unavailable items produce the generic fallback (#23, and likely others) — HIGH
- **Symptom:** seasonal → "Sorry, I couldn't work that out".
- **Cause (check):** when a tool returns `{"available": false, "reason": ...}`, the loop or `validate_reply` doesn't let Gemini answer with the reason. It may also run out of rounds or fail validation.
- **Fix:**
  - The system prompt plus a code path: on `available:false`, reply with the reason in plain words, plus what would make it available.
  - Example: "I need a full year of history to compare seasons; you have N months."
  - Log the fallback reason every time.
- **Tests:** a mocked Gemini returning an unavailable tool → a `send_reply` with the reason text, not the fallback.
- **Done when** F5 answers honestly.

### FC-4 Danger-days alert ignores availability (#20) — MEDIUM
- **Symptom:** CUST05085 (no payday) gets "Tight days ahead … before payday", with dates out to 30 Oct.
- **Fix:** in `inferences/alerts.py`, only raise #20 (and #78, #102 if they use payday) when `availability` says the forecast is available. Or, if you want an alert without a payday, word it "in the next 30 days" and don't say "before payday".
- **Tests:** a profile with no payday → no #20 alert (or the "next 30 days" wording).

### FC-5 Safe-to-spend formula differs from the spec (#17) — DECIDE
- The app uses planned saving × share of cycle left. The spec subtracts the full planned saving. For CUST03369 that's €18.70 (app) vs €0 (spec).
- **Ask Will which one he wants.** Then update `context.md`/HANDOFF to match, add a comment citing #17, and add `test_forecast.py` cases for both customers above.
- **While at it:** document mean vs median (#19), the low-bound rule (#18) and min(12, months) (#22) as deliberate deviations.

### FC-6 Forecast screen (P3.5) — MEDIUM
- **Contents:**
  - safe to spend and safe to save
  - the FC-2 chart
  - a danger-zone banner
  - a bill timeline
  - a surprise-fund row
  - a seasonal banner (hidden when unavailable)
- **Order:** do FC-1 and FC-2 first; this screen reuses them.

### FC-7 Small wording and card issues — LOW
- Danger days are "below €50", not "below your safety buffer". Fix the explainer text or the prompt.
- F3 attached a `level_progress` card with level 3 and **progress −0.18** for a level-2 user. Clamp progress to 0–1 and show the *current* level.
- F4 should attach the chart (or a danger-days card). Allow `forecast_balance` → chart for "when will money get tight".

### FC-8 Add `backend/inferences/tests/test_forecast.py` — do alongside FC-1 to FC-5
- **Cases:**
  - month-end rollover
  - no payday → unavailable, and no "before payday" alert
  - safe to spend for the two hand-checked customers (18.70 and 147.70)
  - danger days = days where low < 50 before payday
  - surprise fund divides by min(12, months)
  - seasonal unavailable with fewer than 12 months
  - the payday inflow is retained income

---

## 4. Re-test after fixing
Ask these again: F1, F2, F4, F5, F8 (CUST03369 / CUST01819), and F6/F7 (CUST05085). Also:
- "Show my balance until payday as a chart": the band is visible and danger days are red.
- The Overview for CUST05085 has no "before payday" alert.
- The Overview for CUST03369 has an end-of-month row with a range.

---

## Appendix: other website test results so far (tests 1–22)
Tests 23–33 are not run yet: the page kept reloading while the code was being edited.

| # | Test | Verdict | Note |
|---|---|---|---|
| 1 | Safe to spend (03369) | PASS | €18.70; text uses "18,70 €" in an English reply |
| 2 | Next payday (03369) | **FAIL** | Generic fallback |
| 3 | Level and next step | PASS | Level 2, €1,089.71 to go |
| 4 | Leaky purchases | PARTIAL | Categories add to €128 but the text says "totaled €82.07" |
| 5 | Cut restaurants 20% | **FAIL** | Slider card shows 0.2%, €0.45 (F6) |
| 6 | Balance chart | PARTIAL | Rendered as horizontal bars, no band |
| 7–10 | Income, broke, splurge, spender type | PASS | |
| 11–15 | Goal: create, save, progress, +€50, undo | PASS | The goal appears in Overview. Undo took 23 s and showed the slider bug again |
| 16 | Pause goal | PARTIAL | Paused, but Overview still says "on track"; the confirm text says "Shall I save it?" |
| 17 | Mortgage ready? | PARTIAL | Score shown as "€0.97"; no advisor offer |
| 18–19 | Mortgage details → save | PASS | Stress €773.16 (14%) matches the formula |
| 20 | Credit score / loan | PARTIAL | "€0.97" again; no advisor offer |
| 21 | Income, partial view (03600) | **FAIL** | States €4,719.25 as if it saw all the income |
| 22 | Other banks? | PASS | Honest |

**Data created by tests (clean up with Will's OK):**
- CUST01819: "Trip to Japan" goal, €1,500, paused.
- CUST01094: mortgage €120,000, 4%, 20 years.
- The goal ID was `goal_3`, so 2 older test goals exist elsewhere (probably CUST00025).

**Stability:**
- Saw "Backend not reachable" twice and several Vite reload failures (`App.jsx`, `Chat.jsx`) during testing, caused by editing while the servers run.
- Freeze edits during test runs and the demo.