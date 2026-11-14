// Coach chat. State lives in useConversations (App) so it survives tab
// switches; this screen only renders it and drives the composer.

import { useEffect, useLayoutEffect, useRef } from 'react'
import AppBar from '../components/AppBar.jsx'
import Icon from '../components/Icon.jsx'
import Message from '../components/Message.jsx'
import { ProviderBadge } from '../components/ui.jsx'

const STARTERS = [
  'What is safe to spend this week?',
  'Show my spending by basket',
  'How much did I spend on taxis last month?',
  'What if I cut dining out by 20%?',
  'What kind of spender am I?',
  'Am I ready to buy a home?',
]

const BASKETS = [
  ['b1', 'Must-pay bills', 'rent, groceries, utilities, subscriptions'],
  ['b2', 'Surprise essentials', 'dentist, a new laptop, a trip home'],
  ['b3', 'Everyday leakage', 'coffee, takeaway, taxis, nights out'],
]

function Welcome({ onSend }) {
  return (
    <div className="welcome">
      <span className="welcome-mark" aria-hidden="true">
        <Icon name="sparkle" size={26} />
      </span>
      <h2>Hi! I'm your Money Coach.</h2>
      <p>
        Ask me anything about your money. I look at your real transactions and
        sort every expense into three baskets:
      </p>
      <ol className="baskets">
        {BASKETS.map(([cls, label, hint]) => (
          <li key={cls}>
            <b className={`dot ${cls}`} aria-hidden="true" />
            <strong>{label}</strong>
            <small>{hint}</small>
          </li>
        ))}
      </ol>
      <h3 className="mini-title">Try asking</h3>
      <div className="starter-grid">
        {STARTERS.map((s) => (
          <button key={s} type="button" className="starter" onClick={() => onSend(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

function Composer({ value, onChange, onSend, onStop, busy, inputRef }) {
  // Auto-grow the textarea up to ~5 lines.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`
  }, [value, inputRef])

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault()
        onSend(value)
      }}
    >
      <textarea
        ref={inputRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            onSend(value)
          }
        }}
        placeholder="Ask about your money…"
        aria-label="Message the coach"
        enterKeyHint="send"
      />
      {busy ? (
        <button
          type="button"
          className="send-btn stop"
          onClick={onStop}
          aria-label="Stop answering"
        >
          <Icon name="stop" size={16} strokeWidth={3} />
        </button>
      ) : (
        <button
          type="submit"
          className="send-btn"
          disabled={!value.trim()}
          aria-label="Send"
        >
          <Icon name="send" size={20} strokeWidth={2.5} />
        </button>
      )}
    </form>
  )
}

export default function ChatScreen({ customer, mode, convo, actions, onBack }) {
  const id = customer.customer_id
  const { messages, busy, draft } = convo
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  const stick = useRef(true)

  const send = (text) => {
    if (busy || !text.trim()) return
    stick.current = true
    actions.send(id, text, messages)
  }

  // Focus the input when arriving with a pre-filled question.
  useEffect(() => {
    const el = inputRef.current
    if (el && draft) {
      el.focus()
      el.setSelectionRange(el.value.length, el.value.length)
    }
    // Only on mount: later draft edits come from the user typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Follow the stream, unless the user scrolled up to read.
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && stick.current && messages.length) el.scrollTop = el.scrollHeight
  }, [messages])

  const onScroll = () => {
    const el = scrollRef.current
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const last = messages[messages.length - 1]
  const followUps = !busy && last?.role === 'assistant' ? (last.suggestions ?? []) : []
  const liveText = last?.role === 'assistant'
    ? last.pending
      ? last.content
        ? ''
        : (last.tools?.at(-1)?.label ?? 'Coach is thinking')
      : last.content
    : ''

  return (
    <main className="screen chat" id="main">
      <AppBar
        title="Money Coach"
        subtitle={id}
        onBack={onBack}
        backLabel="Back to customers"
        right={
          <ProviderBadge
            demo={mode?.demo}
            provider={convo.provider ?? mode?.health?.llm?.provider}
            model={convo.model ?? mode?.health?.llm?.model}
            tiny
          />
        }
      />

      <section
        className="messages"
        ref={scrollRef}
        onScroll={onScroll}
        aria-label="Conversation"
      >
        {messages.length === 0 && <Welcome onSend={send} />}
        {messages.map((m, i) => (
          <Message key={i} msg={m} />
        ))}
        {followUps.length > 0 && (
          <div className="follow-ups" aria-label="Suggested follow-up questions">
            {followUps.map((s) => (
              <button key={s} type="button" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
      </section>
      <p className="sr-only" aria-live="polite">
        {liveText}
      </p>

      <Composer
        value={draft}
        onChange={(v) => actions.setDraft(id, v)}
        onSend={send}
        onStop={() => actions.stop(id)}
        busy={busy}
        inputRef={inputRef}
      />
    </main>
  )
}
