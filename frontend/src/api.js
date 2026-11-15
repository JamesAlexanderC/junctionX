// API client for the Django backend (contract: CLAUDE.md "API").
//
//   GET  /api/customers/?q=<search>   -> [{customer_id, customer_age, ...}]
//   GET  /api/insights/<customer_id>/  -> [{key, inference, title, value,
//                                          unit, text, section, severity?}]
//   GET  /api/goals/?customer_id=<id> -> {active, completed, clash}
//   GET  /api/spending/?customer_id=<id> -> {month, total, categories, savings}
//   POST /api/chat/ {customer_id, message, history, depth?} -> send_reply
//   POST /api/chat/?stream=1 (same body) -> NDJSON progress events, then
//                                          {type: "reply", reply}
//   POST /api/auth/login/ {username, password} -> {token, user}
//   POST /api/auth/logout/                      -> 204
//
// Every call except login sends "Authorization: Token <key>". A 401 forgets
// the token and fires AUTH_EVENT so the app shows the login screen again.
// There is no offline or demo fallback: every error is shown as is.

const API = import.meta.env.VITE_API_URL ?? ''
const TOKEN_KEY = 'saldo.token'
export const AUTH_EVENT = 'saldo:auth'
// Used only when storage is blocked (private mode): lives until reload.
let memoryToken = null

function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return memoryToken
  }
}

function setToken(token) {
  memoryToken = token
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage blocked: memoryToken carries it
  }
  window.dispatchEvent(new Event(AUTH_EVENT))
}

const currentToken = getToken
export const isLoggedIn = () => Boolean(currentToken())

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function send(path, { method = 'GET', body, signal } = {}) {
  try {
    return await fetch(`${API}${path}`, {
      method,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(currentToken() ? { Authorization: `Token ${currentToken()}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') throw e
    throw new ApiError('Backend not reachable', 0)
  }
}

async function readJson(res) {
  let data = null
  try {
    data = await res.json()
  } catch {
    // not JSON (e.g. the Vite proxy's 502 page)
  }
  if (res.status === 401) {
    setToken(null)
    throw new ApiError('Please log in again', 401)
  }
  if (!res.ok) {
    if (res.status >= 502 && res.status <= 504 && !data) {
      throw new ApiError('Backend not reachable', res.status)
    }
    const msg = data?.error ?? data?.detail ?? `Request failed (HTTP ${res.status})`
    throw new ApiError(msg, res.status)
  }
  return data
}

async function request(path, options) {
  return readJson(await send(path, options))
}

// Lines of an NDJSON body as they arrive, parsed. Falls back to reading the
// whole body where the response has no stream (older browsers, test fakes).
async function* ndjsonLines(res) {
  const parse = (line) => (line.trim() ? [JSON.parse(line)] : [])
  if (!res.body?.getReader) {
    for (const line of (await res.text()).split('\n')) yield* parse(line)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n')
    buffer = done ? '' : lines.pop()
    for (const line of lines) yield* parse(line)
    if (done) return
  }
}

// {built, demos: [...], customers: [...]} for the landing page.
export async function getDemoDirectory({ signal } = {}) {
  const body = await request('/api/customers/demo/', { signal })
  return {
    built: Boolean(body?.built),
    demos: Array.isArray(body?.demos) ? body.demos : [],
    customers: Array.isArray(body?.customers) ? body.customers : [],
  }
}

export async function getInsights(customerId, { signal } = {}) {
  const body = await request(`/api/insights/${encodeURIComponent(customerId)}/`, {
    signal,
  })
  // Backend shape: {customer_id, as_of, insights: [...]} (CLAUDE.md "API").
  if (Array.isArray(body)) return body
  return Array.isArray(body?.insights) ? body.insights : []
}

// Backend shape: {customer_id, as_of, active: [...], completed: [...], clash}.
export async function getGoals(customerId, { signal } = {}) {
  const body = await request(
    `/api/goals/?customer_id=${encodeURIComponent(customerId)}`,
    { signal },
  )
  return {
    active: Array.isArray(body?.active) ? body.active : [],
    completed: Array.isArray(body?.completed) ? body.completed : [],
    clash: body?.clash ?? null,
  }
}

// Backend shape: {customer_id, as_of, month, is_current, total, categories:
// [{category, total, share, count, usual, vs_usual}], savings: [{category,
// total, count}], savings_total}. Savings are not part of total.
export async function getSpending(customerId, { signal } = {}) {
  const body = await request(
    `/api/spending/?customer_id=${encodeURIComponent(customerId)}`,
    { signal },
  )
  return {
    month: body?.month ?? null,
    is_current: Boolean(body?.is_current),
    total: body?.total ?? 0,
    categories: Array.isArray(body?.categories) ? body.categories : [],
    savings: Array.isArray(body?.savings) ? body.savings : [],
    savings_total: body?.savings_total ?? 0,
  }
}

// Only the last 6 turns are sent (context.md "Controls"). With onProgress
// the reply streams (?stream=1): onProgress gets each {type: "step" |
// "thought", text} event while the coach works, and the reply comes last.
export async function sendChat({
  customerId,
  message,
  history = [],
  depth,
  conversationId,
  onProgress,
}) {
  const body = {
    customer_id: customerId,
    ...(conversationId ? { conversation_id: conversationId } : {}),
    message,
    history: history.slice(-6),
    ...(depth ? { depth } : {}),
  }
  if (!onProgress) return request('/api/chat/', { method: 'POST', body })
  const res = await send('/api/chat/?stream=1', { method: 'POST', body })
  // Errors (401, 404, 503) and an older backend answer plain JSON.
  if (!res.ok || !res.headers.get('Content-Type')?.includes('ndjson')) {
    return readJson(res)
  }
  try {
    for await (const event of ndjsonLines(res)) {
      if (event.type === 'reply') return event.reply
      if (event.type === 'error') throw new ApiError(event.error, 500)
      if (event.text) onProgress(event)
    }
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError('The connection to the coach dropped', 0)
  }
  throw new ApiError('The coach stopped without answering', 0)
}

export async function login(username, password) {
  const body = await request('/api/auth/login/', {
    method: 'POST',
    body: { username, password },
  })
  setToken(body.token)
  return body.user
}

export async function logout() {
  try {
    await request('/api/auth/logout/', { method: 'POST' })
  } catch {
    // Already logged out or backend down: forget the token either way.
  } finally {
    setToken(null)
  }
}
