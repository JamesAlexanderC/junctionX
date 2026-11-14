import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import demoProfile from '@shared/fixtures/profile_demo.json'
import App from '../App.jsx'
import { ReplyCard } from '../components/Cards.jsx'
import { sortAlerts, topNudgeAlert } from '../lib/alerts.js'
import { AppContext } from '../lib/context.js'
import Alerts from '../screens/Alerts.jsx'
import Chat from '../screens/Chat.jsx'
import Home from '../screens/Home.jsx'

const ALERTS = [
  { id: 'blue-1', inference: 92, severity: 'blue', title: 'Similar subscriptions', text: 'b', priority: 0.033 },
  { id: 'amber-30', inference: 52, severity: 'amber', title: 'Goal off track', text: 'a', priority: 0.067 },
  { id: 'red-1', inference: 99, severity: 'red', title: 'Low balance now', text: 'r', priority: 3 },
  { id: 'amber-5', inference: 20, severity: 'amber', title: 'Danger days', text: 'd', priority: 0.4 },
]

function withCtx(ui, { profile = demoProfile, ...rest } = {}) {
  const value = {
    profile,
    demo: true,
    ask: vi.fn(),
    go: vi.fn(),
    actions: {},
    ...rest,
  }
  return { ...render(<AppContext.Provider value={value}>{ui}</AppContext.Provider>), value }
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

describe('cards', () => {
  it('unknown card type renders nothing', () => {
    const { container } = withCtx(<ReplyCard card={{ type: 'hologram', value: 1 }} />)
    expect(container.innerHTML).toBe('')
  })

  it('plan card shows "clears N alerts" per step', () => {
    withCtx(
      <ReplyCard
        card={{
          type: 'plan',
          steps: [
            { text: 'Cut takeaways', monthly_impact: 58, clears: ['a', 'b', 'c'] },
            { text: 'Keep one subscription', monthly_impact: 11, clears: ['d'] },
          ],
        }}
      />,
    )
    expect(screen.getByText(/clears 3 alerts/)).toBeTruthy()
    expect(screen.getByText(/clears 1 alert$/)).toBeTruthy()
  })

  it('slider card recomputes #24 locally', () => {
    withCtx(
      <ReplyCard
        card={{ type: 'slider', category: 'takeaway', monthly_spend: 90, pct: 20 }}
      />,
    )
    expect(screen.getByTestId('monthly-saving').textContent).toBe('€18')
    expect(screen.getByTestId('yearly-saving').textContent).toBe('€216')
    fireEvent.change(screen.getByRole('slider'), { target: { value: '50' } })
    expect(screen.getByTestId('monthly-saving').textContent).toBe('€45')
  })
})

describe('chat', () => {
  it('a tapped chip sends its text and depth', async () => {
    const onSend = vi.fn()
    withCtx(
      <Chat
        messages={[
          { role: 'user', content: 'What is safe to spend?' },
          {
            role: 'assistant',
            reply: { text: 'EUR 64.', depth: 2, cards: [], chips: ['Show me why', 'What can I do?'] },
          },
        ]}
        busy={false}
        draft=""
        setDraft={() => {}}
        onSend={onSend}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Show me why' }))
    expect(onSend).toHaveBeenCalledWith('Show me why', 3)
    expect(screen.getByTestId('depth-badge').textContent).toBe('Explain')
  })
})

describe('alerts', () => {
  it('sorts by priority, red first', () => {
    expect(sortAlerts(ALERTS).map((a) => a.id)).toEqual([
      'red-1',
      'amber-5',
      'amber-30',
      'blue-1',
    ])
  })

  it('inbox renders alerts in priority order', () => {
    withCtx(<Alerts />, { profile: { ...demoProfile, alerts: ALERTS } })
    const titles = screen
      .getAllByTestId('alert-row')
      .map((row) => row.querySelector('strong').textContent)
    expect(titles).toEqual(['Low balance now', 'Danger days', 'Goal off track', 'Similar subscriptions'])
  })

  it('home nudge shows only the top red or amber alert', () => {
    withCtx(<Home onSeeAllQuestions={() => {}} />, {
      profile: { ...demoProfile, alerts: ALERTS },
    })
    const nudges = screen.getAllByTestId('nudge')
    expect(nudges).toHaveLength(1)
    expect(within(nudges[0]).getByText('Low balance now')).toBeTruthy()
    expect(screen.queryByText('Danger days')).toBeNull()
  })

  it('nudge ignores blue alerts and falls back to a detected goal', () => {
    expect(topNudgeAlert(demoProfile.alerts, demoProfile.today)).toBeNull()
    withCtx(<Home onSeeAllQuestions={() => {}} />)
    expect(within(screen.getByTestId('nudge')).getByText(/Looks like you're saving/)).toBeTruthy()
  })

  it('"Fix this" asks the coach to fix that alert', () => {
    const { value } = withCtx(<Alerts />, { profile: { ...demoProfile, alerts: ALERTS } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Fix this' })[0])
    expect(value.ask).toHaveBeenCalledWith('Help me fix this alert: Low balance now', {
      depth: 4,
      send: true,
    })
  })
})

describe('app', () => {
  it('home renders from profile_demo.json with the API off', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))))
    render(<App />)
    expect(await screen.findByText('Safe to spend this week')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Safe to spend: €64/ })).toBeTruthy()
    expect(screen.getByText('Your four baskets')).toBeTruthy()
    expect(screen.getAllByText(/Japan trip/).length).toBeGreaterThan(0)
  })
})
