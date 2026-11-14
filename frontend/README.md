# Saldo frontend

Minimal chat-first React + Vite app. Pick a real customer, see the insights
the backend computed for them (`GET /api/insights/<id>/`), and chat with the
coach (`POST /api/chat/`). There is no demo data and no offline fallback:
errors from the backend are shown as they are.

```
npm run dev     # http://localhost:5173, proxies /api to Django on :8000
npm test        # Vitest
npm run lint    # oxlint
npm run build
```

`src/lib/formulas.js` holds the #24 and #26 formulas the slider card
recomputes locally; they must match the backend.
