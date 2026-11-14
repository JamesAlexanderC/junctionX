import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App.jsx'
import { ReplyCard } from '../components/Cards.jsx'
import Chat from '../components/Chat.jsx'
import Goals from '../components/Goals.jsx'
import Insights from '../components/Insights.jsx'
import Spending from '../components/Spending.jsx'
import { niceTicks, shortLabel } from '../lib/chart.js'
import { SUGGESTIONS } from '../lib/suggestions.js'

const NO_GOALS = { customer_id: 'CUST00001', active: [], completed: [], clash: null }
const NO_SPENDING = { customer_id: 'CUST00001', month: null, total: 0, categories: [] }

// Test-only shape of GET /api/customers/demo/.
const LEVEL_NAMES = ['Not started', 'Getting started', 'In control', 'Safety net']
const row = (n, spender) => ({
  customer_id: `CUST0000${n}`,
  income_level: n,
  income_label: `Income ${n}`,
  spender_type: spender,
  level: n - 1,
  level_name: LEVEL_NAMES[n - 1],
})
const SPENDERS = ['Night Owl', 'Payday Splurger', 'Balanced']
const DEMO = {
  built: true,
  demos: SPENDERS.map((t, i) => ({
    demo: i + 1,
    customer_id: `CUST0000${i + 1}`,
    level: i,
    level_name: LEVEL_NAMES[i],
    income_level: i + 1,
    income_label: `Income ${i + 1}`,
    spender_type: t,
  })),
  customers: [...SPENDERS, 'Weekend Treater'].map((t, i) => row(i + 1, t)),
}

// Every App test starts logged in unless it clears the token itself.
beforeEach(() => localStorage.setItem('saldo.token', 'test-token'))

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
  localStorage.clear()
})

describe('cards', () => {
  it('uses the backend reference date for slider goal projections', () => {
    render(<ReplyCard card={{
      type: 'slider', category: 'takeaway', monthly_spend: 100, pct: 20,
      as_of: '2026-09-30', goal: { target: 100, saved: 0, monthly_rate: 80 },
    }} />)
    expect(screen.getByText(/Goal date: 30 October 2026/)).toBeTruthy()
  })

  it('does not invent a date for an older slider without a reference date', () => {
    render(<ReplyCard card={{
      type: 'slider', category: 'takeaway', monthly_spend: 100, pct: 20,
      goal: { target: 100, saved: 0, monthly_rate: 80 },
    }} />)
    expect(screen.queryByText(/Goal date:/)).toBeNull()
  })
  it('unknown card type renders nothing', () => {
    const { container } = render(<ReplyCard card={{ type: 'hologram' }} onSend={() => {}} />)
    expect(container.innerHTML).toBe('')
  })

  it('slider recomputes #24 locally', () => {
    render(
      <ReplyCard
        card={{ type: 'slider', category: 'takeaway', monthly_spend: 90, pct: 20 }}
        onSend={() => {}}
      />,
    )
    expect((screen.getByTestId('monthly-saving')).textContent).toContain('€18')
    expect((screen.getByTestId('yearly-saving')).textContent).toContain('€216')
  })

  it('slider reads a 0-1 fraction as percent and can be dragged', () => {
    render(
      <ReplyCard
        card={{ type: 'slider', category: 'restaurants', monthly_spend: 370.95, pct: 0.2 }}
        onSend={() => {}}
      />,
    )
    const slider = screen.getByRole('slider')
    expect(slider.value).toBe('20')
    expect(screen.getByTestId('monthly-saving').textContent).toContain('€74.19')
    fireEvent.change(slider, { target: { value: '30' } })
    expect(screen.getByText('30%')).toBeTruthy()
    expect(screen.getByTestId('monthly-saving').textContent).toContain('€111.29')
  })

  it('plan card shows clears N alerts', () => {
    render(
      <ReplyCard
        card={{
          type: 'plan',
          steps: [{ text: 'Cut takeaway 20%', monthly_impact: 58, clears: ['a', 'b', 'c'] }],
        }}
        onSend={() => {}}
      />,
    )
    expect(screen.getByText(/clears 3 alerts/)).toBeTruthy()
  })

  it('a plan can be accepted only once', () => {
    const onSend = vi.fn()
    render(
      <ReplyCard
        card={{
          type: 'plan',
          steps: [{ text: 'Cut takeaway 20%', monthly_impact: 18, clears: [] }],
        }}
        onSend={onSend}
      />,
    )
    const button = screen.getByRole('button', { name: /Accept plan/ })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith('Accept plan', 4)
    const done = screen.getByRole('button', { name: /Plan accepted/ })
    expect(done.disabled).toBe(true)
  })

  it('slider has a button that sends the chosen cut to the coach', () => {
    const onSend = vi.fn()
    render(
      <ReplyCard
        card={{ type: 'slider', category: 'takeaway', monthly_spend: 90, pct: 20 }}
        onSend={onSend}
      />,
    )
    fireEvent.change(screen.getByRole('slider'), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: /Cut takeaway by 25%/ }))
    expect(onSend).toHaveBeenCalledWith(
      'Save cutting takeaway by 25% as my plan (€22.50 a month)',
      4,
    )
    expect(screen.getByRole('button', { name: /Sent to the coach/ }).disabled).toBe(true)
    // Moving the slider again allows sending the new amount.
    fireEvent.change(screen.getByRole('slider'), { target: { value: '30' } })
    expect(screen.getByRole('button', { name: /Cut takeaway by 30%/ }).disabled).toBe(false)
  })

  it('slider button is off at 0%', () => {
    render(
      <ReplyCard
        card={{ type: 'slider', category: 'takeaway', monthly_spend: 90, pct: 0 }}
        onSend={() => {}}
      />,
    )
    fireEvent.change(screen.getByRole('slider'), { target: { value: '0' } })
    expect(screen.getByRole('button', { name: /Cut takeaway by 0%/ }).disabled).toBe(true)
  })
})

describe('chat', () => {
  it('chip tap sends its text and the next depth', () => {
    const onSend = vi.fn()
    const messages = [
      { role: 'user', content: 'Safe to spend?' },
      { role: 'assistant', reply: { text: 'EUR 64', depth: 1, cards: [], chips: ['Show me why'] } },
    ]
    render(<Chat messages={messages} busy={false} onSend={onSend} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show me why' }))
    expect(onSend).toHaveBeenCalledWith('Show me why', 2)
    expect((screen.getByTestId('depth-badge')).textContent).toContain('Quick')
  })
})

describe('insights panel', () => {
  const items = [
    { key: 'payday', inference: 1, title: 'Next payday', value: '2026-10-15', unit: null, text: 'In 3 days', section: 'income' },
    { key: 'a-85', inference: 85, title: 'Overdraft', value: -42.5, unit: 'EUR', text: 'Balance went below zero', section: 'alerts', severity: 'red' },
  ]

  it('renders exactly the returned items', () => {
    render(<Insights items={items} onAsk={() => {}} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Next payday')).toBeTruthy()
    expect(screen.getByText('-€42.50')).toBeTruthy()
  })

  it('renders nothing when empty', () => {
    const { container } = render(<Insights items={[]} onAsk={() => {}} />)
    expect(container.innerHTML).toBe('')
  })

  it('tapping an insight asks about it', () => {
    const onAsk = vi.fn()
    render(<Insights items={items} onAsk={onAsk} />)
    fireEvent.click(screen.getByText('Overdraft'))
    expect(onAsk).toHaveBeenCalledWith('Tell me about my overdraft', 2)
  })
})

describe('goals panel', () => {
  const bike = {
    id: 7,
    name: 'Bike',
    emoji: null,
    target: 300,
    saved: 60,
    progress_pct: 20,
    expected_pct: 10,
    on_track: true,
    paused: false,
    target_date: '2027-03-01',
    difficulty: 'Easy',
    monthly_needed: 50,
    realistic: true,
    tip: null,
  }
  const goals = (active, extra = {}) => ({ ...NO_GOALS, active, ...extra })

  it('shows the backend numbers for each goal', () => {
    render(<Goals goals={goals([bike])} onAsk={() => {}} />)
    expect(screen.getByText('Bike')).toBeTruthy()
    expect(screen.getByText('20%')).toBeTruthy()
    expect(screen.getByText(/€60 of €300 · by 1 March 2027/)).toBeTruthy()
    expect(screen.getByText(/€50 a month needed · on track/)).toBeTruthy()
  })

  it('shows behind, the realistic amount, the tip and a clash', () => {
    const late = {
      ...bike,
      on_track: false,
      realistic: false,
      suggested_monthly: 30,
      suggested_date: '2027-09-01',
      tip: { text: 'Cut takeaway by 20% to catch up', shortfall: 12 },
    }
    const clash = { clash: true, total_needed: 50, safe_to_save_monthly: 30 }
    render(<Goals goals={goals([late], { clash })} onAsk={() => {}} />)
    expect(screen.getByText(/· behind/)).toBeTruthy()
    expect(screen.getByText(/Realistic: €30 a month, done by 1 September 2027/))
      .toBeTruthy()
    expect(screen.getByText('Cut takeaway by 20% to catch up')).toBeTruthy()
    expect(screen.getByText(/need €50 a month/)).toBeTruthy()
  })

  it('empty state and tapping ask the coach', () => {
    const onAsk = vi.fn()
    const { rerender } = render(<Goals goals={goals([])} onAsk={onAsk} />)
    fireEvent.click(screen.getByText('No goals yet'))
    expect(onAsk).toHaveBeenCalledWith('Help me set a goal', 2)
    rerender(<Goals goals={goals([bike])} onAsk={onAsk} />)
    fireEvent.click(screen.getByText('Bike'))
    expect(onAsk).toHaveBeenCalledWith('Tell me about my Bike goal', 2)
  })

  it('reloads goals after a chat reply', async () => {
    let created = false
    const fetch = vi.fn(async (url) => {
      if (url.startsWith('/api/insights/')) return new Response('[]')
      if (url.startsWith('/api/spending/')) return new Response(JSON.stringify(NO_SPENDING))
      if (url.startsWith('/api/goals/')) {
        return new Response(JSON.stringify(goals(created ? [bike] : [])))
      }
      created = true
      return new Response(
        JSON.stringify({ text: 'Goal added', depth: 1, state_changed: true }),
      )
    })
    vi.stubGlobal('fetch', fetch)
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    expect(await screen.findByText('No goals yet')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'yes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Bike')).toBeTruthy()
    expect(screen.queryByText('No goals yet')).toBeNull()
  })

  it('a goals error is shown while insights still render', async () => {
    const items = [
      { key: 'payday', title: 'Next payday', value: null, text: 'Soon', section: 'income' },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) =>
        url.startsWith('/api/goals/')
          ? new Response(JSON.stringify({ detail: 'Goals broke' }), { status: 500 })
          : new Response(JSON.stringify({ insights: items })),
      ),
    )
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    expect((await screen.findByRole('alert')).textContent).toContain('Goals broke')
    expect(screen.getByText('Next payday')).toBeTruthy()
  })
})

describe('spending panel', () => {
  const housing = {
    category: 'Housing',
    total: 650,
    share: 61.2,
    count: 1,
    usual: 650,
    vs_usual: 0,
  }
  const groceries = {
    category: 'Home & Tech',
    total: 412.5,
    share: 38.8,
    count: 3,
    usual: 380,
    vs_usual: 32.5,
  }
  const spending = (categories) => ({
    ...NO_SPENDING,
    month: '2026-10',
    total: 1062.5,
    categories,
  })

  it('shows each data category with its share and total', () => {
    render(<Spending spending={spending([housing, groceries])} onAsk={() => {}} />)
    expect(screen.getByText('Spending by category (2026-10)')).toBeTruthy()
    expect(screen.getByText('Housing')).toBeTruthy()
    expect(screen.getByText('Home & Tech')).toBeTruthy()
    expect(screen.getByText('61%')).toBeTruthy()
    expect(screen.getByText(/€650 · 1 payment$/)).toBeTruthy()
    expect(screen.getByText(/· 3 payments$/)).toBeTruthy()
  })

  it('shows each category against its usual month', () => {
    const fresh = { category: 'Travel', total: 90, share: 10, count: 1, usual: null }
    const s = { ...spending([housing, groceries, fresh]), is_current: true }
    render(<Spending spending={s} onAsk={() => {}} />)
    expect(screen.getByText('Usually €650 a month · about the same')).toBeTruthy()
    expect(screen.getByText('Usually €380 a month · €32.50 more so far')).toBeTruthy()
    expect(screen.getAllByText(/^Usually/)).toHaveLength(2) // none for Travel
  })

  it('lists savings apart, labelled and outside the total', () => {
    const s = {
      ...spending([housing]),
      savings: [{ category: 'Invest Deposit', total: 235.72, count: 1 }],
      savings_total: 235.72,
    }
    render(<Spending spending={s} onAsk={() => {}} />)
    const saved = screen.getByRole('list', { name: 'Savings' })
    expect(saved.textContent).toContain('Invest Deposit')
    expect(saved.textContent).toContain('Savings')
    expect(screen.getByText(/not counted as spending/)).toBeTruthy()
    expect(screen.getByText('Total spent: €1,062.50')).toBeTruthy()
  })

  it('empty state and tapping ask the coach', () => {
    const onAsk = vi.fn()
    const { rerender } = render(<Spending spending={spending([])} onAsk={onAsk} />)
    expect(screen.getByText('No spending this month yet')).toBeTruthy()
    rerender(<Spending spending={spending([housing])} onAsk={onAsk} />)
    fireEvent.click(screen.getByText('Housing'))
    expect(onAsk).toHaveBeenCalledWith('Tell me about my Housing spending', 2)
  })

  it('loads categories in the customer view', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        if (url.startsWith('/api/spending/')) {
          return new Response(JSON.stringify(spending([housing])))
        }
        if (url.startsWith('/api/goals/')) return new Response(JSON.stringify(NO_GOALS))
        return new Response('[]')
      }),
    )
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    expect(await screen.findByText('Housing')).toBeTruthy()
  })
})

describe('no fallbacks', () => {
  it('API down shows "Backend not reachable" and no customers', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    render(<App />)
    expect((await screen.findByRole('alert')).textContent).toContain('Backend not reachable')
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('a 503 from chat shows the backend error text', async () => {
    const fetch = vi.fn(async (url) => {
      if (url.startsWith('/api/customers/demo/')) {
        return new Response(JSON.stringify(DEMO), { status: 200 })
      }
      if (url.startsWith('/api/insights/')) {
        return new Response('[]', { status: 200 })
      }
      if (url.startsWith('/api/goals/')) {
        return new Response(JSON.stringify(NO_GOALS), { status: 200 })
      }
      if (url.startsWith('/api/spending/')) {
        return new Response(JSON.stringify(NO_SPENDING), { status: 200 })
      }
      return new Response(JSON.stringify({ error: 'Gemini is not configured' }), {
        status: 503,
      })
    })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /Demo 1/ }))
    const input = await screen.findByLabelText('Message')
    fireEvent.change(input, { target: { value: 'Hi' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() =>
      expect((screen.getByRole('alert')).textContent).toContain('Gemini is not configured'),
    )
  })
})

describe('waiting for a reply (F2)', () => {
  afterEach(() => vi.useRealTimers())

  it('shows progress text that changes the longer it takes', () => {
    vi.useFakeTimers()
    render(<Chat messages={[]} busy onSend={() => {}} />)
    const status = screen.getByRole('status')
    expect(status.querySelector('.typing')).toBeNull()
    expect(status.textContent).toBe('Checking your numbers…')
    act(() => vi.advanceTimersByTime(5000))
    expect(status.textContent).toBe('Looking deeper into your data…')
    act(() => vi.advanceTimersByTime(7000))
    expect(status.textContent).toBe('Putting your answer together…')
  })

  it('shows nothing when not waiting', () => {
    render(<Chat messages={[]} busy={false} onSend={() => {}} />)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows the step the coach is on and its thought heading', () => {
    render(
      <Chat
        messages={[]}
        busy
        progress={{ step: 'Checking your goals', thought: 'Planning the answer' }}
        onSend={() => {}}
      />,
    )
    const status = screen.getByRole('status')
    expect(status.textContent).toBe('Checking your goals…Planning the answer')
  })

  // A chat response whose NDJSON lines the test pushes one at a time.
  function streamingApi() {
    let ctrl
    const body = new ReadableStream({ start: (c) => (ctrl = c) })
    const enc = new TextEncoder()
    const push = (...events) =>
      ctrl.enqueue(enc.encode(events.map((e) => JSON.stringify(e) + '\n').join('')))
    const fetch = vi.fn(async (url) =>
      url.startsWith('/api/chat/')
        ? new Response(body, { headers: { 'Content-Type': 'application/x-ndjson' } })
        : new Response('[]'),
    )
    return { fetch, push, close: () => ctrl.close() }
  }

  async function ask() {
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    fireEvent.change(await screen.findByLabelText('Message'), {
      target: { value: 'Safe to spend?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  }

  it('streams what the coach is doing, then shows the reply', async () => {
    const api = streamingApi()
    vi.stubGlobal('fetch', api.fetch)
    await ask()
    api.push(
      { type: 'step', text: 'Working out what is safe to spend' },
      { type: 'thought', text: 'Weighing upcoming bills' },
    )
    expect(await screen.findByText('Working out what is safe to spend…')).toBeTruthy()
    expect(screen.getByText('Weighing upcoming bills')).toBeTruthy()
    api.push({
      type: 'reply',
      reply: { text: 'EUR 64', depth: 1, cards: [], chips: [] },
    })
    api.close()
    expect(await screen.findByText('EUR 64')).toBeTruthy()
    expect(screen.queryByRole('status')).toBeNull()
    const [url] = api.fetch.mock.calls.find(([u]) => u.startsWith('/api/chat/'))
    expect(url).toBe('/api/chat/?stream=1')
  })

  it('an error event in the stream is shown as the reply', async () => {
    const api = streamingApi()
    vi.stubGlobal('fetch', api.fetch)
    await ask()
    api.push({ type: 'error', error: 'The coach stopped unexpectedly.' })
    api.close()
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('stopped unexpectedly'),
    )
  })
})

describe('demo landing page', () => {
  const fetchOk = () =>
    vi.fn(async (url) =>
      url.startsWith('/api/customers/demo/')
        ? new Response(JSON.stringify(DEMO))
        : new Response('[]', { status: 200 }),
    )

  it('demo buttons name the demo, level, income and spender type', async () => {
    vi.stubGlobal('fetch', fetchOk())
    render(<App />)
    const list = await screen.findByRole('list', { name: 'Demo customers' })
    const rows = list.querySelectorAll('li')
    expect(rows).toHaveLength(3)
    expect(rows[0].textContent).toBe('Demo 1Level 0: Not startedIncome 1 · Night Owl')
    expect(list.textContent).not.toContain('CUST')
    fireEvent.click(screen.getByRole('button', { name: /Demo 2/ }))
    expect(window.location.hash).toBe('#/c/CUST00002')
  })

  it('every customer is listed with their tags, and opens on tap', async () => {
    vi.stubGlobal('fetch', fetchOk())
    render(<App />)
    const all = await screen.findByRole('list', { name: 'All customers' })
    expect(all.querySelectorAll('li')).toHaveLength(4)
    expect(all.textContent).toContain(
      'CUST00004Safety net · Income 4 · Weekend Treater',
    )
    expect(screen.queryByLabelText('Search customer')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /CUST00004/ }))
    expect(window.location.hash).toBe('#/c/CUST00004')
  })

  it('says so when the index is not built', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"built": false}')))
    render(<App />)
    expect(await screen.findByText(/build_customer_index/)).toBeTruthy()
  })

  it('the logo in the customer view goes back to the landing page', async () => {
    vi.stubGlobal('fetch', fetchOk())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    const home = await screen.findByRole('link', { name: 'Saldo home' })
    expect(home.getAttribute('href')).toBe('#/')
    window.location.hash = '#/'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    expect(await screen.findByRole('list', { name: 'Demo customers' })).toBeTruthy()
  })

  it('a #/c/<id> link opens the customer view directly', async () => {
    vi.stubGlobal('fetch', fetchOk())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    expect(await screen.findByText('CUST00001')).toBeTruthy()
    expect(screen.getByLabelText('Message')).toBeTruthy()
    expect(screen.queryByRole('list', { name: 'Demo customers' })).toBeNull()
  })

  it('the exit button returns to the landing page', async () => {
    vi.stubGlobal('fetch', fetchOk())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Exit to demo' }))
    expect(await screen.findByRole('list', { name: 'Demo customers' })).toBeTruthy()
  })
})

describe('chart card', () => {
  const bars = {
    type: 'chart',
    kind: 'bar',
    title: 'Spending by basket this month',
    unit: 'EUR',
    data: [
      { label: 'essential', value: 890 },
      { label: 'leaky', value: 172.99 },
      { label: 'saver', value: 150 },
    ],
  }

  it('draws one column per point and tapping shows the exact value', () => {
    const { container } = render(<ReplyCard card={bars} onSend={() => {}} />)
    expect(container.querySelectorAll('path.col')).toHaveLength(3)
    fireEvent.click(screen.getAllByTestId('chart-hit')[1])
    const readout = screen.getByTestId('chart-readout').textContent
    expect(readout).toContain('Leaky')
    expect(readout).toContain('€172.99')
  })

  it('arrow keys move the selection', () => {
    render(<ReplyCard card={bars} onSend={() => {}} />)
    const svg = screen.getByRole('img')
    fireEvent.keyDown(svg, { key: 'ArrowRight' })
    expect(screen.getByTestId('chart-readout').textContent).toContain('€890')
    fireEvent.keyDown(svg, { key: 'ArrowRight' })
    expect(screen.getByTestId('chart-readout').textContent).toContain('€172.99')
  })

  it('draws a line chart with an end dot', () => {
    const card = {
      type: 'chart',
      kind: 'line',
      title: 'Expected balance until payday',
      unit: 'EUR',
      data: [
        { label: '2026-10-19', value: 486 },
        { label: '2026-10-20', value: 450 },
      ],
    }
    const { container } = render(<ReplyCard card={card} onSend={() => {}} />)
    expect(container.querySelector('path.line')).toBeTruthy()
    expect(container.querySelector('circle.dot')).toBeTruthy()
    fireEvent.click(screen.getAllByTestId('chart-hit')[0])
    expect(screen.getByTestId('chart-readout').textContent).toContain('19 October 2026')
  })

  it('named categories draw horizontal bars with full names; months draw columns', () => {
    const named = {
      ...bars,
      data: ['leaky', 'other', 'saver', 'surprise', 'essential'].map((label) => ({
        label,
        value: 100,
      })),
    }
    const { container, unmount } = render(<ReplyCard card={named} onSend={() => {}} />)
    const names = [...container.querySelectorAll('text.name')].map((t) => t.textContent)
    expect(names).toEqual(['Leaky', 'Other', 'Saver', 'Surprise', 'Essential'])
    unmount()
    const months = {
      ...bars,
      data: ['2026-08', '2026-09'].map((label) => ({ label, value: 100 })),
    }
    const view = render(<ReplyCard card={months} onSend={() => {}} />)
    expect(view.container.querySelectorAll('text.name')).toHaveLength(0)
    expect(view.container.querySelectorAll('path.col')).toHaveLength(2)
  })

  it('category bars hide zero rows but keep them in the table', () => {
    const card = {
      ...bars,
      data: [
        { label: 'surprise', value: 0 },
        { label: 'essential', value: 2039.87 },
      ],
    }
    const { container } = render(<ReplyCard card={card} onSend={() => {}} />)
    const names = [...container.querySelectorAll('text.name')].map((t) => t.textContent)
    expect(names).toEqual(['Essential'])
    expect(screen.getAllByRole('row')).toHaveLength(2)
  })

  // FC-2: the forecast chart carries an 80% band and flagged days.
  const forecast = {
    type: 'chart',
    kind: 'line',
    title: 'Expected balance (likely range)',
    unit: 'EUR',
    data: [
      { label: '2026-10-01', value: 900, low: 850, high: 950 },
      { label: '2026-10-02', value: 170, low: 60, high: 280, flag: 'bill' },
      { label: '2026-10-08', value: 90, low: 20, high: 160, flag: 'danger' },
      { label: '2026-10-15', value: 2000, low: 1880, high: 2120, flag: 'payday' },
    ],
  }

  it('draws the likely range as a band under the line', () => {
    const { container } = render(<ReplyCard card={forecast} onSend={() => {}} />)
    expect(container.querySelector('path.band')).toBeTruthy()
    expect(container.querySelector('path.line')).toBeTruthy()
    expect(container.querySelector('text.band-label').textContent).toBe('likely range')
  })

  it('a plain line has no band', () => {
    const plain = { ...forecast, data: forecast.data.map(({ label, value }) => ({ label, value })) }
    const { container } = render(<ReplyCard card={plain} onSend={() => {}} />)
    expect(container.querySelector('path.band')).toBeNull()
  })

  it('marks danger, bill and payday days', () => {
    const { container } = render(<ReplyCard card={forecast} onSend={() => {}} />)
    expect(container.querySelectorAll('circle.marker.danger')).toHaveLength(1)
    expect(container.querySelectorAll('circle.marker.bill')).toHaveLength(1)
    expect(container.querySelectorAll('circle.marker.payday')).toHaveLength(1)
  })

  it('tapping a point shows its likely range and what the day is', () => {
    render(<ReplyCard card={forecast} onSend={() => {}} />)
    fireEvent.click(screen.getAllByTestId('chart-hit')[2])
    const readout = screen.getByTestId('chart-readout').textContent
    expect(readout).toContain('€90')
    expect(readout).toContain('likely €20 to €160')
    expect(readout).toContain('Tight day')
  })

  it('every value is in the screen-reader table', () => {
    render(<ReplyCard card={bars} onSend={() => {}} />)
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })

  it('ticks are clean steps that cover the data', () => {
    expect(niceTicks(0, 890)).toEqual([0, 250, 500, 750, 1000])
    expect(shortLabel('2026-07')).toBe('Jul')
    expect(shortLabel('2026-10-19')).toBe('19 Oct')
  })
})

describe('level card', () => {
  it('shows the ladder with reached and next levels', () => {
    const card = {
      type: 'level_progress',
      level: 3,
      name: 'Safety net',
      progress: 0.5,
      euros_to_go: 445,
      next_step: 'Cut takeaway by 20% (about EUR 18 a month)',
      ladder: [
        { level: 1, name: 'Getting started', reached: true },
        { level: 2, name: 'In control', reached: true },
        { level: 3, name: 'Safety net', reached: false },
        { level: 4, name: 'Goal setter', reached: false },
        { level: 5, name: 'Mortgage ready', reached: false },
        { level: 6, name: 'Wealth builder', reached: false },
      ],
    }
    const { container } = render(<ReplyCard card={card} onSend={() => {}} />)
    expect(container.querySelectorAll('.ladder li.reached')).toHaveLength(2)
    expect(screen.getByLabelText('Level 3 Safety net, next')).toBeTruthy()
    expect(screen.getByText(/€445 to go/)).toBeTruthy()
  })

  it('says what the next level needs and what is done', () => {
    const card = {
      type: 'level_progress',
      level: 6,
      name: 'Wealth builder',
      progress: 0.4,
      requirement: {
        text: 'Keep 3 months of essentials as a buffer and save 10% of income.',
        checks: [
          { text: 'Buffer: 1.2 of 3 months', met: false },
          { text: 'Saved 10% of income in 3 of the last 3 months', met: true },
        ],
      },
    }
    render(<ReplyCard card={card} onSend={() => {}} />)
    expect(screen.getByText(/Keep 3 months of essentials/)).toBeTruthy()
    const list = screen.getByRole('list', { name: 'What this level needs' })
    expect(list.querySelector('li.todo').textContent).toContain('Buffer: 1.2 of 3 months')
    expect(list.querySelector('li.met').textContent).toContain('(done)')
  })
})

describe('auth', () => {
  const json = (body, status = 200) =>
    new Response(JSON.stringify(body), { status })

  it('without a token the login screen shows, and logging in opens the demo customers', async () => {
    localStorage.clear()
    const fetch = vi.fn(async (url) => {
      if (url === '/api/auth/login/') {
        return json({ token: 'abc', user: { username: 'demo' } })
      }
      return json(DEMO)
    })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'demo' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    await screen.findByRole('button', { name: /Demo 1/ })
    expect(localStorage.getItem('saldo.token')).toBe('abc')
    const [, init] = fetch.mock.calls.find(([url]) => url.startsWith('/api/customers/demo/'))
    expect(init.headers.Authorization).toBe('Token abc')
  })

  it('wrong credentials show the backend error', async () => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ error: 'Wrong username or password' }, 400)),
    )
    render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'demo' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect((await screen.findByRole('alert')).textContent).toContain(
      'Wrong username or password',
    )
  })

  it('a 401 forgets the token and returns to the login screen', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'Invalid token.' }, 401)))
    render(<App />)
    expect(await screen.findByLabelText('Username')).toBeTruthy()
    expect(localStorage.getItem('saldo.token')).toBeNull()
  })

  it('log out returns to the login screen', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) =>
        url === '/api/auth/logout/' ? new Response(null, { status: 204 }) : json([]),
      ),
    )
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    expect(await screen.findByLabelText('Username')).toBeTruthy()
    expect(localStorage.getItem('saldo.token')).toBeNull()
  })
})

describe('chat suggestions', () => {
  it('an empty chat offers one starter per feature and sends it with its depth', () => {
    const onSend = vi.fn()
    render(<Chat messages={[]} busy={false} onSend={onSend} />)
    const list = screen.getByRole('list', { name: 'Suggested questions' })
    expect(list.querySelectorAll('button')).toHaveLength(SUGGESTIONS.length)
    fireEvent.click(screen.getByRole('button', { name: /chart of where my money went/ }))
    expect(onSend).toHaveBeenCalledWith(
      'Show me a chart of where my money went this month',
      2,
    )
  })

  it('no suggestions once the chat has messages, or with no customer', () => {
    const { rerender } = render(
      <Chat messages={[{ role: 'user', content: 'Hi' }]} busy={false} onSend={() => {}} />,
    )
    expect(screen.queryByRole('list', { name: 'Suggested questions' })).toBeNull()
    rerender(<Chat messages={[]} busy={false} onSend={() => {}} disabled />)
    expect(screen.queryByRole('list', { name: 'Suggested questions' })).toBeNull()
  })
})

describe('help page', () => {
  const api = () =>
    vi.fn(async (url) => {
      if (url.startsWith('/api/chat/')) {
        return new Response(
          JSON.stringify({ text: 'EUR 64', depth: 1, cards: [], chips: [] }),
        )
      }
      return new Response('[]')
    })

  it('the landing page has no Help button', () => {
    vi.stubGlobal('fetch', api())
    render(<App />)
    expect(screen.queryByRole('button', { name: 'Help' })).toBeNull()
  })

  it('Help sits left of the exit button in the customer view', async () => {
    vi.stubGlobal('fetch', api())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    const help = await screen.findByRole('button', { name: 'Help' })
    const exit = screen.getByRole('button', { name: 'Exit to demo' })
    expect(help.nextElementSibling).toBe(exit)
    fireEvent.click(help)
    expect(await screen.findByRole('heading', { name: 'Charts' })).toBeTruthy()
    expect(window.location.hash).toBe('#/c/CUST00001/help')
  })

  it('Back returns to the same customer with the chat kept', async () => {
    vi.stubGlobal('fetch', api())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    fireEvent.change(await screen.findByLabelText('Message'), {
      target: { value: 'Safe to spend?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await screen.findByText('EUR 64')
    fireEvent.click(screen.getByRole('button', { name: 'Help' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Back' }))
    await waitFor(() => expect(window.location.hash).toBe('#/c/CUST00001'))
    expect(screen.getByText('EUR 64')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Charts' })).toBeNull()
  })

  it('a Try asking question closes help and asks the coach', async () => {
    const fetch = api()
    vi.stubGlobal('fetch', fetch)
    window.location.hash = '#/c/CUST00001/help'
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /How can I save more/ }))
    await screen.findByText('EUR 64')
    expect(window.location.hash).toBe('#/c/CUST00001')
    const [, init] = fetch.mock.calls.find(([url]) => url.startsWith('/api/chat/'))
    expect(JSON.parse(init.body)).toMatchObject({ message: 'How can I save more?', depth: 3 })
  })

  it('the help page needs a login like every other page', () => {
    localStorage.clear()
    window.location.hash = '#/c/CUST00001/help'
    render(<App />)
    expect(screen.getByLabelText('Username')).toBeTruthy()
  })
})

describe('level card (FC-7)', () => {
  it('shows the current level and the next one', () => {
    const card = {
      type: 'level_progress',
      level: 3,
      name: 'Safety net',
      current_level: 2,
      current_name: 'In control',
      progress: 0,
    }
    render(<ReplyCard card={card} onSend={() => {}} />)
    expect(screen.getByText('Level 2: In control')).toBeTruthy()
    expect(screen.getByText('Next: Level 3 Safety net')).toBeTruthy()
  })
})

describe('alert card button', () => {
  const alert = { type: 'alert', id: 'a-101', severity: 'amber', title: 'Bill went up', text: 'x' }

  it('a fixable alert offers Fix this', () => {
    const onSend = vi.fn()
    render(<ReplyCard card={{ ...alert, fixable: true }} onSend={onSend} />)
    fireEvent.click(screen.getByRole('button', { name: 'Fix this' }))
    expect(onSend).toHaveBeenCalledWith('Help me fix the "Bill went up" alert', 4)
  })

  it('an alert no plan can fix offers Why? instead, so it cannot loop', () => {
    const onSend = vi.fn()
    render(<ReplyCard card={{ ...alert, fixable: false }} onSend={onSend} />)
    expect(screen.queryByRole('button', { name: 'Fix this' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Why?' }))
    expect(onSend).toHaveBeenCalledWith('Why did I get the "Bill went up" alert?', 2)
  })
})
