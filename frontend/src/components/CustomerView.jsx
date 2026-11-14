// One customer's view: the insights the backend computed for them, and the
// coach. Layout follows S-mobiili: green top bar, white list sections on grey,
// bottom tabs on phones (Overview / Coach), two columns on wide screens.

import { useCallback, useEffect, useRef, useState } from 'react'
import { getGoals, getInsights, sendChat } from '../api.js'
import Chat from './Chat.jsx'
import Goals from './Goals.jsx'
import Help from './Help.jsx'
import Icon from './Icon.jsx'
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
  ['overview', 'Overview'],
  ['coach', 'Coach'],
]

export default function CustomerView({
  customerId,
  onExit,
  help = false,
  onHelp,
  onCloseHelp,
}) {
  const [insights, setInsights] = useState([])
  const [insightsError, setInsightsError] = useState(null)
  const [goals, setGoals] = useState(null)
  const [goalsError, setGoalsError] = useState(null)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('overview')
  const overviewCtrl = useRef(null)

  // Insights and goals load side by side, so one failing never hides the
  // other. Called on open and after every chat reply: the coach may have
  // added or changed a goal, and the backend has already rebuilt the profile.
  const loadOverview = useCallback(async () => {
    overviewCtrl.current?.abort()
    const ctrl = new AbortController()
    overviewCtrl.current = ctrl
    const [ins, gls] = await Promise.allSettled([
      getInsights(customerId, { signal: ctrl.signal }),
      getGoals(customerId, { signal: ctrl.signal }),
    ])
    if (ctrl.signal.aborted) return
    setInsights(ins.status === 'fulfilled' ? ins.value : [])
    setInsightsError(ins.status === 'rejected' ? ins.reason.message : null)
    setGoals(gls.status === 'fulfilled' ? gls.value : null)
    setGoalsError(gls.status === 'rejected' ? gls.reason.message : null)
    setOverviewLoading(false)
  }, [customerId])

  // The view is keyed on customerId, so this runs once per customer and
  // overviewLoading already starts true.
  useEffect(() => {
    loadOverview()
    return () => overviewCtrl.current?.abort()
  }, [loadOverview])

  const send = useCallback(
    async (text, depth) => {
      if (busy) return
      const history = toHistory(messages)
      setMessages((m) => [...m, { role: 'user', content: text }])
      setBusy(true)
      try {
        const reply = await sendChat({ customerId, message: text, history, depth })
        setMessages((m) => [...m, { role: 'assistant', reply }])
        loadOverview()
      } catch (e) {
        setMessages((m) => [...m, { role: 'assistant', error: e.message }])
      } finally {
        setBusy(false)
      }
    },
    [customerId, busy, messages, loadOverview],
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
              <Icon name="help" size={16} />
              Help
            </button>
            <button
              type="button"
              className="exit"
              aria-label="Exit to demo"
              onClick={onExit}
            >
              <Icon name="close" size={20} />
            </button>
          </div>
        </header>

        <main className="layout">
          <section className="pane overview" aria-label="Overview">
            {[goalsError, insightsError]
              .filter((e, i, all) => e && all.indexOf(e) === i)
              .map((e) => (
                <p key={e} className="error banner" role="alert">
                  <Icon name="error" />
                  {e}
                </p>
              ))}
            {overviewLoading ? (
              <InsightsSkeleton />
            ) : (
              <>
                {goals && <Goals goals={goals} onAsk={ask} />}
                <Insights items={insights} onAsk={ask} />
              </>
            )}
          </section>

          <section className="pane coach" aria-label="Coach">
            <Chat messages={messages} busy={busy} onSend={send} />
          </section>
        </main>

        <nav className="tabbar" aria-label="Sections">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={tab === key ? 'active' : ''}
              aria-current={tab === key ? 'page' : undefined}
              onClick={() => setTab(key)}
            >
              <Icon name={key} size={24} />
              {label}
            </button>
          ))}
        </nav>
      </div>
    </>
  )
}
