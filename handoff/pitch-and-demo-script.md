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
The frontend is now a single chat-first page (`frontend/src/App.jsx`): a
customer picker, an insights panel listing only what `GET /api/insights/<id>/`
returns for that real customer, and the chat. There is no Home, Explore,
alert inbox or demo data any more, so every moment runs through chat.

| # | Moment | What supports it (frontend/src) |
|---|--------|---------------------------------|
| 1 | Pick a customer, insights appear (safe to spend, baskets, alerts) | `components/CustomerPicker.jsx`, `components/Insights.jsx` |
| 2 | Quick question -> number card -> "Go deeper" chips | `components/Chat.jsx`, `components/Cards.jsx` (number), chips |
| 3 | What-if slider: dining out -20% -> goal sooner | `components/Cards.jsx` SliderCard, `lib/formulas.js` (#24, #26) |
| 4 | "Help me buy a flat" -> clarifying question -> goal card | question + goal cards (needs backend depth-4 flow) |
| 5 | "Help me clear my alerts" -> 2-step plan, before/after | type it, or tap an alert insight; plan + before_after cards |
| 6 | Detected-goal nudge "Looks like you're saving. Name it?" | only if the backend returns it as an insight |
| 7 | Bonus: connect Nordea -> hidden car loan | not in the UI; real data has one account per customer |

## Open items for the presenter
- Pick the real demo customer whose data produces moments 3 to 6 together, or
  switch customers mid-demo via the picker.
- Moment 7 would need a mock second bank, which conflicts with the
  "no demo data" rule; drop it or label it clearly as synthetic.
- Cache the scripted questions (backend DEMO_MODE) before recording the video.
