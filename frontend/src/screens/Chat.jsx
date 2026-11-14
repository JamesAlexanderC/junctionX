// Chat screen: user bubbles, coach replies from send_reply (text streamed
// client-side), cards, a depth badge and "Go deeper" chips.

import { useEffect, useRef, useState } from 'react'
import { ReplyCard } from '../components/Cards.jsx'
import { DEPTH_NAMES } from '../lib/format.js'

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
    .map((block, i) => (
      <p key={i}>
        {block.split('\n').map((l, j) => (
          <span key={j}>
            {j > 0 && <br />}
            <Inline text={l} />
          </span>
        ))}
      </p>
    ))
}

// Reveal the reply word by word, like streaming.
function useTypewriter(text, enabled) {
  const words = text.split(/(\s+)/)
  const [n, setN] = useState(enabled ? 0 : words.length)
  useEffect(() => {
    if (n >= words.length) return undefined
    const t = setTimeout(() => setN((x) => x + 2), 25)
    return () => clearTimeout(t)
  }, [n, words.length])
  return words.slice(0, n).join('')
}

const nextDepth = (d) => Math.min(4, (d ?? 1) + 1)

function CoachMessage({ msg, onSend, isLast }) {
  const reply = msg.reply
  const text = useTypewriter(reply.text ?? '', msg.animate)
  const done = text.length >= (reply.text ?? '').length
  return (
    <div className="assistant">
      <div className={`bubble coach${msg.error ? ' error' : ''}`}>
        {reply.depth && (
          <span className="depth-badge" data-testid="depth-badge">
            {DEPTH_NAMES[reply.depth]}
          </span>
        )}
        <RichText text={text || ' '} />
      </div>
      {done &&
        (reply.cards ?? []).map((card, i) => (
          <ReplyCard key={i} card={card} onSend={onSend} />
        ))}
      {done && isLast && reply.chips?.length > 0 && (
        <div className="go-deeper">
          <small className="muted">Go deeper</small>
          <div className="chips">
            {reply.chips.slice(0, 3).map((c) => (
              <button key={c} type="button" onClick={() => onSend(c, nextDepth(reply.depth))}>
                {c}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Chat({ messages, busy, draft, setDraft, onSend, demo }) {
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  useEffect(() => {
    if (draft) inputRef.current?.focus()
  }, [draft])

  return (
    <div className="chat">
      {demo && (
        <div className="demo-banner">
          Demo mode: backend not reachable, answers come from sample rules.
        </div>
      )}
      <section className="messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="welcome">
            <h2>Hey! 👋</h2>
            <p>
              Ask me anything about your money. I only use your own numbers,
              calculated by the app, never guesses.
            </p>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="bubble user">
              {m.content}
            </div>
          ) : m.pending ? (
            <div key={i} className="assistant">
              <div className="bubble coach">
                <span className="typing" aria-label="Coach is thinking">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </div>
          ) : (
            <CoachMessage
              key={i}
              msg={m}
              onSend={onSend}
              isLast={i === messages.length - 1}
            />
          ),
        )}
        <div ref={endRef} />
      </section>
      <footer className="composer">
        <form
          className="composer-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (draft.trim() && !busy) onSend(draft.trim())
          }}
        >
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about your money…"
            aria-label="Message"
          />
          <button type="submit" disabled={busy || !draft.trim()} aria-label="Send">
            ↑
          </button>
        </form>
      </footer>
    </div>
  )
}
