// Connect another bank, simulated PSD2 (MULTIBANK_PLAN.md §7): choose a bank,
// a consent screen with Allow / Cancel only (never a login field), then what
// was found and the before/after card.
import { useEffect, useState } from 'react'
import { connectBank, getAccounts, getBanks } from '../api.js'
import { ReplyCard } from './Cards.jsx'
import Icon from './Icon.jsx'

const DELTA_KEYS = ['safe_to_spend', 'dsti', 'buffer_months', 'level', 'monthly_income']

function deltaCard(delta) {
  const side = (when) =>
    Object.fromEntries(DELTA_KEYS.map((k) => [k, delta?.[k]?.[when] ?? null]))
  return { type: 'before_after', before: side('before'), after: side('after') }
}

function ChooseBank({ banks, onPick }) {
  return (
    <>
      <h2 id="connect-title">Connect another bank</h2>
      <p className="ins-text">Simulated data: no real bank is contacted.</p>
      {banks === null ? (
        <p className="ins-text">Loading banks…</p>
      ) : (
        <ul className="bank-list">
          {banks.map((b) => (
            <li key={b.code}>
              <button type="button" className="row" onClick={() => onPick(b)}>
                {b.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function Consent({ bank, busy, onAllow, onCancel }) {
  return (
    <>
      <h2 id="connect-title">Allow Saldo to read {bank.name}?</h2>
      <p>
        Saldo will read your accounts, balances and transactions for 180 days. It
        cannot move money.
      </p>
      <p className="ins-text">
        You are not asked for a password. This connection is simulated.
      </p>
      <div className="sheet-actions">
        <button type="button" className="btn-dark" disabled={busy} onClick={onAllow}>
          Allow
        </button>
        <button type="button" className="btn-plain" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </>
  )
}

function Connected({ bank, result, onDone }) {
  const found = result.consent.accounts_found
  return (
    <>
      <h2 id="connect-title">Connected to {bank.name}</h2>
      <p>
        {found
          ? `Found ${found} account${found === 1 ? '' : 's'} (simulated data).`
          : result.consent.message}
      </p>
      {result.accounts.delta && <ReplyCard card={deltaCard(result.accounts.delta)} />}
      <div className="sheet-actions">
        <button type="button" className="btn-dark" onClick={onDone}>
          Done
        </button>
      </div>
    </>
  )
}

export default function ConnectBank({ customerId, onClose, onConnected }) {
  const [banks, setBanks] = useState(null)
  const [bank, setBank] = useState(null)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const ctrl = new AbortController()
    getBanks({ signal: ctrl.signal })
      .then(setBanks)
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(e.message)
      })
    return () => ctrl.abort()
  }, [])

  const allow = async () => {
    setBusy(true)
    setError(null)
    try {
      const consent = await connectBank(customerId, bank.code)
      const accounts = await getAccounts(customerId)
      setResult({ consent, accounts })
      onConnected?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sheet-backdrop">
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="connect-title">
        <button type="button" className="sheet-close" aria-label="Close" onClick={onClose}>
          <Icon name="close" size={20} />
        </button>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!bank && <ChooseBank banks={banks} onPick={setBank} />}
        {bank && !result && (
          <Consent bank={bank} busy={busy} onAllow={allow} onCancel={onClose} />
        )}
        {bank && result && <Connected bank={bank} result={result} onDone={onClose} />}
      </div>
    </div>
  )
}
