// Saldo: chat-first. Pick a real customer, see the insights the backend
// computed for them, and ask the coach. No demo data, no fallbacks.

import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { getInsights, sendChat } from './api.js'
import Chat from './components/Chat.jsx'
import CustomerPicker from './components/CustomerPicker.jsx'
import Insights from './components/Insights.jsx'

// Chat history in the API's shape: [{role, content}].
const toHistory = (messages) =>
  messages
    .filter((m) => m.role === 'user' || m.reply)
    .map((m) =>
      m.role === 'user'
        ? { role: 'user', content: m.content }
        : { role: 'assistant', content: m.reply.text ?? '' },
    )

export default function App() {
  const [customerId, setCustomerId] = useState(null)
  const [insights, setInsights] = useState([])
  const [insightsError, setInsightsError] = useState(null)
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!customerId) return undefined
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
    return () => ctrl.abort()
  }, [customerId])

  const pickCustomer = (id) => {
    setCustomerId(id)
    setMessages([])
    setInsights([])
    setInsightsError(null)
  }

  const send = useCallback(
    async (text, depth) => {
      if (!customerId || busy) return
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

  return (
    <main className="app">
      <header>
        <h1>Saldo</h1>
        <CustomerPicker value={customerId} onChange={pickCustomer} />
      </header>
      {insightsError && (
        <p className="error" role="alert">
          {insightsError}
        </p>
      )}
      {customerId && <Insights items={insights} onAsk={send} />}
      <Chat messages={messages} busy={busy} onSend={send} disabled={!customerId} />
    </main>
  )
}
