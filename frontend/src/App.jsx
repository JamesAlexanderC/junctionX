import { useEffect, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getCustomers, streamChat } from './api.js'
import './App.css'

const SUGGESTIONS = [
  'How much did I spend on taxis last month?',
  'Show my spending by basket',
  'What is safe to spend this week?',
  'What if I cut dining out by 20%?',
  'What kind of spender am I?',
  'Am I ready to buy a home?',
]

// Basket colours first, so pie charts of the three baskets match the legend.
const COLORS = [
  'var(--b1)',
  'var(--b2)',
  'var(--b3)',
  '#00aa46',
  '#91fa9b',
  '#5f6b66',
]

const formatValue = (value, unit) =>
  unit === '€'
    ? `€${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })}`
    : `${Number(value).toLocaleString('en-US')}${unit ? ` ${unit}` : ''}`

// ---------- Text rendering (tiny markdown subset: **bold**, "- " lists) ----

function Inline({ text }) {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : (
        part
      ),
    )
}

function RichText({ text }) {
  return text
    .trim()
    .split(/\n{2,}/)
    .map((block, i) => {
      const lines = block.split('\n')
      if (lines.every((l) => /^\s*[-*] /.test(l))) {
        return (
          <ul key={i}>
            {lines.map((l, j) => (
              <li key={j}>
                <Inline text={l.replace(/^\s*[-*] /, '')} />
              </li>
            ))}
          </ul>
        )
      }
      return (
        <p key={i}>
          {lines.map((l, j) => (
            <span key={j}>
              {j > 0 && <br />}
              <Inline text={l} />
            </span>
          ))}
        </p>
      )
    })
}

// ---------- Charts ---------------------------------------------------------

function ChartCard({ chart }) {
  const { kind = 'bar', title, unit, data = [] } = chart
  if (!data.length) return null
  const tooltip = <Tooltip formatter={(v) => formatValue(v, unit)} />
  const axisProps = { tick: { fontSize: 12 }, tickLine: false, axisLine: false }

  let body
  if (kind === 'pie') {
    body = (
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          innerRadius="50%"
          outerRadius="80%"
          paddingAngle={2}
        >
          {data.map((d, i) => (
            <Cell key={d.label} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        {tooltip}
        <Legend
          iconType="circle"
          wrapperStyle={{ fontSize: 12 }}
          formatter={(v) => <span style={{ color: 'var(--body)' }}>{v}</span>}
        />
      </PieChart>
    )
  } else if (kind === 'line') {
    body = (
      <LineChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} width={48} />
        {tooltip}
        <Line
          type="monotone"
          dataKey="value"
          stroke="var(--accent)"
          strokeWidth={2.5}
          dot={{ r: 3 }}
        />
      </LineChart>
    )
  } else {
    body = (
      <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} width={48} />
        {tooltip}
        <Bar dataKey="value" fill="var(--accent)" radius={[4, 4, 0, 0]} />
      </BarChart>
    )
  }

  return (
    <figure className="chart-card">
      {title && <figcaption>{title}</figcaption>}
      <div className="chart-body">
        <ResponsiveContainer width="100%" height="100%">
          {body}
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

// ---------- Messages -------------------------------------------------------

function Message({ msg }) {
  if (msg.role === 'user') {
    return <div className="bubble user">{msg.content}</div>
  }
  const waiting = msg.pending && !msg.content
  return (
    <div className="assistant">
      <div className={`bubble coach${msg.error ? ' error' : ''}`}>
        {waiting ? (
          <span className="typing" aria-label="Coach is thinking">
            <i />
            <i />
            <i />
          </span>
        ) : (
          <RichText text={msg.content} />
        )}
      </div>
      {msg.charts?.map((c, i) => (
        <ChartCard key={i} chart={c} />
      ))}
      {msg.concepts?.map((c, i) => (
        <aside key={i} className="concept">
          <strong>💡 {c.title}</strong>
          <p>{c.text}</p>
        </aside>
      ))}
    </div>
  )
}

// ---------- Screens --------------------------------------------------------

function CustomerPicker({ customers, demo, loading, onPick }) {
  return (
    <main className="picker">
      <header className="app-bar">
        <h1>Money Coach</h1>
      </header>
      <p className="intro">
        Chat with your own banking data. Pick a customer to start.
      </p>
      {demo && <DemoBanner />}
      <h2 className="section-title">Customers</h2>
      {loading ? (
        <p className="muted center">Loading customers…</p>
      ) : (
        <ul className="customer-list">
          {customers.map((c) => (
            <li key={c.customer_id}>
              <button type="button" onClick={() => onPick(c)}>
                <span className="avatar">{c.customer_age ?? '?'}</span>
                <span>
                  <strong>Customer {c.customer_id}</strong>
                  <small>
                    {c.customer_postal_code && `Postal code ${c.customer_postal_code}`}
                  </small>
                </span>
                <span className="chevron">›</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}

function DemoBanner() {
  return (
    <div className="demo-banner">
      Demo mode: backend not reachable, showing made-up sample answers.
    </div>
  )
}

function Chat({ customer, demo, onBack }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const abortRef = useRef(null)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  // Apply an update to the last (assistant) message.
  const patchLast = (fn) =>
    setMessages((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1])])

  async function send(text) {
    const question = text.trim()
    if (!question || busy) return
    setInput('')
    setBusy(true)

    const history = [
      ...messages
        .filter((m) => !m.error && m.content)
        .map(({ role, content }) => ({ role, content })),
      { role: 'user', content: question },
    ]
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '', pending: true, charts: [], concepts: [] },
    ])

    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamChat({
        customerId: customer.customer_id,
        messages: history,
        demo,
        signal: controller.signal,
        onEvent: (ev) => {
          if (ev.type === 'token') {
            patchLast((m) => ({ ...m, content: m.content + ev.text }))
          } else if (ev.type === 'chart' && ev.chart) {
            patchLast((m) => ({ ...m, charts: [...m.charts, ev.chart] }))
          } else if (ev.type === 'concept') {
            const concept = { title: ev.title, text: ev.text }
            patchLast((m) => ({ ...m, concepts: [...m.concepts, concept] }))
          } else if (ev.type === 'error') {
            throw new Error(ev.message || 'Something went wrong')
          }
        },
      })
    } catch (err) {
      if (err.name !== 'AbortError') {
        patchLast((m) => ({
          ...m,
          error: true,
          content: `Sorry, I couldn't answer that. ${err.message}`,
        }))
      }
    } finally {
      patchLast((m) => ({ ...m, pending: false }))
      setBusy(false)
    }
  }

  return (
    <main className="chat">
      <header className="app-bar">
        <button type="button" className="back" onClick={onBack} aria-label="Back">
          ‹
        </button>
        <div>
          <h1>Money Coach</h1>
          <small>Customer {customer.customer_id}</small>
        </div>
      </header>
      {demo && <DemoBanner />}

      <section className="messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="welcome">
            <h2>Hey! 👋</h2>
            <p>
              Ask me anything about your money. I sort every expense into three
              baskets:
            </p>
            <h3 className="section-title">Your three baskets</h3>
            <ol className="baskets">
              <li>
                <b className="dot b1" /> <strong>Must-pay bills</strong>
                <small>rent, insurance, subscriptions</small>
              </li>
              <li>
                <b className="dot b2" /> <strong>Surprise essentials</strong>
                <small>car repair, dentist, broken washer</small>
              </li>
              <li>
                <b className="dot b3" /> <strong>Everyday leakage</strong>
                <small>coffee, takeaway, taxis</small>
              </li>
            </ol>
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} msg={m} />
        ))}
        <div ref={endRef} />
      </section>

      <footer className="composer">
        {messages.length === 0 && (
          <div className="chips">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your money…"
            aria-label="Message"
          />
          <button type="submit" disabled={busy || !input.trim()} aria-label="Send">
            ↑
          </button>
        </form>
      </footer>
    </main>
  )
}

// ---------- App ------------------------------------------------------------

function App() {
  const [customers, setCustomers] = useState([])
  const [demo, setDemo] = useState(false)
  const [loading, setLoading] = useState(true)
  const [customer, setCustomer] = useState(null)

  useEffect(() => {
    getCustomers().then((res) => {
      setCustomers(res.customers)
      setDemo(res.demo)
      setLoading(false)
    })
  }, [])

  return customer ? (
    <Chat
      key={customer.customer_id}
      customer={customer}
      demo={demo}
      onBack={() => setCustomer(null)}
    />
  ) : (
    <CustomerPicker
      customers={customers}
      demo={demo}
      loading={loading}
      onPick={setCustomer}
    />
  )
}

export default App
