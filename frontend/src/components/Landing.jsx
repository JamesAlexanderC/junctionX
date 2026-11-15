// Demo landing page (GET /api/customers/demo/): one demo customer per app
// level (#28 to #33), then every customer to scroll through, tagged with
// their level, income level and spender type. Tap one to open their view.

import { useEffect, useState } from 'react'
import { getDemoDirectory, getMultibankCustomers, logout } from '../api.js'
import Icon from './Icon.jsx'

// Customers with simulated other-bank data (MULTIBANK_PLAN.md). The level
// demos above stay as they are; this only adds a way in.
function MultibankPicker({ customers, onEnter }) {
  if (!customers.length) return null
  return (
    <div className="section multibank-picker">
      <h2 className="section-title">
        <Icon name="multibank" size={16} />
        Other-bank demo (simulated)
      </h2>
      <select
        aria-label="Customers with other-bank data"
        defaultValue=""
        onChange={(e) => e.target.value && onEnter(e.target.value)}
      >
        <option value="" disabled>
          Choose a customer…
        </option>
        {customers.map((c) => (
          <option key={c.customer_id} value={c.customer_id}>
            {[c.customer_id, c.banks.join(' + '), c.story].filter(Boolean).join(' · ')}
          </option>
        ))}
      </select>
      <p className="muted">
        Open one, then Accounts → Connect another bank → pick the bank shown here.
      </p>
    </div>
  )
}

function CustomerRow({ c, onEnter }) {
  const tags = [c.level_name, c.income_label, c.spender_type].filter(Boolean)
  return (
    <li>
      <button type="button" className="customer-row" onClick={() => onEnter(c.customer_id)}>
        <span className="customer-id">{c.customer_id}</span>
        <span className="customer-tags">{tags.join(' · ')}</span>
        <Icon name="chevron" className="chevron" />
      </button>
    </li>
  )
}

export default function Landing({ onEnter }) {
  const [dir, setDir] = useState(null)
  const [error, setError] = useState(null)
  const [multibank, setMultibank] = useState([])

  useEffect(() => {
    const ctrl = new AbortController()
    getDemoDirectory({ signal: ctrl.signal })
      .then(setDir)
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(e.message)
      })
    // Optional: without generated other-bank data the dropdown just hides.
    getMultibankCustomers({ signal: ctrl.signal })
      .then(setMultibank)
      .catch(() => {})
    return () => ctrl.abort()
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="logo" aria-hidden="true">
            S
          </span>
          <h1>Saldo</h1>
          <div className="topbar-actions">
            <button type="button" className="logout" onClick={logout}>
              <Icon name="logout" size={16} />
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="landing">
        {error && (
          <p className="error banner" role="alert">
            <Icon name="error" />
            {error}
          </p>
        )}
        {!error && dir === null && <p className="muted">Loading customers…</p>}
        {dir && !dir.built && (
          <p className="muted">
            No customer index yet. Run <code>manage.py build_customer_index</code>.
          </p>
        )}

        <MultibankPicker customers={multibank} onEnter={onEnter} />

        {dir?.demos.length > 0 && (
          <div className="section">
            <h2 className="section-title">Demo customers</h2>
            <ul className="demo-list" aria-label="Demo customers">
              {dir.demos.map((d) => (
                <li key={d.customer_id}>
                  <button
                    type="button"
                    className="demo-customer"
                    onClick={() => onEnter(d.customer_id)}
                  >
                    <Icon name="customer" size={22} className="demo-icon" />
                    <span className="demo-label">Demo {d.demo}</span>
                    <span className="demo-level">
                      Level {d.level}: {d.level_name}
                    </span>
                    <span className="demo-meta">
                      {[d.income_label, d.spender_type].filter(Boolean).join(' · ')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {dir?.customers.length > 0 && (
          <div className="section">
            <h2 className="section-title">All customers ({dir.customers.length})</h2>
            <ul className="customer-list" aria-label="All customers">
              {dir.customers.map((c) => (
                <CustomerRow key={c.customer_id} c={c} onEnter={onEnter} />
              ))}
            </ul>
          </div>
        )}
        {dir?.built && dir.customers.length === 0 && (
          <p className="muted">No customers loaded. Run load_data first.</p>
        )}
      </main>
    </div>
  )
}
