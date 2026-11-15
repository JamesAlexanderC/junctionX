# Next session: state of `will-live-testing` and what to do next

Written 14 Nov 2026 at the end of a long session, so a fresh session can carry on.
Read `CLAUDE.md`, `docs/gemini_tools.md` and this file first.

## How Will wants to work (binding)

- **Plan first, then ask.** Explain the cause and the planned change, and wait
  for an explicit go before editing code. Answering a design question is not a go.
- Tests first (red, then green), one commit per fix, `scripts/bin/check` and
  `python manage.py verify_handoff` before each commit.
- Never push, merge or delete data without asking. Deleting rows needs his OK.
- Live repro without touching `.env`:
  `DEMO_MODE=0 GEMINI_ROUTER_MODEL=gemini-3.5-flash-lite ../.venv/bin/python manage.py shell < script.py`
  (`python-dotenv` does not override variables that are already set).
- With `settings.DEBUG`, a fallback reply carries `debug` (reason, tool trace,
  validation errors), and the log has a `chat fallback {...}` line. Use it.

## Branch state

`will-live-testing`, branched from `develop` after PR #9. **Not pushed.**
17 commits since PR #9, all with `scripts/bin/check` passing:

| Commit | What |
|---|---|
| `91797c9`…`b22e7e9` | Forecast fixes FC-1 to FC-5, FC-7, FC-8 (`handoff/forcasting.md`) |
| `98c6788` | Conversational replies: cards in history, earlier numbers allowed, one-round small talk |
| `4632a98` | "Fix this" only on alerts a plan can fix (`fixable`); others show "Why?" |
| `eaa77e5` | F8: "last month" = latest complete month (`inferences.common.last_complete_month`) |
| `ed40edc` | Friendly merchant names (`MRC-GRO-0016` -> "a grocery shop"); #101 skips shops |
| `5716877` | #93 yearly-bill false positive, English card units, seasonal wording, privacy, off-topic |
| `d63b781` | #88 partial-view wording; #8 surprises vs unusual charges |
| `dc5bdad` | Level card only for level or progress questions |
| `91371a4` | `calculate_goal` tool (#26, #49, #65, #66); one-off safe-to-save is not monthly |
| `6eb92ed` | Number cards may omit the label (rejections cost 6-16 s each) |
| `c056a3f` | Thinking by depth: facts and small talk off, depth 2 low, 3-4 default |

Speed, 10 core questions on CUST02305: median 21.9 s at the start of the day,
then 18.7 s, and **12.2 s after `c056a3f`** (max 28.9 s, no fallbacks).

### Uncommitted: speed experiment (a), decide first

Files: `coach/gemini/loop.py`, `router.py`, `tools/context.py`,
`tests/test_fallback.py`, `tests/test_loop.py`, new `tests/test_prefetch.py`.
All 484 tests pass with it.

- `router.prefetch_for` runs the obvious tool before the first Gemini call
  (safe to spend, payday, baskets, level, spender type, alerts, month-end
  balance; at most 2).
- `router.one_call_ok`: for clear quick facts with no why/explain/what-if/help
  wording, round 1 only declares `send_reply`, so it answers in one call.

It was never measured cleanly: the with/without run was stopped. **Next:**
1 run of the 10 core questions with and without, on top of `c056a3f`.
Commit it if it is faster, otherwise drop it with `git checkout` on those files
and delete `test_prefetch.py`.

Related: "What is safe for me to spend this week?" and "What level am I?" have
no depth keyword, so the router model ranks them deep (default thinking,
18-24 s). Adding keyword rules for them to depth 1 is a cheap speed win.

### Untracked files Will added

`handoff/forcasting.md`, `handoff/forcast_context.md`,
`handoff/test_feastability.md`. Ask before committing them.

### Will's `.env`

`DEMO_CUSTOMERS=CUST01819,CUST03369,CUST01094,CUST03600` (F5, chosen).
Check `GEMINI_ROUTER_MODEL=gemini-3.5-flash-lite` (2.5 is retired, 404) and
`DEMO_MODE=0` while testing. The demo reply cache was emptied today.

## Next fixes (from Will's latest live tests), in this order

1. **"How much can I safely spend this week?" gave "Sorry" for CUST00004 and
   CUST00033** (2 of 8; tapping the chip then worked). Probably a rejected
   reply or running out of rounds. Two later commits likely help (`6eb92ed`,
   `c056a3f`). Re-run both live, read the `chat fallback` reason, then fix.
2. **Seasonal alert says "Last year 2026-10"** (CUST00007, 00021, 00028):
   `inferences/alerts.py` `rule_23_seasonal` formats next month's key; write
   the month name ("Last October ...").
3. **Too many alerts** (CUST00027 and 00028 have 8): cap at 5 by priority in
   `coach/services.active_alerts`; the rest stay reachable in chat.
4. **Demo hardening:** `DEBUG = True` is hard-coded in `conf/settings.py`
   (404 pages list the URL routes); read it from `.env`, return JSON 404s; add
   a gunicorn command with 3-4 workers and no auto-reload (F18). The Overview
   took a median of 12 s when 50 customers loaded at once (single-threaded dev
   server), and the dev server dropped once (502).
5. **Level wording:** every level 1 -> 2 answer says "build your buffer", but
   the spec says level 2 = spent no more than income last month. Lives in
   `inferences/levels.py` (next step text); shared code, explain before changing.
6. Smaller: "it is varies" / "day(s)" grammar (F17, 15 customers); "Essentials
   1321%" (CUST00050, share calculation); yearly-bill alert twice (CUST00035,
   dedupe); month-end forecast below EUR 0 with no alert (CUST00048);
   history accepts `role: "system"` (reject it); no message length limit; the
   slider shows 0.2% instead of 20% (F6).

## Also open (deferred by Will)

- **#33 level card ladder:** `levels.ladder.reached` is each level's own test,
  so level 5 can be "reached" while level 3 is not. `tools/read.level_card`
  fixes the order, but Gemini also sees the raw ladder (from `get_level` and
  `get_inference("levels")`) and mixed them. Options: (a) Python replaces level
  cards with `level_card()` after validation, like `mark_alert_cards`;
  (b) stop exposing the raw ladder; (c) cumulative `reached` in `levels.py`.
  Recommended (a) + (b).
- FC-6 Forecast screen (`handoff/forcasting.md`).
- #103-#110 expert features (F10): build only from real data, invent nothing.
- Button contrast: white on `#00aa46` is about 3:1 (skipped by Will for now).
- `goals.safe_to_save_monthly` adds a one-off amount to a monthly rate and
  feeds #66 realism. It is only relabelled for Gemini; the maths is unchanged.
