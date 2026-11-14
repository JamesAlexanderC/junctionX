# Handoff: live Gemini evals, model choice and streaming

## What exists (branch `jamie-implementation`)
- `backend/coach/gemini/loop.py`: the context.md loop (mode ANY, AFC off,
  max 5 rounds, one validation retry, then `FALLBACK_REPLY`). Without
  `GEMINI_API_KEY` it returns an offline canned reply (P2.1).
- `backend/coach/gemini/router.py`: keyword rules, Flash-Lite fallback.
- `backend/coach/management/commands/run_evals.py`: the full eval set from
  context.md "Tests" section 3 (3 runs per question, pass-rate report). It
  skips with a warning when no key is set.
- All API tests use a scripted fake client; nothing has been run against the
  real model yet.

## Why this is handed off
It needs a real `GEMINI_API_KEY`, and the pass checks need tuning against real
model output, which can't be done offline.

## Next steps
1. Put `GEMINI_API_KEY` in `.env` and list the models your key can use:
   `python -c "from google import genai; [print(m.name) for m in genai.Client().models.list()]"`.
   Set `GEMINI_MODEL` / `GEMINI_ROUTER_MODEL` in `.env` (defaults
   `gemini-3.8-flash` / `gemini-3.5-flash-lite`).
2. Build a demo profile (`load_data` + `build_profiles`) or use `demo-aino`.
3. `cd backend && python manage.py run_evals --customer <id>`; target 90 %.
4. Common things to tune if evals fail:
   - `validate.py` number matching: dates written as "23 October", amounts
     rounded by the model, and `FREE_INTEGERS` (0-10 allowed without a source).
   - The router regexes for questions without keywords.
   - The system prompt for Finnish replies and refusals.
   - `run_evals.py` checks are coarse (depth, tools called, no goal created,
     Finnish text). Add per-question checks ("names a bill or the buffer",
     "slider card present", "number matches #24") as needed.
5. Turn `DEMO_MODE=1` on before the demo; scripted questions are cached in
   `DemoCache` after the first good answer. Run the demo once with Wi-Fi on
   to warm the cache, then check it works with Wi-Fi off.

## Streaming
`POST /api/chat/` returns the whole send_reply JSON at once. context.md says
"React streams the text"; the simplest route is to keep the JSON response and
animate the text client-side. If true streaming is wanted, wrap the
validated reply in an SSE response (`StreamingHttpResponse`, events
`token` / `cards` / `done`) after validation, since numbers must be checked
before any text is shown.
