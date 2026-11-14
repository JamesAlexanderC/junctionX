// Explore: every inference, section by section (context.md "Explore
// sections"). Each card has "Ask about this" to open chat prefilled.

import { useState } from 'react'
import { ChartCard, SliderCard } from '../components/Cards.jsx'
import { GoalForm, LoanForm } from '../components/Forms.jsx'
import {
  BasketBar,
  Card,
  DifficultyTag,
  Info,
  ProgressBar,
  Stat,
  Tag,
} from '../components/ui.jsx'
import { sortAlerts } from '../lib/alerts.js'
import { useApp } from '../lib/context.js'
import { BASKETS, capitalise, eur, longDate, pct, shortDate } from '../lib/format.js'
import { SECTIONS } from '../lib/sections.js'


const arrow = (v) => (v > 0 ? '▲' : v < 0 ? '▼' : '•')

function Baskets({ p }) {
  const b = p.baskets ?? {}
  const months = [...(b.history ?? []), { month: b.month, totals: b.totals }]
  const [month, setMonth] = useState(b.month)
  const shown = months.find((m) => m.month === month) ?? months[months.length - 1]
  return (
    <>
      <Card title="Four baskets" ask="Explain my four baskets">
        <label className="inline-select">
          Month{' '}
          <select value={month} onChange={(e) => setMonth(e.target.value)}>
            {months.map((m) => (
              <option key={m.month}>{m.month}</option>
            ))}
          </select>
        </label>
        <BasketBar totals={shown?.totals} />
      </Card>
      <Card title="Share and trend" ask="Which basket is growing?">
        <ul className="list">
          {BASKETS.map((k) => (
            <li key={k.key}>
              <span>
                <Info word={k.key === 'essential' ? 'essentials' : k.key}>{k.label}</Info>
              </span>
              <span>
                {pct(b.shares?.[k.key], { decimals: 1 })}{' '}
                <small className="muted">
                  {arrow(b.trend?.[k.key])} {Math.abs(b.trend?.[k.key] ?? 0)} pts
                </small>
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Leaky categories" ask="What's my leaky spending?">
        <ul className="list">
          {(b.leaky_categories ?? []).map((c) => (
            <li key={c.category}>
              <span>{capitalise(c.category)}</span>
              <strong>{eur(c.monthly_total)} / month</strong>
            </li>
          ))}
        </ul>
      </Card>
    </>
  )
}

function Forecast({ p }) {
  const f = p.forecast ?? {}
  const path = (f.daily_path ?? []).map((d) => ({
    label: shortDate(d.date),
    value: d.expected,
  }))
  return (
    <>
      <Card title="Safe to spend and save" ask="Why is my safe to spend so low?">
        <div className="stats">
          <Stat label={<Info word="safe_to_spend">This week</Info>} value={eur(f.safe_to_spend_week)} />
          <Stat label="Safe to save today" value={eur(f.safe_to_save_today)} />
          <Stat label={<Info word="buffer">Buffer</Info>} value={eur(f.buffer)} />
        </div>
      </Card>
      <Card title="End of month" ask="What will my balance be at the end of the month?">
        <Stat
          label="Expected balance"
          value={eur(f.end_of_month?.expected)}
          sub={`80% range ${eur(f.end_of_month?.low)} to ${eur(f.end_of_month?.high)}`}
        />
        {path.length > 1 && (
          <ChartCard card={{ kind: 'line', title: 'Balance to payday', unit: '€', data: path }} />
        )}
      </Card>
      <Card title="Danger days" ask="Will I run out of money before payday?">
        {f.danger_days?.length ? (
          <ul className="list">
            {f.danger_days.map((d) => (
              <li key={d.date ?? d}>
                <span>{shortDate(d.date ?? d)}</span>
                <Tag tone="red">Low balance risk</Tag>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No danger days before payday.</p>
        )}
      </Card>
      <Card title="Upcoming bills" ask="Which bills are coming up?">
        <ul className="list">
          {(f.upcoming_bills ?? []).map((bill) => (
            <li key={`${bill.merchant_id}-${bill.date}`}>
              <span>
                {shortDate(bill.date)} · {bill.name}
              </span>
              <strong>{eur(bill.amount)}</strong>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Surprise fund" ask="How much should I set aside for surprises?">
        <Stat
          label={<Info word="surprise">Set aside per month</Info>}
          value={eur(f.surprise_fund_monthly)}
        />
      </Card>
      {f.seasonal?.warn && (
        <Card title="Seasonal heads-up" className="banner" ask="Why is next month expensive?">
          <p>
            {f.seasonal.next_month} is usually {Math.round((f.seasonal.ratio - 1) * 100)}%
            above your average. A pot of {eur(f.seasonal.pot)} would cover it.
          </p>
        </Card>
      )}
    </>
  )
}

function Goals({ p }) {
  const { actions } = useApp()
  const g = p.goals ?? {}
  const l = p.levels ?? {}
  const [adding, setAdding] = useState(false)
  const [editingRec, setEditingRec] = useState(false)
  const rec = g.recommended
  return (
    <>
      <Card title="Level ladder" ask="How do I reach the next level?">
        <ol className="ladder">
          {(l.ladder ?? []).map((s) => (
            <li key={s.level} className={s.reached ? 'reached' : ''}>
              <span>
                {s.reached ? '✓' : s.level} {s.name}
              </span>
              {!s.reached && s.progress != null && (
                <ProgressBar value={s.progress} label={`${s.name} progress`} />
              )}
            </li>
          ))}
        </ol>
        {l.easiest_next_step?.text && (
          <p className="tip">Next step: {l.easiest_next_step.text}</p>
        )}
      </Card>

      {rec && (
        <Card title="Recommended goal" ask={`Tell me about the "${rec.name}" goal`}>
          <div className="row">
            <strong>{rec.name}</strong>
            <DifficultyTag difficulty={rec.difficulty} />
          </div>
          <p className="muted small">
            {eur(rec.target)} · {eur(rec.monthly_needed)} a month · gets you to Level{' '}
            {rec.for_level}
          </p>
          {editingRec ? (
            <GoalForm initial={rec} onDone={() => setEditingRec(false)} />
          ) : (
            <div className="btn-row wrap">
              <button
                type="button"
                className="btn small"
                onClick={() =>
                  actions.createGoal?.({
                    customer_id: p.customer_id,
                    name: rec.name,
                    target: rec.target,
                    type: rec.type,
                  })
                }
              >
                Accept
              </button>
              <button type="button" className="btn small ghost" onClick={() => setEditingRec(true)}>
                Edit
              </button>
              <button
                type="button"
                className="btn small ghost"
                onClick={() => actions.dismissDetected?.(rec.id)}
              >
                Dismiss
              </button>
              <button
                type="button"
                className="btn small ghost"
                aria-label="Thumbs up"
                onClick={() => actions.rate?.(rec, 'up')}
              >
                👍
              </button>
              <button
                type="button"
                className="btn small ghost"
                aria-label="Thumbs down"
                onClick={() => actions.rate?.(rec, 'down')}
              >
                👎
              </button>
            </div>
          )}
        </Card>
      )}

      <Card title="My goals" ask="Am I on track with my goals?">
        {(g.active ?? []).length === 0 && <p className="muted">No goals yet.</p>}
        {(g.active ?? []).map((goal) => (
          <div key={goal.id} className="goal-row">
            <div className="row">
              <strong>
                {goal.emoji} {goal.name}
              </strong>
              <span className="tags">
                <DifficultyTag difficulty={goal.difficulty} />
                {goal.paused ? (
                  <Tag>Paused</Tag>
                ) : (
                  <Tag tone={goal.on_track ? 'good' : 'amber'}>
                    {goal.on_track ? 'On track' : 'Off track'}
                  </Tag>
                )}
              </span>
            </div>
            <ProgressBar value={(goal.progress_pct ?? 0) / 100} label={`${goal.name} progress`} />
            <small className="muted">
              {eur(goal.saved)} of {eur(goal.target)} · {eur(goal.monthly_needed)} a month ·
              by {longDate(goal.target_date)}
            </small>
            {goal.realistic === false && (
              <p className="warn">This goal looks unrealistic at your current pace.</p>
            )}
            {goal.milestones_hit?.length > 0 && (
              <small>🎉 Milestones: {goal.milestones_hit.join('%, ')}%</small>
            )}
            <div className="btn-row">
              <button
                type="button"
                className="btn small ghost"
                onClick={() => actions.updateGoal?.(goal.id, { paused: !goal.paused })}
              >
                {goal.paused ? 'Resume' : 'Pause'}
              </button>
            </div>
          </div>
        ))}
        {g.clash?.clash && (
          <p className="warn">
            Your goals need {eur(g.clash.total_needed)} a month but you can safely save{' '}
            {eur(g.clash.safe_to_save_monthly)}.
          </p>
        )}
        {adding ? (
          <GoalForm onDone={() => setAdding(false)} />
        ) : (
          <button type="button" className="btn" onClick={() => setAdding(true)}>
            Add a goal
          </button>
        )}
      </Card>

      {(g.detected ?? []).length > 0 && (
        <Card title="Detected for you" ask="Which goals do you suggest for me?">
          {g.detected.map((d) => (
            <div key={d.id} className="goal-row">
              <p>{d.text}</p>
              <div className="btn-row">
                <button type="button" className="btn small" onClick={() => setAdding(true)}>
                  Name it
                </button>
                <button
                  type="button"
                  className="btn small ghost"
                  onClick={() => actions.dismissDetected?.(d.id)}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </Card>
      )}
    </>
  )
}

function Income({ p }) {
  const i = p.income ?? {}
  const series = (i.monthly_income_series ?? []).map((m) => ({ label: m.month, value: m.value }))
  return (
    <>
      <Card title="Payday and income" ask="When is payday?">
        <div className="stats">
          <Stat
            label="Next payday"
            value={i.payday?.found ? shortDate(i.payday.next_payday) : 'Not found'}
            sub={i.payday?.found ? `Usually the ${i.payday.day_of_month}th` : undefined}
          />
          <Stat label="Monthly income" value={eur(i.monthly_income)} />
          <Stat label="Stability" value={i.stability?.label ?? '–'} />
        </div>
        {series.length > 1 && (
          <ChartCard card={{ kind: 'line', title: 'Income by month', unit: '€', data: series }} />
        )}
      </Card>
      <Card title="Regular bills" ask="What are my regular bills?">
        <ul className="list">
          {(i.bills ?? []).map((b) => (
            <li key={b.merchant_id}>
              <span>
                {b.name} <small className="muted">next {shortDate(b.next_date)}</small>
              </span>
              <strong>{eur(b.amount)}</strong>
            </li>
          ))}
        </ul>
      </Card>
      <Card title={<Info word="subscription">Subscriptions</Info>} ask="Which subscriptions do I have?">
        <ul className="list">
          {(i.subscriptions ?? []).map((s) => {
            const unused = i.possibly_unused?.some((u) => u.merchant_id === s.merchant_id)
            return (
              <li key={s.merchant_id}>
                <span>
                  {s.name} {unused && <Tag tone="blue">Check this</Tag>}
                </span>
                <strong>{eur(s.amount)}</strong>
              </li>
            )
          })}
        </ul>
      </Card>
    </>
  )
}

function Habits({ p }) {
  const h = p.habits ?? {}
  return (
    <>
      <Card title="Spender type" ask="What kind of spender am I?">
        <Tag tone="good">{h.spender_type?.label ?? '–'}</Tag>
        {h.spender_type?.scores && (
          <ChartCard
            card={{
              kind: 'bar',
              title: 'Trait scores (0 to 1)',
              data: Object.entries(h.spender_type.scores).map(([k, v]) => ({
                label: k,
                value: v,
              })),
            }}
          />
        )}
      </Card>
      <Card title="When you spend" ask="Do I spend more at weekends?">
        <ul className="list">
          <li>
            <span>Weekend share</span>
            <span>
              {pct(h.weekend?.share, { fraction: true })}{' '}
              {h.weekend?.flag && <Tag tone="amber">Weekend spender</Tag>}
            </span>
          </li>
          <li>
            <span>Night (22-05)</span>
            <span>
              {pct(h.night?.share, { fraction: true })}{' '}
              {h.night?.flag && <Tag tone="amber">Night owl</Tag>}
            </span>
          </li>
          <li>
            <span>Impulse bursts / month</span>
            <span>{h.impulse?.bursts_per_month ?? '–'}</span>
          </li>
          <li>
            <span>Payday splurge ratio</span>
            <span>{h.payday_splurge?.ratio ?? '–'}x</span>
          </li>
        </ul>
      </Card>
      <Card title="Where you spend" ask="Where do I spend the most?">
        <Stat
          label={h.loyalty?.label ?? 'Merchants'}
          value={pct(h.loyalty?.top3_share, { fraction: true })}
          sub="of spending at your top 3 merchants"
        />
      </Card>
    </>
  )
}

function WhatIfs({ p }) {
  const w = p.whatif ?? {}
  const goal = p.goals?.active?.[0]
  const cats = Object.entries(w.category_means ?? {})
  const [cat, setCat] = useState(cats[0]?.[0])
  const spend = w.category_means?.[cat]
  return (
    <>
      <Card title="Cut a category" ask={`What if I cut ${cat} by 20%?`}>
        <label className="inline-select">
          Category{' '}
          <select value={cat} onChange={(e) => setCat(e.target.value)}>
            {cats.map(([c]) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        {spend != null && (
          <SliderCard
            key={cat}
            today={p.today}
            card={{
              category: cat,
              monthly_spend: spend,
              min_pct: 0,
              max_pct: 50,
              pct: 20,
              ...(goal && {
                goal: {
                  target: goal.target,
                  saved: goal.saved,
                  monthly_rate: p.baskets?.monthly_saving ?? 0,
                },
              }),
            }}
          />
        )}
      </Card>
      <Card title="Drop a subscription" ask="What if I cancel a subscription?">
        <ul className="list">
          {(w.subscription_savings ?? []).map((s) => (
            <li key={s.merchant_id}>
              <span>{s.name}</span>
              <strong>{eur(s.yearly_saving)} a year</strong>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="What your habits cost" ask="What else could my leaky spending buy?">
        <ul className="list">
          {(w.habit_translation ?? []).map((t) => (
            <li key={t.category}>
              <span>{capitalise(t.category)}</span>
              <span>
                = {t.count} × {t.reference}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  )
}

function Mortgage({ p }) {
  const m = p.mortgage ?? {}
  const r = m.readiness
  return (
    <>
      <Card title={<Info word="dsti">Loan burden</Info>} ask="How big is my loan burden?">
        {m.loan_payments_found ? (
          <Stat label="DSTI" value={pct(m.dsti, { fraction: true })} sub="Amber 40%, red 50%" />
        ) : (
          <p className="muted">No loan payments found in your account.</p>
        )}
      </Card>
      <Card title="Rate-rise stress test" ask="Can I afford my mortgage if rates go up?">
        {m.stress_test ? (
          <Stat
            label="Payments at 6% interest"
            value={eur(m.stress_test.stressed_payment)}
            sub={`${pct(m.stress_test.stressed_dsti, { fraction: true })} of income (limit 60%)`}
          />
        ) : (
          <p className="muted">Add your loan details to run the FIN-FSA 6% test.</p>
        )}
        <details>
          <summary>Add loan details</summary>
          <LoanForm />
        </details>
      </Card>
      {r && (
        <Card title={<Info word="readiness">Mortgage readiness</Info>} ask="How ready am I for a mortgage?">
          <div className="gauge">
            <ProgressBar value={r.score} label="Readiness score" />
            <strong>{Math.round(r.score * 100)} / 100</strong>
          </div>
          <h4>Gaps to close</h4>
          <ul className="list">
            {(r.gaps ?? []).map((g) => (
              <li key={g.feature}>
                <span>{g.feature.replace(/_/g, ' ')}</span>
                <span>
                  you {g.user} · approved {g.approved_median}
                </span>
              </li>
            ))}
          </ul>
          <small className="muted">{r.note ?? 'Guidance only, not a loan decision.'}</small>
        </Card>
      )}
    </>
  )
}

function People({ p }) {
  const b = p.benchmarks ?? {}
  const rows = (list) =>
    (list ?? []).map((x) => ({ label: x.category, value: x.ratio }))
  return (
    <>
      {[
        ['age', `Your age group (${p.customer?.age_band ?? '–'})`],
        ['area', `Your area (${p.customer?.area ?? '–'}xxx)`],
      ].map(([key, title]) => (
        <Card key={key} title={title} ask={`How do I compare with my ${key === 'age' ? 'age group' : 'area'}?`}>
          <ul className="list">
            {(b[key] ?? []).map((x) => (
              <li key={x.category}>
                <span>{capitalise(x.category)}</span>
                <span>
                  {eur(x.user)} vs {eur(x.peer_median)}{' '}
                  {x.flag && <Tag tone={x.flag === 'above' ? 'amber' : 'good'}>{x.flag}</Tag>}
                </span>
              </li>
            ))}
          </ul>
          {rows(b[key]).length > 0 && (
            <ChartCard card={{ kind: 'bar', title: 'You ÷ peer median', data: rows(b[key]) }} />
          )}
        </Card>
      ))}
      <small className="muted pad">Source: {b.source}</small>
    </>
  )
}

function AlertsSection({ p }) {
  const { go } = useApp()
  const alerts = sortAlerts(p.alerts, p.today)
  return (
    <Card title="Alerts" ask="Help me clear my alerts">
      <ul className="list">
        {alerts.map((a) => (
          <li key={a.id}>
            <span>{a.title}</span>
            <Tag tone={a.severity}>{a.severity}</Tag>
          </li>
        ))}
      </ul>
      <button type="button" className="btn" onClick={() => go('alerts')}>
        Open alert inbox
      </button>
    </Card>
  )
}

function Accounts({ p }) {
  const mb = p.multibank ?? {}
  return (
    <>
      <Card title="Connected banks" ask="What changes if I connect another bank?">
        <ul className="list">
          {(mb.accounts ?? []).map((a) => (
            <li key={a.bank_account_id}>
              <span>{a.bank}</span>
              <small className="muted">{a.bank_account_id}</small>
            </li>
          ))}
        </ul>
        <button type="button" className="btn ghost" disabled title="Mock PSD2 consent, coming soon">
          Connect another bank
        </button>
      </Card>
      <Card title="Across all banks" ask="What is my true total income?">
        <Stat label="True total income" value={eur(mb.true_income)} />
        {mb.hidden_loans?.length > 0 && (
          <p className="warn">{mb.hidden_loans.length} loan(s) found at other banks.</p>
        )}
        {mb.duplicate_subscriptions?.length > 0 && (
          <p className="warn">
            {mb.duplicate_subscriptions.length} subscription(s) paid in two banks.
          </p>
        )}
      </Card>
    </>
  )
}

const RENDER = {
  baskets: Baskets,
  forecast: Forecast,
  goals: Goals,
  income: Income,
  habits: Habits,
  whatifs: WhatIfs,
  mortgage: Mortgage,
  people: People,
  alerts: AlertsSection,
  accounts: Accounts,
}

export default function Explore({ section = 'baskets' }) {
  const { profile, go } = useApp()
  const Section = RENDER[section] ?? Baskets
  return (
    <div className="explore">
      <nav className="chips scroll section-tabs" aria-label="Explore sections">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={s.id === section ? 'active' : ''}
            aria-current={s.id === section ? 'page' : undefined}
            onClick={() => go(`explore/${s.id}`)}
          >
            {s.label}
          </button>
        ))}
      </nav>
      <Section p={profile} />
    </div>
  )
}
