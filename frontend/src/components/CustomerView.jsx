// One customer's view: the insights the backend computed for them, and the
// coach. Layout follows S-mobiili: green top bar, white list sections on grey,
// bottom tabs on phones (Overview / Coach), two columns on wide screens.

import { useCallback, useEffect, useState } from 'react'
import { getInsights, sendChat } from '../api.js'
import Chat from './Chat.jsx'
import Help from './Help.jsx'
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

export default function CustomerView({
  customerId,
  onExit,
  help = false,
  onHelp,
  onCloseHelp,
}) {
  const [conversationId] = useState(() => crypto.randomUUID())
  const [revision, setRevision] = useState(0)
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
        if (ctrl.signal.aborted) return
        setInsights(items)
        setInsightsError(null)
      })
      .catch((e) => {
        if (e?.name === 'AbortError') return
        setInsightsError(e.message)
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setInsightsLoading(false)
      })
    return () => ctrl.abort()
  }, [customerId, revision])

  const send = useCallback(
    async (text, depth) => {
      if (busy) return
      const history = toHistory(messages)
      setMessages((m) => [...m, { role: 'user', content: text }])
      setBusy(true)
      try {
        const reply = await sendChat({
          customerId, message: text, history, depth, conversationId,
        })
        setMessages((m) => [...m, { role: 'assistant', reply }])
        if (reply.state_changed) setRevision((r) => r + 1)
      } catch (e) {
        setMessages((m) => [...m, { role: 'assistant', error: e.message }])
      } finally {
        setBusy(false)
      }
    },
    [customerId, busy, messages, conversationId],
  )

  // Tapping an insight asks the coach, so on phones jump to the Coach tab.
  const ask = (text, depth) => {
    setTab('coach')
    send(text, depth)
  }

  return (
    <>
      {help && (
        <Help
          onBack={onCloseHelp}
          onAsk={(text, depth) => {
            onCloseHelp()
            ask(text, depth)
          }}
        />
      )}
      {/* Hidden, not unmounted, under the help page so the chat is kept. */}
      <div
        className="app"
        data-tab={tab}
        style={help ? { display: 'none' } : undefined}
      >
        <header className="topbar">
          <div className="topbar-inner">
            {/* Logo and name go back to the demo landing page. */}
            <a className="home" href="#/" aria-label="Saldo home">
              <span className="logo" aria-hidden="true">
                S
              </span>
              <h1>Saldo</h1>
            </a>
            <span className="who">{customerId}</span>
            <button type="button" className="logout" onClick={onHelp}>
              Help
            </button>
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
                {insightsError}{' '}
                <button type="button" onClick={() => setRevision((r) => r + 1)}>
                  Retry Overview
                </button>
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
    </>
  )
}
