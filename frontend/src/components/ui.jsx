// Small design system: big numbers, bars, tags, info icons.

import { useState } from 'react'
import { explain } from '../lib/explainers.js'
import { useApp } from '../lib/context.js'
import { BASKETS, eur } from '../lib/format.js'
import { numberQuestions } from '../lib/questions.js'

export function Tag({ children, tone = 'neutral' }) {
  return <span className={`tag tag-${tone}`}>{children}</span>
}

const DIFFICULTY_TONE = { Easy: 'good', Stretch: 'amber', Hard: 'red' }
export function DifficultyTag({ difficulty }) {
  if (!difficulty) return null
  return <Tag tone={DIFFICULTY_TONE[difficulty] ?? 'neutral'}>{difficulty}</Tag>
}

// Money word with an (i) icon that opens a two-line explainer.
export function Info({ word, children }) {
  const { profile } = useApp()
  const [open, setOpen] = useState(false)
  const lines = explain(word, profile)
  if (!lines) return children ?? null
  return (
    <span className="info-word">
      {children}
      <button
        type="button"
        className="info-btn"
        aria-label={`What does ${word.replace('_', ' ')} mean?`}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
      >
        i
      </button>
      {open && (
        <span className="info-pop" role="note">
          {lines.map((l) => (
            <span key={l}>{l}</span>
          ))}
        </span>
      )}
    </span>
  )
}

export function ProgressBar({ value, label }) {
  const v = Math.max(0, Math.min(1, value ?? 0))
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v * 100)}
    >
      <span style={{ width: `${v * 100}%` }} />
    </div>
  )
}

// Four-basket stacked bar; Saver in a positive colour.
export function BasketBar({ totals, showLegend = true }) {
  const values = BASKETS.map((b) => ({ ...b, value: Number(totals?.[b.key] ?? 0) }))
  const sum = values.reduce((s, b) => s + b.value, 0)
  return (
    <div className="basket-bar">
      <div className="basket-track" aria-label="Four-basket split">
        {sum > 0 &&
          values.map(
            (b) =>
              b.value > 0 && (
                <span
                  key={b.key}
                  className={`seg seg-${b.key}`}
                  style={{ width: `${(b.value / sum) * 100}%` }}
                  title={`${b.label} ${eur(b.value)}`}
                />
              ),
          )}
      </div>
      {showLegend && (
        <ul className="basket-legend">
          {values.map((b) => (
            <li key={b.key}>
              <b className={`dot seg-${b.key}`} />
              <span>{b.label}</span>
              <strong>{eur(b.value)}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Opens chat with a prefilled question.
export function AskButton({ question }) {
  const { ask } = useApp()
  return (
    <button type="button" className="ask-btn" onClick={() => ask(question)}>
      Ask about this
    </button>
  )
}

// A tappable big number: tapping shows three suggested questions.
export function TapNumber({ label, value, unit = 'EUR' }) {
  const { ask } = useApp()
  const [open, setOpen] = useState(false)
  return (
    <span className="tap-number">
      <button
        type="button"
        className="big-number"
        aria-label={`${label}: ${unit === 'EUR' ? eur(value) : value}`}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
        }}
      >
        {unit === 'EUR' ? eur(value, { decimals: 0 }) : value}
      </button>
      {open && (
        <span className="chips inline">
          {numberQuestions(label).map((q) => (
            <button
              key={q.text}
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                ask(q.text, { depth: q.depth, send: true })
              }}
            >
              {q.text}
            </button>
          ))}
        </span>
      )}
    </span>
  )
}

export function Card({ title, children, ask, className = '', onOpen }) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <h3 className="card-title">
          {onOpen ? (
            <button type="button" className="link" onClick={onOpen}>
              {title} ›
            </button>
          ) : (
            title
          )}
        </h3>
      )}
      {children}
      {ask && <AskButton question={ask} />}
    </section>
  )
}

export function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <small>{label}</small>
      <strong>{value}</strong>
      {sub && <span className="muted">{sub}</span>}
    </div>
  )
}
