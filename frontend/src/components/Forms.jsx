// Add goal (#64) and Add loan details (P2.8) forms. Validation mirrors the
// Django rules so users see errors before the request is sent.

import { useState } from 'react'
import { useApp } from '../lib/context.js'

export function GoalForm({ initial, onDone }) {
  const { profile, actions } = useApp()
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    target: initial?.target ?? '',
    target_date: initial?.target_date ?? '',
    emoji: initial?.emoji ?? '🎯',
  })
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    const target = Number(form.target)
    if (!form.name.trim()) return setError('Give the goal a name.')
    if (!(target > 0)) return setError('The amount must be more than 0.')
    if (!form.target_date || form.target_date <= (profile.today ?? ''))
      return setError('Pick a date in the future.')
    setError(null)
    setSaving(true)
    try {
      await actions.createGoal({
        customer_id: profile.customer_id,
        name: form.name.trim(),
        target,
        target_date: form.target_date,
        emoji: form.emoji,
        type: initial?.type ?? 'custom',
      })
      onDone?.()
    } catch (err) {
      setError(`Could not save the goal (${err.message}).`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Add goal">
      <label>
        Name
        <input value={form.name} onChange={set('name')} placeholder="Japan trip" />
      </label>
      <label>
        Amount (EUR)
        <input type="number" min="1" value={form.target} onChange={set('target')} />
      </label>
      <label>
        Date
        <input type="date" value={form.target_date} onChange={set('target_date')} />
      </label>
      <label>
        Emoji
        <input value={form.emoji} onChange={set('emoji')} maxLength={4} />
      </label>
      {error && <p className="form-error">{error}</p>}
      <div className="btn-row">
        <button type="submit" className="btn" disabled={saving}>
          Save goal
        </button>
        {onDone && (
          <button type="button" className="btn ghost" onClick={onDone}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

export function LoanForm({ onDone }) {
  const { profile, actions } = useApp()
  const [form, setForm] = useState({ balance: '', interest_rate: '', years_left: '' })
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    const balance = Number(form.balance)
    const rate = Number(form.interest_rate)
    const years = Number(form.years_left)
    if (!(balance > 0)) return setError('Balance must be more than 0.')
    if (!(rate >= 0 && rate <= 20)) return setError('Rate must be between 0 and 20%.')
    if (!(years >= 1 && years <= 40)) return setError('Years left must be 1 to 40.')
    setError(null)
    try {
      await actions.saveLoan({
        customer_id: profile.customer_id,
        balance,
        interest_rate: rate,
        years_left: years,
      })
      setSaved(true)
      onDone?.()
    } catch (err) {
      setError(`Could not save (${err.message}).`)
    }
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Add loan details">
      <label>
        Loan balance (EUR)
        <input type="number" value={form.balance} onChange={set('balance')} />
      </label>
      <label>
        Interest rate (%)
        <input
          type="number"
          step="0.01"
          value={form.interest_rate}
          onChange={set('interest_rate')}
        />
      </label>
      <label>
        Years left
        <input type="number" value={form.years_left} onChange={set('years_left')} />
      </label>
      {error && <p className="form-error">{error}</p>}
      {saved && <p className="muted">Saved. The rate-rise test now uses your loan.</p>}
      <button type="submit" className="btn">
        Save loan details
      </button>
    </form>
  )
}
