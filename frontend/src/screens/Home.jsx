// Focus home (context.md "UI: Focus home and Explore"), top to bottom:
// safe to spend, level bar, four baskets, top goal, one nudge, try asking,
// chat bar. Every tile opens its Explore section.

import { useEffect, useState } from 'react'
import { BasketBar, DifficultyTag, Info, ProgressBar, TapNumber } from '../components/ui.jsx'
import { fixAlertQuestion, topNudgeAlert } from '../lib/alerts.js'
import { useApp } from '../lib/context.js'
import { DEPTH_NAMES, eur } from '../lib/format.js'
import { placeholders, tryAsking } from '../lib/questions.js'

function Tile({ section, label, children, className = '' }) {
  const { go } = useApp()
  return (
    <section
      className={`tile ${className}`}
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={() => go(`explore/${section}`)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') go(`explore/${section}`)
      }}
    >
      {children}
    </section>
  )
}

export function Nudge({ profile }) {
  const { ask, go, actions } = useApp()
  const alert = topNudgeAlert(profile.alerts, profile.today)
  if (alert) {
    return (
      <section className={`nudge sev-${alert.severity}`} data-testid="nudge">
        <strong>{alert.title}</strong>
        <p>{alert.text}</p>
        <div className="btn-row">
          <button
            type="button"
            className="btn"
            onClick={() => ask(fixAlertQuestion(alert), { depth: 4, send: true })}
          >
            Fix this
          </button>
          <button type="button" className="btn ghost" onClick={() => go('alerts')}>
            See all alerts
          </button>
        </div>
      </section>
    )
  }
  const detected = profile.goals?.detected?.[0]
  if (!detected) return null
  return (
    <section className="nudge sev-good" data-testid="nudge">
      <strong>{detected.text}</strong>
      {detected.monthly_amount != null && (
        <p>You move about {eur(detected.monthly_amount)} a month to savings.</p>
      )}
      <div className="btn-row">
        <button type="button" className="btn" onClick={() => go('explore/goals')}>
          Name it
        </button>
        <button
          type="button"
          className="btn ghost"
          onClick={() => actions.dismissDetected?.(detected.id)}
        >
          Not now
        </button>
      </div>
    </section>
  )
}

function ChatBar({ profile }) {
  const { ask, go } = useApp()
  const hints = placeholders(profile)
  const [i, setI] = useState(0)
  const [text, setText] = useState('')
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % hints.length), 3500)
    return () => clearInterval(t)
  }, [hints.length])
  return (
    <div className="home-chatbar">
      <form
        className="composer-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (text.trim()) ask(text.trim(), { send: true })
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={hints[i]}
          aria-label="Ask the coach"
        />
        <button type="submit" aria-label="Send" disabled={!text.trim()}>
          ↑
        </button>
      </form>
      <button type="button" className="link" onClick={() => go('explore')}>
        Explore all your numbers ›
      </button>
    </div>
  )
}

export default function Home({ onSeeAllQuestions }) {
  const { profile, ask } = useApp()
  const f = profile.forecast ?? {}
  const pay = profile.income?.payday
  const lvl = profile.levels ?? {}
  const goal = profile.goals?.active?.[0]

  return (
    <div className="home">
      <Tile section="forecast" label="Safe to spend this week" className="hero">
        <small>
          <Info word="safe_to_spend">Safe to spend this week</Info>
        </small>
        <TapNumber label="Safe to spend" value={f.safe_to_spend_week} />
        <span className="muted">
          {pay?.found
            ? `${pay.days_to_payday} days to payday`
            : 'Payday not found yet'}
        </span>
      </Tile>

      <Tile section="goals" label="Level progress">
        <div className="row">
          <strong>
            Level {lvl.next}: {lvl.next_name}
          </strong>
          <span>{Math.round((lvl.progress ?? 0) * 100)}%</span>
        </div>
        <ProgressBar value={lvl.progress} label="Level progress" />
        <small className="muted">
          {eur(lvl.euros_to_go)} to go
          {lvl.easiest_next_step?.text && ` · Fastest way: ${lvl.easiest_next_step.text}`}
        </small>
      </Tile>

      <Tile section="baskets" label="Four baskets">
        <h3 className="card-title">Your four baskets</h3>
        <BasketBar totals={profile.baskets?.totals} />
      </Tile>

      {goal && (
        <Tile section="goals" label="Top goal">
          <div className="row">
            <strong>
              {goal.emoji} {goal.name}
            </strong>
            <DifficultyTag difficulty={goal.difficulty} />
          </div>
          <ProgressBar value={(goal.progress_pct ?? 0) / 100} label="Goal progress" />
          <small className="muted">
            {eur(goal.saved)} of {eur(goal.target)} ·{' '}
            {goal.on_track ? 'On track' : 'Off track'}
          </small>
        </Tile>
      )}

      <Nudge profile={profile} />

      <section className="try-asking">
        <h3 className="card-title">Try asking</h3>
        <div className="chips scroll">
          {tryAsking(profile).map((q) => (
            <button
              key={q.depth}
              type="button"
              onClick={() => ask(q.text, { depth: q.depth, send: true })}
            >
              <span className="depth-badge">{DEPTH_NAMES[q.depth]}</span> {q.text}
            </button>
          ))}
        </div>
        <button type="button" className="link" onClick={onSeeAllQuestions}>
          See all questions ›
        </button>
      </section>

      <ChatBar profile={profile} />
    </div>
  )
}
