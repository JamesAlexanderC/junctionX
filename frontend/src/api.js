// API client for the Django coach backend (contract: docs/design.md).
//
// On first use we probe GET /api/health/ once. If the backend answers with a
// healthy JSON body we talk to it for the rest of the session; otherwise the
// whole app switches to demo mode and every call is served by mock.js, so the
// UI can always be clicked through. Add `?demo=1` to the URL to force demo
// mode even when a backend is running.
//
// Chat is SSE over POST /api/chat/: one `data: <json>\n\n` per event, where the
// JSON `type` is one of meta | tool | token | chart | concept | suggestions |
// error | done.

import {
  MOCK_HEALTH,
  mockChat,
  mockCustomers,
  mockFeatured,
  mockOverview,
} from './mock.js'

const API = import.meta.env.VITE_API_URL ?? ''
const HEALTH_TIMEOUT_MS = 3000

let modePromise = null

function forcedDemo() {
  try {
    return new URLSearchParams(window.location.search).has('demo')
  } catch {
    return false
  }
}

async function probeHealth() {
  if (forcedDemo()) return { demo: true, health: MOCK_HEALTH }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS)
  try {
    const res = await fetch(`${API}/api/health/`, { signal: controller.signal })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const health = await res.json()
    if (health?.status !== 'ok') throw new Error('Backend not healthy')
    return { demo: false, health }
  } catch {
    return { demo: true, health: MOCK_HEALTH }
  } finally {
    clearTimeout(timer)
  }
}

/** Resolves once to `{ demo: boolean, health }`; later calls reuse it. */
export function getMode() {
  modePromise ??= probeHealth()
  return modePromise
}

async function getJSON(path, signal) {
  const res = await fetch(`${API}${path}`, { signal })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json())?.detail ?? ''
    } catch {
      // Body was not JSON; the status code is enough.
    }
    throw new Error(detail || `Request failed (HTTP ${res.status})`)
  }
  return res.json()
}

export async function getFeatured(signal) {
  const { demo } = await getMode()
  if (demo) return mockFeatured()
  const body = await getJSON('/api/customers/featured/', signal)
  return Array.isArray(body) ? body : (body.results ?? [])
}

export async function searchCustomers({ search = '', limit = 20, offset = 0 }, signal) {
  const { demo } = await getMode()
  if (demo) return mockCustomers({ search, limit, offset })
  const qs = new URLSearchParams({ search, limit, offset })
  const body = await getJSON(`/api/customers/?${qs}`, signal)
  if (Array.isArray(body)) return { count: body.length, results: body }
  return { count: body.count ?? 0, results: body.results ?? [] }
}

// Overviews are cached per customer so Home <-> Coach tab switches are instant.
const overviewCache = new Map()
const overviewResolved = new Map()

/** Returns an already-loaded overview synchronously, or undefined. */
export const peekOverview = (customerId) => overviewResolved.get(customerId)

async function loadOverview(customerId) {
  const { demo } = await getMode()
  if (demo) return mockOverview(customerId)
  return getJSON(`/api/customers/${encodeURIComponent(customerId)}/overview/`)
}

export function getOverview(customerId) {
  if (!overviewCache.has(customerId)) {
    const promise = loadOverview(customerId).then(
      (data) => {
        overviewResolved.set(customerId, data)
        return data
      },
      (err) => {
        overviewCache.delete(customerId)
        throw err
      },
    )
    overviewCache.set(customerId, promise)
  }
  return overviewCache.get(customerId)
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

/** Streams one coach reply, calling onEvent per event; resolves when done. */
export async function streamChat({ customerId, messages, onEvent, signal }) {
  const { demo } = await getMode()
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
