// Renderers for send_reply cards (CLAUDE.md "Card payloads").
// Unknown card types render nothing, so new backend cards never crash chat.

import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fixAlertQuestion } from '../lib/alerts.js'
import { useApp } from '../lib/context.js'
import { eur, longDate, pct } from '../lib/format.js'
import { cutSaving, goalWithCut } from '../lib/formulas.js'
import { BasketBar, DifficultyTag, ProgressBar } from './ui.jsx'

// Fallback when the profile has no `today` (fixtures always set it).
const TODAY = new Date().toISOString().slice(0, 10)

function NumberCard({ card }) {
  const isEur = !card.unit || card.unit === 'EUR' || card.unit === '€'
  return (
    <div className="rcard number-card">
      <small>{card.label}</small>
      <strong className="big-number">{isEur ? eur(card.value) : card.value}</strong>
      {!isEur && card.unit && <span className="muted"> {card.unit}</span>}
    </div>
  )
}

export function ChartCard({ card }) {
  const { kind = 'bar', title, unit, data = [] } = card
  if (!data.length) return null
  const fmt = (v) => (unit === '€' || unit === 'EUR' ? eur(v) : v)
  const axis = { tick: { fontSize: 12 }, tickLine: false, axisLine: false }
  const body =
    kind === 'line' ? (
      <LineChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} width={48} />
        <Tooltip formatter={fmt} />
        <Line dataKey="value" stroke="var(--accent)" strokeWidth={2.5} dot={{ r: 3 }} />
      </LineChart>
    ) : (
      <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} width={48} />
        <Tooltip formatter={fmt} />
        <Bar dataKey="value" fill="var(--accent)" radius={[4, 4, 0, 0]} />
      </BarChart>
    )
  return (
    <figure className="rcard chart-card">
      {title && <figcaption>{title}</figcaption>}
      <div className="chart-body">
        <ResponsiveContainer width="100%" height="100%">
          {body}
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

function BasketBarCard({ card }) {
  return (
    <div className="rcard">
      <BasketBar totals={card} />
    </div>
  )
}

// What-if slider: #24 and #26 recalculated locally, no API call.
export function SliderCard({ card, today }) {
  const [p, setP] = useState(card.pct ?? 20)
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
      today ?? TODAY,
    )
  return (
    <div className="rcard slider-card">
      <label htmlFor={`slider-${card.category}`}>
        Cut <strong>{card.category}</strong> by <strong>{p}%</strong>
      </label>
      <input
        id={`slider-${card.category}`}
        type="range"
        min={card.min_pct ?? 0}
        max={card.max_pct ?? 50}
        step={5}
        value={p}
        onChange={(e) => setP(Number(e.target.value))}
      />
      <div className="slider-out">
        <div>
          <small>Per month</small>
          <strong data-testid="monthly-saving">{eur(saving.monthly)}</strong>
        </div>
        <div>
          <small>Per year</small>
          <strong data-testid="yearly-saving">{eur(saving.yearly)}</strong>
        </div>
      </div>
      {goal && (
        <p className="muted small">
          {goal.after == null
            ? 'Goal not reachable at the current pace.'
            : `Goal date: ${longDate(goal.afterDate)}` +
              (goal.monthsSooner > 0 ? ` (${goal.monthsSooner} months sooner)` : '')}
        </p>
      )}
      <small className="muted">From {eur(card.monthly_spend)} a month now.</small>
    </div>
  )
}

function GoalCard({ card }) {
  const progress = card.target ? (card.saved ?? 0) / card.target : 0
  return (
    <div className="rcard goal-card">
      <div className="row">
        <strong>{card.name}</strong>
        <DifficultyTag difficulty={card.difficulty} />
      </div>
      <ProgressBar value={progress} label={`${card.name} progress`} />
      <div className="row muted small">
        <span>
          {eur(card.saved ?? 0)} of {eur(card.target)}
        </span>
        {card.monthly_needed != null && <span>{eur(card.monthly_needed)} / month</span>}
      </div>
      {card.target_date && <small className="muted">By {longDate(card.target_date)}</small>}
    </div>
  )
}

function LevelProgressCard({ card }) {
  return (
    <div className="rcard">
      <div className="row">
        <strong>
          Level {card.level}: {card.name}
        </strong>
        <span>{pct(card.progress, { fraction: true })}</span>
      </div>
      <ProgressBar value={card.progress} label="Level progress" />
      <small className="muted">
        {eur(card.euros_to_go)} to go{card.next_step ? ` · ${card.next_step}` : ''}
      </small>
    </div>
  )
}

function QuestionCard({ card, onSend }) {
  return (
    <div className="rcard question-card">
      <strong>{card.question}</strong>
      <div className="chips">
        {(card.options ?? []).map((o) => (
          <button key={o} type="button" onClick={() => onSend(o, 4)}>
            {o}
          </button>
        ))}
        {card.quick_answer && (
          <button type="button" className="ghost" onClick={() => onSend(card.quick_answer, 4)}>
            {card.quick_answer}
          </button>
        )}
      </div>
    </div>
  )
}

export function AlertCard({ card, onSend }) {
  return (
    <div className={`rcard alert-card sev-${card.severity}`}>
      <strong>{card.title}</strong>
      <p>{card.text}</p>
      {onSend && (
        <button type="button" className="btn small" onClick={() => onSend(fixAlertQuestion(card), 4)}>
          Fix this
        </button>
      )}
    </div>
  )
}

export function PlanCard({ card, onSend }) {
  const steps = card.steps ?? []
  return (
    <div className="rcard plan-card">
      <strong>Plan, {steps.length} steps</strong>
      <ol>
        {steps.map((s, i) => (
          <li key={i}>
            <span>{s.text}</span>
            <span className="muted small">
              +{eur(s.monthly_impact)} a month · clears {s.clears?.length ?? 0} alert
              {s.clears?.length === 1 ? '' : 's'}
            </span>
          </li>
        ))}
      </ol>
      {onSend && (
        <button type="button" className="btn" onClick={() => onSend('Accept plan', 4)}>
          Accept plan
        </button>
      )}
    </div>
  )
}

function BeforeAfterCard({ card }) {
  const rows = [
    ['Safe to spend', (v) => eur(v), 'safe_to_spend'],
    ['Buffer', (v) => (v == null ? '–' : `${v} months`), 'buffer_months'],
    ['Goal date', (v) => longDate(v), 'goal_date'],
  ]
  return (
    <div className="rcard before-after">
      <table>
        <thead>
          <tr>
            <th />
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, fmt, key]) => (
            <tr key={key}>
              <th>{label}</th>
              <td>{fmt(card.before?.[key])}</td>
              <td>
                <strong>{fmt(card.after?.[key])}</strong>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
  const { profile } = useApp()
  const Renderer = RENDERERS[card?.type]
  if (!Renderer) return null
  return <Renderer card={card} onSend={onSend} today={profile?.today} />
}
