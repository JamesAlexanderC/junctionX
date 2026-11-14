// One customer's view: the insights the backend computed for them, and the
// coach. Layout follows S-mobiili: green top bar, white list sections on grey,
// bottom tabs on phones (Overview / Coach), two columns on wide screens.

import { useCallback, useEffect, useState } from 'react'
import { getInsights, sendChat } from '../api.js'
import Chat from './Chat.jsx'
import Insights, { InsightsSkeleton } from './Insights.jsx'

// Chat history in the API's shape: [{role, content}].
const toHistory = (messages) =>
  messages
    .filter((m) => m.role === 'user' || m.reply)
    .map((m) =>
      m.role === 'user'
        ? { role: 'user', content: m.content }
        : { role: 'assistant', content: m.reply.text ?? '' },
    )

const TABS = [
  ['overview', 'Overview', 'M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z'],
  ['coach', 'Coach', 'M4 5h16v11H8l-4 4z'],
]

export default function CustomerView({ customerId, onExit }) {
  const [insights, setInsights] = useState([])
  const [insightsError, setInsightsError] = useState(null)
  const [insightsLoading, setInsightsLoading] = useState(true)
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('overview')

  // The view is keyed on customerId, so this runs once per customer and
  // insightsLoading already starts true.
  useEffect(() => {
    const ctrl = new AbortController()
    getInsights(customerId, { signal: ctrl.signal })
      .then((items) => {
        setInsights(items)
        setInsightsError(null)
      })
      .catch((e) => {
        if (e?.name === 'AbortError') return
        setInsights([])
        setInsightsError(e.message)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setInsightsLoading(false)
      })
    return () => ctrl.abort()
  }, [customerId])

  const send = useCallback(
    async (text, depth) => {
      if (busy) return
      const history = toHistory(messages)
      setMessages((m) => [...m, { role: 'user', content: text }])
      setBusy(true)
      try {
        const reply = await sendChat({ customerId, message: text, history, depth })
        setMessages((m) => [...m, { role: 'assistant', reply }])
      } catch (e) {
        setMessages((m) => [...m, { role: 'assistant', error: e.message }])
      } finally {
        setBusy(false)
      }
    },
    [customerId, busy, messages],
  )

  // Tapping an insight asks the coach, so on phones jump to the Coach tab.
  const ask = (text, depth) => {
    setTab('coach')
    send(text, depth)
  }

  return (
    <div className="app" data-tab={tab}>
      <header className="topbar">
        <div className="topbar-inner">
          <span className="logo" aria-hidden="true">
            S
          </span>
          <h1>Saldo</h1>
          <span className="who">{customerId}</span>
          <button
            type="button"
            className="exit"
            aria-label="Exit to demo"
            onClick={onExit}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
      </header>

      <main className="layout">
        <section className="pane overview" aria-label="Overview">
          {insightsError && (
            <p className="error banner" role="alert">
              {insightsError}
            </p>
          )}
          {insightsLoading ? (
            <InsightsSkeleton />
          ) : (
            <Insights items={insights} onAsk={ask} />
          )}
        </section>

        <section className="pane coach" aria-label="Coach">
          <Chat messages={messages} busy={busy} onSend={send} />
        </section>
      </main>

      <nav className="tabbar" aria-label="Sections">
        {TABS.map(([key, label, icon]) => (
          <button
            key={key}
            type="button"
            className={tab === key ? 'active' : ''}
            aria-current={tab === key ? 'page' : undefined}
            onClick={() => setTab(key)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d={icon} />
            </svg>
            {label}
          </button>
        ))}
      </nav>
    </div>
  )
}
