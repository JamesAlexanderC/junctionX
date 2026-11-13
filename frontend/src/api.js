// API client for the Django coach backend.
//
// Chat stream contract (SSE over POST /api/chat/). Each event is one line of
// `data: <json>` followed by a blank line, where the JSON is one of:
//   { "type": "token",   "text": "..." }                  streamed answer text
//   { "type": "chart",   "chart": Chart }                 optional chart payload
//   { "type": "concept", "title": "...", "text": "..." }  optional explainer
//   { "type": "error",   "message": "..." }
//   { "type": "done" }
//
// Chart = {
//   kind: "bar" | "line" | "pie",
//   title: string,
//   unit?: string,                      // e.g. "€"
//   data: [{ label: string, value: number }]
// }
//
// If the backend can't be reached, the app falls back to demo mode and uses
// canned answers from mock.js so the UI can still be developed and shown.

import { mockChat, MOCK_CUSTOMERS } from './mock.js'

const API = import.meta.env.VITE_API_URL ?? ''

export async function getCustomers() {
  try {
    const res = await fetch(`${API}/api/customers/`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const body = await res.json()
    const customers = Array.isArray(body) ? body : body.results ?? []
    return { customers, demo: false }
  } catch {
    return { customers: MOCK_CUSTOMERS, demo: true }
  }
}

function handleEvent(raw, onEvent) {
  const data = raw
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  if (!data) return
  let event
  try {
    event = JSON.parse(data)
  } catch {
    // Treat non-JSON data lines as plain answer text.
    event = { type: 'token', text: data }
  }
  onEvent(event)
}

// Streams one coach reply. Calls onEvent for every event, resolves when done.
export async function streamChat({ customerId, messages, demo, onEvent, signal }) {
  if (demo) return mockChat({ customerId, messages, onEvent, signal })

  const res = await fetch(`${API}/api/chat/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ customer_id: customerId, messages }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`Chat failed (HTTP ${res.status})`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let split
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      handleEvent(buffer.slice(0, split), onEvent)
      buffer = buffer.slice(split + 2)
    }
  }
  if (buffer.trim()) handleEvent(buffer, onEvent)
  onEvent({ type: 'done' })
}
