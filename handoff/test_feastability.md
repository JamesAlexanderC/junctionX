# SALDO PREFLIGHT: predict what will pass or fail before we test

You are Claude Code, working in Will's `junctionX` repo (Saldo, the S-Bank AI money coach for Junction 2026).

**Goal:** read the code and predict, for every item #1–110 plus the alert coach and the goal flow, whether a live chat test will pass. **Do not run the chat and do not call Gemini.** This is a static read. It tells us what to fix before spending ~105 live API calls.

## Rules
- **Read-only.** Don't edit app code, don't change data, don't commit, and don't push. The only file you write is `PREFLIGHT_RESULTS.md` in the repo root.
- Running `pytest` and `python manage.py verify_handoff` is allowed: they're local and make no Gemini calls. Mock anything that would call the API.
- Don't print `.env` or the API key.
- The spec is `HANDOFF.md` §6. The real file layout may differ from HANDOFF §3; find the real paths, don't assume them. The frontend is `.jsx`.

## Step 1: map the pipeline (write this down first)
Find and note the file path and function names for each of these:
1. **Inference code:** the `backend/inferences/` modules, or wherever the maths lives. Make a list of which inference numbers are actually computed. Grep for `inference=`, `"inference":`, `#NN` and keys like `safe_to_spend`.
2. **Insights endpoint:** `/api/insights/<id>/`. Which inferences it returns.
3. **Tool registry:** the `TOOLS` dict and `TOOL_DECLARATIONS`. List every tool name and the inference(s) it exposes. Compare with HANDOFF §5.2:
   - Core: get_category_spend, get_safe_to_spend, get_safe_to_save, get_baskets, get_level, simulate_cut, forecast_balance, get_spender_type, list_goals, create_goal, rate_goal, get_detected_goals, get_mortgage_readiness, get_explainer, get_benchmark, get_relevant_insights.
   - Coach: get_alerts, explain_alert, suggest_fixes, simulate_plan, accept_plan, snooze_alert.
   - Expert: get_account_split, get_overdraft_history, get_credit_health, simulate_save_vs_invest, get_deposit_options, get_cost_of_living, get_rate_exposure, get_market_data.
4. **Router:** the keyword rules and the Flash-Lite fallback. Which phrases map to which depth or tool set? Can a question reach every tool, or does the router hide some tools from some depths?
5. **validate_reply:** exactly how numbers are checked. **Key question:** are numbers the *user* typed (30%, €1,500, June 2027, 2,000) allowed, or are they rejected? Are percentages stored as 0.2 but written as 20%? Euro formatting (1,103.89 vs 1103.89 vs "1 103,89")? Finnish decimal commas? Any of these is a likely cause of the generic fallback.
6. **Fallback:** where "Sorry, I couldn't work that out just now" is produced, and every path that leads there (5 rounds used up, validation failed twice, exception caught). Is the reason logged?
7. **Goal creation and the confirmation state:** how "Yes, save it" finds the pending goal. Is it from `history`, the session, or the DB? Note that the frontend sends only `{role, content}` text history (last 6 turns), with no structured pending state.
8. **Date handling:** how "last month" and "this month" are resolved. Live tests show "last month" = **August**, but `as_of` = 2026-09-30. Find the cause.

## Step 2: predict every item
For each row, decide:
- **Built?** YES / PARTIAL / NO, with the file and function.
- **Reachable from chat?** Is there a tool for it, and can the router send the question there?
- **Prediction:** PASS / PARTIAL / FAIL / FALLBACK / NOT BUILT / NOT TRIGGERED (the customer lacks the data).
- **Why:** one line, with file:line.
- **Fix:** one line, if it is not PASS.

Use these test questions; they are the ones the live run will ask.

### Core inferences
| # | Item | Test question | Check |
|---|---|---|---|
| 1 | Payday | When do I get paid? | weekend shift |
| 2 | Monthly income | What's my monthly income? | median of 3 months |
| 3 | Income stability | Is my income steady? | CV band |
| 4 | Regular bills | What are my regular bills? | |
| 5 | Subscriptions | What subscriptions do I have? | |
| 6 | Unused subscription | Am I paying for anything I don't use? | |
| 7 | Essentials | How much goes on essentials? | essentials ≥ rent? (live: 1,581 < 2,266) |
| 8 | Surprises | Did I have any unexpected costs? | |
| 9 | Leaky | What are my small leaky purchases? | |
| 10 | Basket split | Where did my money go last month? | shares sum to 100 |
| 11 | Weekend share | Am I a weekend spender? | live: PASS |
| 12 | Night share | How much do I spend at night? | live: PASS |
| 13 | Impulse bursts | Do I make impulse purchases? | |
| 14 | Payday splurge | Do I overspend after payday? | |
| 15 | Loyalty | Do I always shop at the same places? | |
| 16 | Spender type | What's my spender type? | live: PASS |
| 17 | Safe to spend | How much can I spend this week? | |
| 18 | Safe to save | How much can I safely save now? | |
| 19 | Month-end balance | What will my balance be at month end? | shows a range |
| 20 | Danger days | When will money get tight? | |
| 21 | Upcoming bills | What bills are coming up? | |
| 22 | Surprise fund | How much should I set aside for surprises? | |
| 23 | Seasonal | Do I spend more at certain times of year? | |
| 24 | Cut by p% | If I cut entertainment by 10%? | slider units (live: min/max 0–50 but pct 0.2; another reply used 0.05–0.5) |
| 25 | Drop subscription | What would I save a year if I cancel it? | |
| 26 | Goal date | When could I save 3,000 EUR? | |
| 27 | Habit translation | What could my restaurant spending buy instead? | |
| 28–32 | Levels | What level am I? / What do I need for the next level? | live said L1→L2 needs buffer, but the spec says spend ≤ income; "97%" next to "€322 to go" |
| 33 | Easiest step | What's the easiest way to improve? | live: 30% cut = €16 (base €54 leaky) vs #24 using €246 |
| 34–35 | Mortgage readiness | Am I ready for a mortgage? | "guidance only" wording |
| 36 | Peer benchmark | Compare me with people my age | live: PASS, no card |
| 37 | Area benchmark | How do I compare with my area? | |
| 38 | Unusual charge | Explain the 320.06 EUR charge | live: raw MRC ID shown |
| 39 | Duplicate | Was I charged twice for anything? | |
| 40 | Category spike | Did any category jump this month? | |
| 41–43 | Multi-bank | Do I have accounts at other banks? | bonus; is it honest? |
| 44–48 | Recommended goal | What goal should I set? | matches the level |
| 49 | Difficulty | (goal flow) | Easy/Stretch/Hard |
| 50 | Realism | Save 5,000 EUR by Christmas | suggests realistic amount/date |
| 51–52 | Progress / on track | How is my Japan goal going? | |
| 53 | Coaching tip | How can I get back on track? | |
| 54–55 | Ratings / success | (UI thumbs; unit test) | |
| 56–62 | Detected goals | Do you see any goals in my spending? | |
| 63–74 | User goals | (goal flow below) | priority, clash, pause, milestones |
| 75 | Saver | How much do I save each month? | |

### Alerts (#76–102)
For each alert: is the rule coded? Is there a tool that returns it? Does `explain_alert` give evidence transactions with **merchant names, not MRC IDs**? Which of the 50 demo customers (CUST00001–00050) can trigger it? List one customer per alert if you can work it out from the data or the code.

| # | Alert | Test question |
|---|---|---|
| 76 | Loan burden | How much of my income goes to loans? |
| 77 | Rate-rise stress | What if interest rates rise? |
| 78 | Mortgage at risk | Can I cover my next mortgage payment? |
| 79 | Payment changed | Did my loan payment change? |
| 80 | Missed loan | Did I miss any loan payments? |
| 81 | Thin buffer | Is my buffer enough for my loan? |
| 82 | Affordability | Could I afford a 250,000 EUR flat with 25,000 deposit? |
| 83 | New credit | Have I taken any new credit? |
| 84 | Many lenders | How many lenders do I owe? |
| 85 | Overdraft | Have I gone into overdraft? |
| 86 | Fees | Have I paid any bank or late fees? |
| 87 | Income dropped | Did my income drop? |
| 88 | Spending pace | Am I spending too fast this month? |
| 89 | Lifestyle creep | Is my spending creeping up? |
| 90 | Subscription creep | Are my subscriptions growing? |
| 91 | Trial to paid | Did a free trial turn into a paid plan? |
| 92 | Similar subscriptions | Do I have overlapping subscriptions? |
| 93 | Annual bill | Any yearly bills coming up? |
| 94 | Savings withdrawn | Did I take money out of savings? |
| 95 | Streak broken | Did I miss my usual saving this month? |
| 96 | Cash up | Am I using more cash than usual? |
| 97 | Small leaks | How many tiny purchases do I make? |
| 98 | Gambling | (opt-in; check the wording only) |
| 99 | Low balance | Is my balance too low right now? |
| 100 | Payday missed | Has my salary arrived? (CUST05085, no payday) |
| 101 | Bill went up | Did any bills go up? |
| 102 | Big bill soon | Can I cover my next big bill? |

### Alert coach (failed live)
"Help me clear my alerts" → "Simulate step 1" → "Do it" → "Yes".
Trace it through the code:
- Does `suggest_fixes` run the greedy set-cover?
- Does it re-run `run_all_alerts` on a simulated profile?
- Does `accept_plan` read the confirmation?

Also find out why "Help me clear my alerts" and "Fix tight days" failed live. Likely causes: a router depth that hides the tools, validation of computed numbers, or an exception.

### Expert features
| # | Feature | Test question | Live result |
|---|---|---|---|
| 103 | Account split | How much should I move to savings? | generic answer, no move amount |
| 104 | Overdraft history | How often have I been overdrawn and what did it cost? | |
| 105 | Credit health | What's my credit health score? | **fallback** |
| 106 | Save vs invest | Should I save or invest 100 EUR a month for 10 years? | |
| 107 | Healthy ranges | Are my spending shares healthy? | |
| 108 | Fixed vs base | I got a 2,000 EUR bonus. Fixed term or savings account? | |
| 109 | Cost of living | How did inflation affect my spending? | said it can't measure this |
| 110 | Rate exposure | How exposed am I to Euribor changes? | |

### Goal flow (failed 3/3 live at "Yes, save it")
1. "I want to save 1,500 EUR for a trip to Japan by June 2027". Live: the app asked for a priority (OK).
2. "Medium"
3. "Yes, save it". **Trace exactly what happens:** router depth, which tools, whether `create_goal` is allowed this turn, how it knows the confirmation happened, and whether validate_reply rejects 1,500 / June 2027 because those numbers come from the user, not a tool.
4. "How is my Japan goal going?"
5. "Add a 5,000 EUR emergency fund by Christmas" (realism, clash)
6. "Pause the Japan goal"

Note: a "Japan trip" goal may already exist on CUST00025 from an interrupted test. Check the DB read-only and report it; don't delete it.

### Other things seen live (confirm the cause in code)
- Generic fallback with HTTP 200 and no reason given: credit health, "salary dropped 30%", and 6 times in round 1.
- Latency: median 18 s (5–28 s). Count the Gemini calls per turn (router + tool rounds + validation retry) and say where the time goes.
- Intermittent 502 on `/api/chat/`. Is the Django dev server auto-reloading, or is the worker crashing on goal messages?
- "Last month" means August instead of September.
- Restaurants: €54 (leaky, <€25 purchases) vs €246 (all restaurants) used inconsistently.
- Essentials (€452 in Sep) are less than rent (€622) for CUST00025. Check the basket rules.
- Chips that lead nowhere ("Snooze alert", "Add a loan", "Talk to an advisor"): do they map to a tool or a screen?
- The Tesla refusal attached an unrelated level_progress card.

## Step 3: output
Write `PREFLIGHT_RESULTS.md` with:
1. **Pipeline map** (Step 1), with paths.
2. **Summary counts:** PASS / PARTIAL / FAIL / FALLBACK / NOT BUILT / NOT TRIGGERED.
3. **One table row per item:** # | item | built | tool | prediction | why (file:line) | fix.
4. **Top 10 root causes**, ranked by how many items each one breaks. For example, "validate_reply rejects user-supplied numbers → breaks #24, #26, #50, #63–74, #82, #106, #108".
5. **Customer picks:** which CUST id triggers loans, overdraft, subscriptions and the alerts, for the live run.
6. **Suggested fix order**, merged with `SALDO_FIX_PLAN.txt` if it is in the repo (keep its F-numbers and add new ones as F22+).

Then stop and show Will the summary counts and the top 10 root causes. Don't start fixing until he says so.