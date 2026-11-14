// Chat: user bubbles, coach replies (send_reply), cards, depth badge, chips.

import { useEffect, useRef, useState } from 'react'
import { DEPTH_NAMES } from '../lib/format.js'
import { ReplyCard } from './Cards.jsx'

const nextDepth = (d) => Math.min(4, (d ?? 1) + 1)

function CoachMessage({ reply, onSend, isLast }) {
  return (
    <div className="msg coach">
      <div className="msg-head">
        <span className="coach-name">Saldo coach</span>
        {reply.depth && (
          <span className="depth" data-testid="depth-badge">
            {DEPTH_NAMES[reply.depth]}
          </span>
        )}
      </div>
      <p className="text">{reply.text}</p>
      {(reply.cards ?? []).map((card, i) => (
        <ReplyCard key={i} card={card} onSend={onSend} />
      ))}
      {isLast && reply.chips?.length > 0 && (
        <div className="chips">
          {reply.chips.slice(0, 3).map((c) => (
            <button key={c} type="button" onClick={() => onSend(c, nextDepth(reply.depth))}>
              {c}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Chat({ messages, busy, onSend, disabled }) {
  const [draft, setDraft] = useState('')
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  return (
    <section className="chat">
      <div className="messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-empty">
            <span className="logo big" aria-hidden="true">
              S
            </span>
            <p>
              {disabled
                ? 'Pick a customer, then ask the coach anything about their money.'
                : 'Ask about spending, saving, goals or alerts.'}
            </p>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="msg user">
              {m.content}
            </div>
          ) : m.error ? (
            <div key={i} className="msg error" role="alert">
              {m.error}
            </div>
          ) : (
            <CoachMessage
              key={i}
              reply={m.reply}
              onSend={onSend}
              isLast={i === messages.length - 1}
            />
          ),
        )}
        {busy && (
          <div
            className="msg coach typing"
            role="status"
            aria-label="Coach is thinking"
          >
            <span />
            <span />
            <span />
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          if (draft.trim() && !busy && !disabled) {
            onSend(draft.trim())
            setDraft('')
          }
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={disabled ? 'Pick a customer first' : 'Ask about your money'}
          aria-label="Message"
          disabled={disabled}
        />
        <button type="submit" className="send" disabled={busy || disabled || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}
