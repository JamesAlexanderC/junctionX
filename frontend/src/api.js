// API client for the Django backend (contract: CLAUDE.md "API").
//
//   GET  /api/customers/                -> [{customer_id, customer_age, ...}]
//   GET  /api/home/<customer_id>/       -> profile JSON
//   POST /api/chat/  {customer_id, message, history, depth?} -> send_reply
//   POST /api/goals/, PATCH /api/goals/<id>/, POST /api/goals/<id>/rate/
//   POST /api/loans/ {customer_id, balance, interest_rate, years_left}
//   POST /api/alerts/<id>/snooze/ {customer_id, days}
//
// When the backend can't be reached the app runs in demo mode: the profile
// comes from shared/fixtures/profile_demo.json and chat from mock.js.

import demoProfile from '@shared/fixtures/profile_demo.json'
import { MOCK_CUSTOMERS, mockReply } from './mock.js'

const API = import.meta.env.VITE_API_URL ?? ''

export const DEMO_PROFILE = demoProfile

async function request(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`)
    err.status = res.status
    try {
      err.detail = await res.json()
    } catch {
      // body was not JSON
    }
    throw err
  }
  return res.status === 204 ? null : res.json()
}

export async function getCustomers() {
  try {
    const body = await request('/api/customers/')
    const customers = Array.isArray(body) ? body : (body.results ?? [])
    return { customers, demo: false }
  } catch {
    return { customers: MOCK_CUSTOMERS, demo: true }
  }
}

export async function getProfile(customerId) {
  try {
    const profile = await request(`/api/home/${encodeURIComponent(customerId)}/`)
    return { profile, demo: false }
  } catch {
    return { profile: structuredClone(demoProfile), demo: true }
  }
}

// Only the last 6 turns are sent (context.md "Controls").
export async function sendChat({ customerId, message, history, depth, demo, profile }) {
  const body = {
    customer_id: customerId,
    message,
    history: history.slice(-6),
    ...(depth ? { depth } : {}),
  }
  if (demo) return mockReply({ message, depth, profile })
  return request('/api/chat/', { method: 'POST', body })
}

export const createGoal = (goal) =>
  request('/api/goals/', { method: 'POST', body: goal })

export const updateGoal = (id, patch) =>
  request(`/api/goals/${id}/`, { method: 'PATCH', body: patch })

export const rateGoal = (id, body) =>
  request(`/api/goals/${encodeURIComponent(id)}/rate/`, { method: 'POST', body })

export const saveLoan = (loan) =>
  request('/api/loans/', { method: 'POST', body: loan })

export const snoozeAlert = (customerId, alertId, days) =>
  request(`/api/alerts/${encodeURIComponent(alertId)}/snooze/`, {
    method: 'POST',
    body: { customer_id: customerId, days },
  })
