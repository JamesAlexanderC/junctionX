# Handoff: pitch and demo script (P3.6)

Not built on `jamie-implementation`: slides and the spoken demo script need a
human presenter, rehearsal timing and the final demo customers chosen from the
real data, so they were left out of the code work.

## What is needed
- 5 slides: problem, demo, how it works, why it fits S-mobiili, next steps.
- A 3-minute demo script (about 20 seconds per moment below), rehearsed twice.
- A backup video of the full demo (DEMO_MODE on, Wi-Fi off).
- Pitch lines from context.md: opener "Every Finn checks their saldo. None of
  them can ask it a question. Until now."; tagline "Know your balance. Find
  your balance."; trust line "The AI never guesses numbers. Python calculates,
  the AI explains."
- Check that the name "Saldo" (backup "Sisu Coach") is not already a
  well-known finance app.

## Demo moments and the screens that support them
| # | Moment | Screen / component (frontend/src) |
|---|--------|-----------------------------------|
| 1 | Home: safe to spend, level bar, four baskets | `screens/Home.jsx` (Focus home) |
| 2 | Quick question -> number card -> "Go deeper" chips | `screens/Chat.jsx`, `components/Cards.jsx` (number), chips |
| 3 | What-if slider: dining out -20% -> goal sooner | `components/Cards.jsx` SliderCard, `lib/formulas.js` (#24, #26) |
| 4 | "Help me buy a flat" -> clarifying question -> goal card | Chat question + goal cards (needs backend depth-4 flow) |
| 5 | "Help me clear my alerts" -> 2-step plan, before/after | `screens/Alerts.jsx`, plan + before_after cards (needs backend alert coach) |
| 6 | Detected-goal nudge "Looks like you're saving. Name it?" | Home nudge (falls back to detected goal when no red/amber alert) |
| 7 | Bonus: connect Nordea -> hidden car loan | Explore > Accounts (static view only; mock consent screen not built) |

## Open items for the presenter
- Pick the demo customer whose data produces moments 4, 5 and 6 together, or
  switch customers mid-demo via the customer picker.
- Moment 7 needs a mock consent screen ("Allow S-Bank to read your Nordea
  account for 180 days?"); not built yet.
- Cache the scripted questions (backend DEMO_MODE) before recording the video.
