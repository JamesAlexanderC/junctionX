// Renderers for send_reply cards (CLAUDE.md "Card payloads"), plain markup.
// Unknown card types render nothing, so new backend cards never crash chat.

import { useState } from 'react'
import { eur, formatValue, longDate } from '../lib/format.js'
import { cutSaving, goalWithCut } from '../lib/formulas.js'
import ChartCard from './Chart.jsx'
import Icon from './Icon.jsx'

const TODAY = () => new Date().toISOString().slice(0, 10)

const pct = (v) => Math.max(0, Math.min(1, Number(v) || 0)) * 100

// Progress bar for a 0..1 share; `marker` (0..1) draws a tick, e.g. where the
// goal should be by now (#52).
export function Bar({ value, marker }) {
  return (
    <div className="bar">
      <div style={{ width: `${pct(value)}%` }} />
      {marker != null && (
        <i className="bar-marker" style={{ left: `${pct(marker)}%` }} />
      )}
    </div>
  )
}

function NumberCard({ card }) {
  return (
    <div className="card">
      <small>{card.label}</small>
      <strong className="big">{formatValue(card.value, card.unit ?? 'EUR')}</strong>
    </div>
  )
}

const BASKETS = [
  ['essential', 'Essentials'],
  ['surprise', 'Surprises'],
  ['leaky', 'Leaky'],
  ['saver', 'Saver'],
]

function BasketBarCard({ card }) {
  const rows = BASKETS.filter(([k]) => card[k] != null)
  const total = rows.reduce((s, [k]) => s + Math.abs(Number(card[k]) || 0), 0) || 1
  return (
    <div className="card">
      <ul className="chart">
        {rows.map(([k, label]) => (
          <li key={k}>
            <span>{label}</span>
            <Bar value={Math.abs(card[k]) / total} />
            <span>{eur(card[k])}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// What-if slider: #24 and #26 recalculated locally, no API call.
// The slider works in whole percent on 5 % steps. A fraction (0.2) is read as
// 20 %, in case a card still carries simulate_cut's 0-1 value.
const sliderStart = (pct) => {
  const p = pct > 0 && pct <= 1 ? pct * 100 : (pct ?? 20)
  return Math.round(p / 5) * 5
}

export function SliderCard({ card, onSend }) {
  const [p, setP] = useState(() => sliderStart(card.pct))
  const [sent, setSent] = useState(null)
  const saving = cutSaving(card.monthly_spend, p / 100)
  const goal =
    card.goal &&
    goalWithCut(
      {
        target: card.goal.target,
        saved: card.goal.saved,
        monthlyRate: card.goal.monthly_rate,
      },
      saving.monthly,
      TODAY(),
    )
  return (
    <div className="card">
      <label className="slider">
        <span>
          Cut {card.category} by <strong>{p}%</strong>
        </span>
        <input
          type="range"
          min={card.min_pct ?? 0}
          max={card.max_pct ?? 50}
          step={5}
          value={p}
          onChange={(e) => setP(Number(e.target.value))}
        />
      </label>
      <p>
        <span data-testid="monthly-saving">{eur(saving.monthly)}</span> a month,{' '}
        <span data-testid="yearly-saving">{eur(saving.yearly)}</span> a year (from{' '}
        {eur(card.monthly_spend)} a month now)
      </p>
      {goal && (
        <p className="muted">
          {goal.after == null
            ? 'Goal not reachable at the current pace.'
            : `Goal date: ${longDate(goal.afterDate)}` +
              (goal.monthsSooner > 0 ? ` (${goal.monthsSooner} months sooner)` : '')}
        </p>
      )}
      {onSend && (
        <button
          type="button"
          className="btn-primary"
          disabled={p <= 0 || sent === p}
          onClick={() => {
            setSent(p)
            onSend(
              `Save cutting ${card.category} by ${p}% as my plan ` +
                `(${eur(saving.monthly)} a month)`,
              4,
            )
          }}
        >
          <Icon name="check" size={16} />
          {sent === p ? 'Sent to the coach' : `Cut ${card.category} by ${p}%`}
        </button>
      )}
    </div>
  )
}

function GoalCard({ card }) {
  return (
    <div className="card">
      <strong>{card.name}</strong>
      {card.difficulty && <span className="tag">{card.difficulty}</span>}
      <Bar value={card.target ? (card.saved ?? 0) / card.target : 0} />
      <small>
        {eur(card.saved ?? 0)} of {eur(card.target)}
        {card.monthly_needed != null && ` · ${eur(card.monthly_needed)} a month`}
        {card.target_date && ` · by ${longDate(card.target_date)}`}
      </small>
    </div>
  )
}

// Six-level ladder (#28-#33): reached levels filled, the target outlined.
function Ladder({ ladder, target }) {
  return (
    <ol className="ladder" aria-label="Levels">
      {ladder.map((r) => {
        const state = r.reached ? 'reached' : r.level === target ? 'target' : 'ahead'
        return (
          <li
            key={r.level}
            className={state}
            title={r.name}
            aria-label={`Level ${r.level} ${r.name}, ${
              r.reached ? 'reached' : r.level === target ? 'next' : 'not yet'
            }`}
          >
            {r.level}
          </li>
        )
      })}
    </ol>
  )
}

function LevelProgressCard({ card }) {
  return (
    <div className="card">
      {card.ladder?.length > 0 && <Ladder ladder={card.ladder} target={card.level} />}
      <strong>
        Level {card.level}: {card.name}
      </strong>
      <Bar value={card.progress} />
      <small>
        {card.euros_to_go != null && `${eur(card.euros_to_go)} to go`}
        {card.next_step && ` · ${card.next_step}`}
      </small>
      {card.requirement?.text && (
        <div className="level-req">
          <p>{card.requirement.text}</p>
          {card.requirement.checks?.length > 0 && (
            <ul aria-label="What this level needs">
              {card.requirement.checks.map((c) => (
                <li key={c.text} className={c.met ? 'met' : 'todo'}>
                  <Icon name={c.met ? 'check' : 'behind'} size={14} />
                  {c.text}
                  <span className="sr-only">{c.met ? ' (done)' : ' (to do)'}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function QuestionCard({ card, onSend }) {
  const options = [...(card.options ?? []), ...(card.quick_answer ? [card.quick_answer] : [])]
  return (
    <div className="card">
      <strong>{card.question}</strong>
      <div className="chips">
        {options.map((o) => (
          <button key={o} type="button" onClick={() => onSend(o, 4)}>
            {o}
          </button>
        ))}
      </div>
    </div>
  )
}

function AlertCard({ card, onSend }) {
  return (
    <div className="card">
      <strong>
        <i className={`dot sev-${card.severity}`} /> {card.title}
      </strong>
      <p>{card.text}</p>
      <button
        type="button"
        className="btn-primary"
        onClick={() => onSend(`Help me fix the "${card.title}" alert`, 4)}
      >
        <Icon name="fix" size={16} />
        Fix this
      </button>
    </div>
  )
}

export function PlanCard({ card, onSend }) {
  const steps = card.steps ?? []
  // One tap only: the backend also refuses to save the same plan twice.
  const [accepted, setAccepted] = useState(false)
  const accept = () => {
    if (accepted) return
    setAccepted(true)
    onSend('Accept plan', 4)
  }
  return (
    <div className="card">
      <ol>
        {steps.map((s, i) => {
          const n = s.clears?.length ?? 0
          return (
            <li key={i}>
              {s.text} · +{eur(s.monthly_impact)} a month · clears {n} alert
              {n === 1 ? '' : 's'}
            </li>
          )
        })}
      </ol>
      <button
        type="button"
        className="btn-primary"
        disabled={accepted}
        onClick={accept}
      >
        <Icon name="check" size={16} />
        {accepted ? 'Plan accepted' : 'Accept plan'}
      </button>
    </div>
  )
}

function BeforeAfterCard({ card }) {
  const rows = [
    ['Safe to spend', 'safe_to_spend', eur],
    ['Buffer', 'buffer_months', (v) => (v == null ? '–' : `${v} months`)],
    ['Goal date', 'goal_date', longDate],
  ].filter(([, k]) => card.before?.[k] != null || card.after?.[k] != null)
  return (
    <table className="card">
      <thead>
        <tr>
          <th />
          <th>Before</th>
          <th>After</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, k, fmt]) => (
          <tr key={k}>
            <th>{label}</th>
            <td>{fmt(card.before?.[k])}</td>
            <td>{fmt(card.after?.[k])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const RENDERERS = {
  number: NumberCard,
  chart: ChartCard,
  basket_bar: BasketBarCard,
  slider: SliderCard,
  goal: GoalCard,
  level_progress: LevelProgressCard,
  question: QuestionCard,
  alert: AlertCard,
  plan: PlanCard,
  before_after: BeforeAfterCard,
}

export function ReplyCard({ card, onSend }) {
  const Renderer = RENDERERS[card?.type]
  if (!Renderer) return null
  return <Renderer card={card} onSend={onSend} />
}
