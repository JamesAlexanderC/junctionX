// API client for the Django backend (contract: CLAUDE.md "API").
//
//   GET  /api/customers/?q=<search>   -> [{customer_id, customer_age, ...}]
//   GET  /api/insights/<customer_id>/  -> [{key, inference, title, value,
//                                          unit, text, section, severity?}]
//   POST /api/chat/ {customer_id, message, history, depth?} -> send_reply
//
// There is no offline or demo fallback: every error is shown as is.

const API = import.meta.env.VITE_API_URL ?? ''

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
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
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
  if (!res.ok) {
    if (res.status >= 502 && res.status <= 504 && !data) {
      throw new ApiError('Backend not reachable', res.status)
    }
    const msg = data?.error ?? data?.detail ?? `Request failed (HTTP ${res.status})`
    throw new ApiError(msg, res.status)
  }
  return data
}

export async function getCustomers(q = '', { signal } = {}) {
  const query = q ? `?q=${encodeURIComponent(q)}` : ''
  const body = await request(`/api/customers/${query}`, { signal })
  return Array.isArray(body) ? body : (body?.results ?? [])
}

export async function getInsights(customerId, { signal } = {}) {
  const body = await request(`/api/insights/${encodeURIComponent(customerId)}/`, {
    signal,
  })
  // Backend shape: {customer_id, as_of, insights: [...]} (CLAUDE.md "API").
  if (Array.isArray(body)) return body
  return Array.isArray(body?.insights) ? body.insights : []
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
