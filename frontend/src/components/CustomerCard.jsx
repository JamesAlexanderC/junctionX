// Picker rows: a rich card for featured customers and a compact search row.

import { eur, personaInitials } from '../format.js'
import Icon from './Icon.jsx'
import { MortgageBadge, SavingsPill } from './ui.jsx'

export function PersonaAvatar({ persona, size = 44 }) {
  return (
    <span
      className={`persona-avatar persona-${persona?.key ?? 'unknown'}`}
      style={{ width: size, height: size, fontSize: size * 0.36 }}
      aria-hidden="true"
    >
      {personaInitials(persona?.label) || '?'}
    </span>
  )
}

const meta = (c) =>
  [
    c.customer_id,
    c.customer_age != null && `${c.customer_age} y`,
    c.customer_postal_code,
  ]
    .filter(Boolean)
    .join(' · ')

export function FeaturedCard({ customer: c, onPick }) {
  return (
    <button
      type="button"
      className="featured-card"
      onClick={() => onPick(c)}
      aria-label={`${c.persona?.label ?? 'Customer'}, ${meta(c)}. Open.`}
    >
      <span className="featured-top">
        <PersonaAvatar persona={c.persona} />
        <span className="featured-id">
          <strong>{c.persona?.label ?? 'Customer'}</strong>
          <small>{meta(c)}</small>
        </span>
        <Icon name="chevron" size={18} className="chevron" />
      </span>
      <span className="featured-stats">
        <span>
          <small>Income</small>
          <b>{eur(c.monthly_income)}</b>
          <small>/mo</small>
        </span>
        <span>
          <small>Balance</small>
          <b>{eur(c.balance)}</b>
        </span>
      </span>
      <span className="featured-pills">
        <SavingsPill rate={c.savings_rate} />
        {c.has_mortgage_application && (
          <MortgageBadge decision={c.mortgage_decision} />
        )}
      </span>
    </button>
  )
}

export function CustomerRow({ customer: c, onPick }) {
  return (
    <button type="button" className="customer-row" onClick={() => onPick(c)}>
      <PersonaAvatar persona={c.persona} size={36} />
      <span className="customer-row-text">
        <strong>{c.customer_id}</strong>
        <small>
          {[
            c.persona?.label,
            c.customer_age != null && `${c.customer_age} y`,
            `${eur(c.monthly_income)}/mo`,
          ]
            .filter(Boolean)
            .join(' · ')}
        </small>
      </span>
      {c.has_mortgage_application && (
        <MortgageBadge decision={c.mortgage_decision} short />
      )}
      <Icon name="chevron" size={18} className="chevron" />
    </button>
  )
}
