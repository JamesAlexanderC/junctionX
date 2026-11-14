// Saldo app shell: phone frame, hash routes (home, explore/<section>, chat,
// alerts, customers), profile loading with demo fallback, chat state.

import { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from './api.js'
import { sortAlerts } from './lib/alerts.js'
import { AppContext } from './lib/context.js'
import { mockReply } from './mock.js'
import Alerts from './screens/Alerts.jsx'
import Chat from './screens/Chat.jsx'
import { SECTIONS } from './lib/sections.js'
import Explore from './screens/Explore.jsx'
import Home from './screens/Home.jsx'
import QuestionsSheet from './screens/QuestionsSheet.jsx'
import './App.css'

function readHash() {
  return window.location.hash.replace(/^#\/?/, '') || 'home'
}

function useHashRoute() {
  const [route, setRoute] = useState(readHash)
  useEffect(() => {
    const onChange = () => setRoute(readHash())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const go = useCallback((r) => {
    window.location.hash = `#/${r}`
    setRoute(r)
  }, [])
  return [route, go]
}

const addDays = (iso, days) => {
  const d = new Date(iso ?? Date.now())
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

const TABS = [
  { id: 'home', label: 'Home', icon: '⌂' },
  { id: 'explore', label: 'Explore', icon: '▤' },
  { id: 'chat', label: 'Coach', icon: '✉' },
  { id: 'alerts', label: 'Alerts', icon: '!' },
]

function titleFor(route) {
  const [base, section] = route.split('/')
  if (base === 'explore') {
    return SECTIONS.find((s) => s.id === section)?.label ?? 'Explore'
  }
  return { home: 'Saldo', chat: 'Money Coach', alerts: 'Alerts', customers: 'Customers' }[
    base
  ] ?? 'Saldo'
}

function CustomerPicker({ customers, onPick }) {
  return (
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
  )
}

export default function App() {
  const [route, go] = useHashRoute()
  const [customers, setCustomers] = useState([])
  const [customer, setCustomer] = useState(null)
  const [profile, setProfile] = useState(null)
  const [demo, setDemo] = useState(false)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [sheet, setSheet] = useState(false)

  useEffect(() => {
    api.getCustomers().then((res) => {
      setCustomers(res.customers)
      setCustomer((c) => c ?? res.customers[0] ?? null)
    })
  }, [])

  const refresh = useCallback(async (id) => {
    const res = await api.getProfile(id)
    setProfile(res.profile)
    setDemo(res.demo)
  }, [])

  useEffect(() => {
    if (customer) refresh(customer.customer_id)
  }, [customer, refresh])

  const send = useCallback(
    async (text, depth) => {
      if (!profile) return
      setDraft('')
      setBusy(true)
      const history = messages
        .filter((m) => !m.pending && !m.error)
        .map((m) =>
          m.role === 'user'
            ? { role: 'user', content: m.content }
            : { role: 'assistant', content: m.reply.text },
        )
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: text },
        { role: 'assistant', pending: true },
      ])
      let reply
      let error = false
      try {
        reply = await api.sendChat({
          customerId: profile.customer_id,
          message: text,
          history,
          depth,
          demo,
          profile,
        })
      } catch (err) {
        if (err.status) {
          error = true
          reply = { text: `Sorry, I couldn't answer that (${err.message}).`, cards: [], chips: [] }
        } else {
          // Network failure: fall back to the local demo coach.
          reply = mockReply({ message: text, depth, profile })
        }
      }
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', reply, animate: true, error },
      ])
      setBusy(false)
    },
    [messages, profile, demo],
  )

  const ask = useCallback(
    (text, { depth, send: now = false } = {}) => {
      go('chat')
      if (now) send(text, depth)
      else setDraft(text)
    },
    [go, send],
  )

  // Optimistic local update; in live mode also call the API and refetch.
  const mutate = useCallback(
    async (apiCall, localUpdate) => {
      if (localUpdate) setProfile((p) => localUpdate(structuredClone(p)))
      if (demo) return
      await apiCall()
      await refresh(customer.customer_id)
    },
    [demo, refresh, customer],
  )

  const actions = useMemo(
    () => ({
      createGoal: (goal) =>
        mutate(
          () => api.createGoal(goal),
          demo &&
            ((p) => {
              p.goals.active.push({
                id: `local-${Date.now()}`,
                saved: 0,
                progress_pct: 0,
                on_track: true,
                start_date: p.today,
                ...goal,
              })
              return p
            }),
        ),
      updateGoal: (id, patch) =>
        mutate(
          () => api.updateGoal(id, patch),
          (p) => {
            p.goals.active = p.goals.active.map((g) => (g.id === id ? { ...g, ...patch } : g))
            return p
          },
        ),
      rate: (goal, rating) =>
        mutate(() => api.rateGoal(goal.id, { rating, goal_type: goal.type }), null),
      saveLoan: (loan) => mutate(() => api.saveLoan(loan), null),
      snooze: (alertId, days) =>
        mutate(
          () => api.snoozeAlert(profile.customer_id, alertId, days),
          (p) => {
            p.alerts = p.alerts.map((a) =>
              a.id === alertId ? { ...a, snoozed_until: addDays(p.today, days) } : a,
            )
            return p
          },
        ).catch(() => {}),
      dismissDetected: (id) =>
        setProfile((p) => {
          const next = structuredClone(p)
          next.goals.detected = next.goals.detected.filter((d) => d.id !== id)
          if (next.goals.recommended?.id === id) next.goals.recommended = null
          return next
        }),
    }),
    [mutate, demo, profile],
  )

  const ctx = useMemo(
    () => ({ profile, demo, ask, go, actions }),
    [profile, demo, ask, go, actions],
  )

  const [base, section] = route.split('/')
  const alertCount = profile ? sortAlerts(profile.alerts, profile.today).length : 0

  let screen
  if (!profile) {
    screen = <p className="muted center pad">Loading your numbers…</p>
  } else if (base === 'explore') {
    screen = <Explore section={section} />
  } else if (base === 'chat') {
    screen = (
      <Chat
        messages={messages}
        busy={busy}
        draft={draft}
        setDraft={setDraft}
        onSend={send}
        demo={demo}
      />
    )
  } else if (base === 'alerts') {
    screen = <Alerts />
  } else if (base === 'customers') {
    screen = (
      <CustomerPicker
        customers={customers}
        onPick={(c) => {
          setMessages([])
          setCustomer(c)
          go('home')
        }}
      />
    )
  } else {
    screen = <Home onSeeAllQuestions={() => setSheet(true)} />
  }

  return (
    <AppContext.Provider value={ctx}>
      <div className="app">
        <header className="app-bar">
          {base !== 'home' && (
            <button type="button" className="back" aria-label="Back" onClick={() => go('home')}>
              ‹
            </button>
          )}
          <div>
            <h1>{titleFor(route)}</h1>
            {customer && (
              <button type="button" className="link small" onClick={() => go('customers')}>
                Customer {customer.customer_id}
                {demo ? ' · demo' : ''}
              </button>
            )}
          </div>
        </header>
        <main className={`screen screen-${base}`}>{screen}</main>
        <nav className="tabbar" aria-label="Main">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={base === t.id ? 'active' : ''}
              aria-current={base === t.id ? 'page' : undefined}
              onClick={() => go(t.id === 'explore' ? `explore/${section ?? 'baskets'}` : t.id)}
            >
              <span aria-hidden="true">{t.icon}</span>
              {t.label}
              {t.id === 'alerts' && alertCount > 0 && <b className="badge">{alertCount}</b>}
            </button>
          ))}
        </nav>
        {sheet && <QuestionsSheet onClose={() => setSheet(false)} />}
      </div>
    </AppContext.Provider>
  )
}
