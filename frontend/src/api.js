// API client for the Django backend (contract: CLAUDE.md "API").
//
//   GET  /api/customers/?q=<search>   -> [{customer_id, customer_age, ...}]
//   GET  /api/insights/<customer_id>/  -> [{key, inference, title, value,
//                                          unit, text, section, severity?}]
//   GET  /api/goals/?customer_id=<id> -> {active, completed, clash}
//   GET  /api/baskets/?customer_id=<id> -> {month, total, buckets, ...}
//   POST /api/chat/ {customer_id, message, history, depth?} -> send_reply
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

async function request(path, { method = 'GET', body, signal } = {}) {
  let res
  try {
    res = await fetch(`${API}${path}`, {
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

// Backend shape: {customer_id, as_of, month, total, buckets: [{key, name,
// total, share, trend, categories: [{category, total}]}], monthly_essentials,
// monthly_saving}.
export async function getBaskets(customerId, { signal } = {}) {
  const body = await request(
    `/api/baskets/?customer_id=${encodeURIComponent(customerId)}`,
    { signal },
  )
  return {
    month: body?.month ?? null,
    total: body?.total ?? 0,
    buckets: Array.isArray(body?.buckets) ? body.buckets : [],
    monthly_essentials: body?.monthly_essentials ?? null,
    monthly_saving: body?.monthly_saving ?? null,
  }
}

// Only the last 6 turns are sent (context.md "Controls").
export function sendChat({ customerId, message, history = [], depth }) {
  return request('/api/chat/', {
    method: 'POST',
    body: {
      customer_id: customerId,
      message,
      history: history.slice(-6),
      ...(depth ? { depth } : {}),
    },
  })
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
