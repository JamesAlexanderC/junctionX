// One customer's view: the insights the backend computed for them, and the
// coach. Layout follows S-mobiili: green top bar, white list sections on grey,
// bottom tabs on phones (Overview / Coach), two columns on wide screens.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  disconnectBank,
  getAccounts,
  getGoals,
  getInsights,
  getSpending,
  sendChat,
} from '../api.js'
import Accounts, { PartialViewBanner } from './Accounts.jsx'
import ConnectBank from './ConnectBank.jsx'
import Spending from './Spending.jsx'
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
  const [conversationId] = useState(() => crypto.randomUUID())
  const [insights, setInsights] = useState([])
  const [insightsError, setInsightsError] = useState(null)
  const [goals, setGoals] = useState(null)
  const [goalsError, setGoalsError] = useState(null)
  const [spending, setSpending] = useState(null)
  const [spendingError, setSpendingError] = useState(null)
  const [accounts, setAccounts] = useState(null)
  const [connecting, setConnecting] = useState(false)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  // What the coach is doing right now: {step, thought} from the stream.
  const [progress, setProgress] = useState({})
  const [tab, setTab] = useState('overview')
  const overviewCtrl = useRef(null)

  // Insights, goals and spending load side by side, so one failing never hides
  // the other. Called on open and after a reply that changed state (a goal or
  // plan written): the backend has already rebuilt the profile.
  const loadOverview = useCallback(async () => {
    overviewCtrl.current?.abort()
    const ctrl = new AbortController()
    overviewCtrl.current = ctrl
    const [ins, gls, spd, acc] = await Promise.allSettled([
      getInsights(customerId, { signal: ctrl.signal }),
      getGoals(customerId, { signal: ctrl.signal }),
      getSpending(customerId, { signal: ctrl.signal }),
      getAccounts(customerId, { signal: ctrl.signal }),
    ])
    if (ctrl.signal.aborted) return
    // A failed refresh keeps the last good data on screen beside the error.
    if (ins.status === 'fulfilled') setInsights(ins.value)
    setInsightsError(ins.status === 'rejected' ? ins.reason.message : null)
    if (gls.status === 'fulfilled') setGoals(gls.value)
    setGoalsError(gls.status === 'rejected' ? gls.reason.message : null)
    if (spd.status === 'fulfilled') setSpending(spd.value)
    setSpendingError(spd.status === 'rejected' ? spd.reason.message : null)
    // Accounts are optional (simulated PSD2): if they fail, the rest still shows.
    if (acc.status === 'fulfilled') setAccounts(acc.value)
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
      setProgress({})
      const onProgress = (e) => setProgress((p) => ({ ...p, [e.type]: e.text }))
      try {
        const reply = await sendChat({
          customerId,
          message: text,
          history,
          depth,
          conversationId,
          onProgress,
        })
        setMessages((m) => [...m, { role: 'assistant', reply }])
        if (reply.state_changed) loadOverview()
      } catch (e) {
        setMessages((m) => [...m, { role: 'assistant', error: e.message }])
      } finally {
        setBusy(false)
      }
    },
    [customerId, busy, messages, conversationId, loadOverview],
  )

  const disconnect = useCallback(
    async (consentId) => {
      try {
        await disconnectBank(consentId)
      } finally {
        loadOverview()
      }
    },
    [loadOverview],
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
            {[goalsError, spendingError, insightsError]
              .filter((e, i, all) => e && all.indexOf(e) === i)
              .map((e) => (
                <p key={e} className="error banner" role="alert">
                  <Icon name="error" />
                  {e}{' '}
                  <button type="button" onClick={loadOverview}>
                    Retry Overview
                  </button>
                </p>
              ))}
            <PartialViewBanner
              coverage={accounts?.coverage}
              onConnect={() => setConnecting(true)}
            />
            {overviewLoading ? (
              <InsightsSkeleton />
            ) : (
              <>
                {goals && <Goals goals={goals} onAsk={ask} />}
                {spending && <Spending spending={spending} onAsk={ask} />}
                <Insights items={insights} onAsk={ask} />
                <Accounts
                  data={accounts}
                  onDisconnect={disconnect}
                  onConnect={() => setConnecting(true)}
                />
              </>
            )}
          </section>

          <section className="pane coach" aria-label="Coach">
            <Chat
              messages={messages}
              busy={busy}
              progress={progress}
              onSend={send}
              onConnect={() => setConnecting(true)}
            />
          </section>
        </main>

        {connecting && (
          <ConnectBank
            customerId={customerId}
            onClose={() => setConnecting(false)}
            onConnected={loadOverview}
          />
        )}

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
