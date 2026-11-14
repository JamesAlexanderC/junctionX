import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App.jsx'
import { ReplyCard } from '../components/Cards.jsx'
import Chat from '../components/Chat.jsx'
import Insights from '../components/Insights.jsx'
import { niceTicks, shortLabel } from '../lib/chart.js'

afterEach(() => {
  vi.unstubAllGlobals()
  window.location.hash = ''
})

describe('cards', () => {
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

describe('no fallbacks', () => {
  it('API down shows "Backend not reachable" and no customers', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    render(<App />)
    expect((await screen.findByRole('alert')).textContent).toContain('Backend not reachable')
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1) // only "Pick a customer"
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('a 503 from chat shows the backend error text', async () => {
    const fetch = vi.fn(async (url) => {
      if (url.startsWith('/api/customers/')) {
        return new Response(JSON.stringify([{ customer_id: 'CUST00001' }]), { status: 200 })
      }
      if (url.startsWith('/api/insights/')) {
        return new Response('[]', { status: 200 })
      }
      return new Response(JSON.stringify({ error: 'Gemini is not configured' }), {
        status: 503,
      })
    })
    vi.stubGlobal('fetch', fetch)
    render(<App />)
    await screen.findByRole('option', { name: /CUST00001/ })
    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: 'CUST00001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open customer view' }))
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
    expect(status.querySelectorAll('.typing span')).toHaveLength(3)
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
})

describe('demo landing page', () => {
  const fetchOk = () =>
    vi.fn(async (url) =>
      url.startsWith('/api/customers/')
        ? new Response(JSON.stringify([{ customer_id: 'CUST00001' }]))
        : new Response('[]', { status: 200 }),
    )

  it('a #/c/<id> link opens the customer view directly', async () => {
    vi.stubGlobal('fetch', fetchOk())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    expect(await screen.findByText('CUST00001')).toBeTruthy()
    expect(screen.getByLabelText('Message')).toBeTruthy()
    expect(screen.queryByLabelText('Customer')).toBeNull()
  })

  it('the exit button returns to the landing page', async () => {
    vi.stubGlobal('fetch', fetchOk())
    window.location.hash = '#/c/CUST00001'
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Exit to demo' }))
    expect(await screen.findByLabelText('Customer')).toBeTruthy()
    const open = screen.getByRole('button', { name: 'Open customer view' })
    expect(open.disabled).toBe(true)
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
})
