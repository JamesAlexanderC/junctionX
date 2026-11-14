// Small shared building blocks: badges, skeletons, error and demo notices.

import Icon from './Icon.jsx'

/** Shows which brain answers: Gemini, the offline coach, or demo data. */
export function ProviderBadge({
  provider,
  model,
  demo,
  compact = false,
  tiny = false,
}) {
  if (demo) {
    return (
      <span className="badge badge-demo" title="Backend not reachable: sample data">
        <span className="badge-dot" aria-hidden="true" />
        {tiny ? 'Demo' : 'Demo data'}
      </span>
    )
  }
  if (!provider) return null
  const gemini = provider === 'gemini'
  const label = gemini ? 'Gemini' : tiny ? 'Offline' : 'Offline coach'
  return (
    <span
      className={`badge ${gemini ? 'badge-ai' : 'badge-offline'}`}
      title={gemini && model ? `Answers by ${model}` : `Answers by ${label}`}
    >
      <Icon name={gemini ? 'sparkle' : 'bulb'} size={13} />
      {compact || tiny ? label : gemini && model ? model : label}
    </span>
  )
}

export function DemoBanner() {
  return (
    <p className="demo-banner" role="note">
      <Icon name="info" size={16} />
      <span>
        <strong>Demo mode.</strong> The backend isn't reachable, so you're
        seeing realistic sample customers.
      </span>
    </p>
  )
}

export function Skeleton({ width = '100%', height = 14, radius, className = '' }) {
  return (
    <span
      className={`skeleton ${className}`}
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  )
}

export function ErrorState({ title = 'Something went wrong', message, onRetry }) {
  return (
    <div className="error-state" role="alert">
      <span className="error-icon">
        <Icon name="alert" size={22} />
      </span>
      <strong>{title}</strong>
      {message && <p>{message}</p>}
      {onRetry && (
        <button type="button" className="btn btn-outline" onClick={onRetry}>
          <Icon name="refresh" size={16} /> Try again
        </button>
      )}
    </div>
  )
}

const DECISIONS = {
  approved: { cls: 'good', label: 'Mortgage approved', icon: 'check' },
  rejected: { cls: 'bad', label: 'Mortgage declined', icon: 'close' },
}

export function MortgageBadge({ decision, short = false }) {
  const d = DECISIONS[decision] ?? {
    cls: 'neutral',
    label: decision
      ? `Mortgage ${decision.replace(/_/g, ' ')}`
      : 'Mortgage in progress',
    icon: 'house',
  }
  return (
    <span className={`pill pill-${d.cls}`}>
      <Icon name={d.icon} size={12} strokeWidth={2.5} />
      {short ? d.label.replace('Mortgage ', '') : d.label}
    </span>
  )
}

/** Savings-rate pill coloured by how healthy the rate is. */
export function SavingsPill({ rate }) {
  const r = Number(rate) || 0
  const cls = r >= 0.15 ? 'good' : r >= 0.05 ? 'neutral' : 'bad'
  const label =
    r < 0 ? `Overspends ${Math.round(-r * 100)}%` : `Saves ${Math.round(r * 100)}%`
  return (
    <span className={`pill pill-${cls}`} title="Share of income left after spending">
      {label}
    </span>
  )
}
