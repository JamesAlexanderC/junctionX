import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import CustomerView from '../components/CustomerView.jsx'

const insight = (title) => ({
  insights: [{ key: 'goal', title, text: title, section: 'goals' }],
})
const json = (data, status = 200) => new Response(JSON.stringify(data), { status })
const EMPTY_GOALS = { active: [], completed: [], clash: null }
const EMPTY_SPENDING = { month: null, total: 0, categories: [], savings: [] }
// Goals and spending load beside insights; only insights reads are counted.
const otherPanel = (url) => {
  if (url.startsWith('/api/goals/')) return json(EMPTY_GOALS)
  if (url.startsWith('/api/spending/')) return json(EMPTY_SPENDING)
  return null
}
afterEach(() => vi.unstubAllGlobals())

it('refreshes after a write, preserves old insights on failure and can retry', async () => {
  let reads = 0
  const ids = []
  const fetch = vi.fn(async (url, init) => {
    if (url.startsWith('/api/chat/')) {
      ids.push(JSON.parse(init.body).conversation_id)
      return json({ text: 'Saved.', depth: 4, cards: [], state_changed: true })
    }
    const other = otherPanel(url)
    if (other) return other
    reads += 1
    if (reads === 2) return json({ error: 'Refresh failed' }, 503)
    return json(insight(reads === 1 ? 'Old goal' : 'New goal'))
  })
  vi.stubGlobal('fetch', fetch)
  render(<CustomerView customerId="CUST1" />)
  await screen.findByText('Old goal', { selector: '.ins-title' })
  const send = () => {
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Save goal' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  }
  send()
  await screen.findByRole('button', { name: 'Retry Overview' })
  expect(screen.getByText('Old goal', { selector: '.ins-title' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Retry Overview' }))
  await screen.findByText('New goal', { selector: '.ins-title' })
  send()
  await waitFor(() => expect(ids).toHaveLength(2))
  expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/)
  expect(ids[1]).toBe(ids[0])
})

it('does not refresh for a read-only reply', async () => {
  let reads = 0
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    if (url.startsWith('/api/chat/')) {
      return json({ text: 'Hello.', depth: 1, cards: [], state_changed: false })
    }
    const other = otherPanel(url)
    if (other) return other
    reads += 1
    return json(insight('Current goal'))
  }))
  render(<CustomerView customerId="CUST1" />)
  await screen.findByText('Current goal', { selector: '.ins-title' })
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Hello' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  await screen.findByText('Hello.')
  expect(reads).toBe(1)
})
