// Accounts in the Overview (MULTIBANK_PLAN.md §7): S-Bank and linked banks,
// each linked one tagged "simulated", with its consent expiry and a
// Disconnect that asks first. Plus the partial-view banner (#112).
import { useState } from 'react'
import { eur, longDate } from '../lib/format.js'
import Icon from './Icon.jsx'

export function SourceBadge({ bank }) {
  return <span className="source-badge">{bank} · simulated</span>
}

export function PartialViewBanner({ coverage, onConnect }) {
  if (coverage !== 'partial') return null
  return (
    <div className="banner partial-view" role="status">
      <Icon name="multibank" />
      <p>
        I only see your S-Bank account, so part of your money is missing.
        Connecting your other bank shows the whole picture.
      </p>
      <button type="button" className="btn-dark" onClick={onConnect}>
        Connect another bank
      </button>
    </div>
  )
}

const TYPE_NAMES = {
  current: 'Current account',
  savings: 'Savings',
  credit: 'Credit card',
  loan: 'Loan',
}

function AccountRow({ account }) {
  return (
    <li className="row account-row">
      <span className="row-main">
        <span className="ins-title">
          {account.name}{' '}
          {account.simulated ? (
            <SourceBadge bank={account.bank} />
          ) : (
            <span className="bank-name">{account.bank}</span>
          )}
        </span>
        <small className="ins-text">
          {TYPE_NAMES[account.type] ?? account.type}
          {account.iban_masked && <span className="iban">{account.iban_masked}</span>}
        </small>
      </span>
      <strong className="row-value">
        {account.balance_eur == null ? '–' : eur(account.balance_eur)}
      </strong>
    </li>
  )
}

// One entry per consent: banks can hold several accounts.
function consents(accounts) {
  const seen = new Map()
  for (const a of accounts) {
    if (a.simulated && a.consent_id != null && !seen.has(a.consent_id)) {
      seen.set(a.consent_id, { id: a.consent_id, bank: a.bank, ends: a.consent_expires_at })
    }
  }
  return [...seen.values()]
}

function ConsentControl({ consent, onDisconnect }) {
  const [asking, setAsking] = useState(false)
  if (asking) {
    return (
      <div className="confirm" role="alertdialog" aria-label={`Disconnect ${consent.bank}?`}>
        <p>
          Disconnect {consent.bank}? Saldo deletes the accounts and transactions it
          read from {consent.bank}. You can connect again later.
        </p>
        <button type="button" className="btn-dark" onClick={() => onDisconnect(consent.id)}>
          Yes, disconnect
        </button>
        <button type="button" className="btn-plain" onClick={() => setAsking(false)}>
          Cancel
        </button>
      </div>
    )
  }
  return (
    <p className="consent-line">
      <span>
        {consent.bank} connected until {longDate(consent.ends?.slice(0, 10))}
      </span>
      <button
        type="button"
        className="btn-plain"
        aria-label={`Disconnect ${consent.bank}`}
        onClick={() => setAsking(true)}
      >
        Disconnect
      </button>
    </p>
  )
}

export default function Accounts({ data, onDisconnect, onConnect }) {
  const accounts = data?.accounts ?? []
  if (!accounts.length) return null
  return (
    <div className="section accounts" aria-label="Accounts">
      <h2 className="section-title">
        <Icon name="multibank" size={16} />
        Accounts
      </h2>
      <ul className="panel rows">
        {accounts.map((a, i) => (
          <AccountRow key={`${a.bank}-${a.iban_masked ?? i}`} account={a} />
        ))}
      </ul>
      {consents(accounts).map((c) => (
        <ConsentControl key={c.id} consent={c} onDisconnect={onDisconnect} />
      ))}
      <button type="button" className="btn-dark connect-more" onClick={onConnect}>
        Connect another bank
      </button>
    </div>
  )
}
