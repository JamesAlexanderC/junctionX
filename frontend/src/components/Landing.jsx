// Demo landing page (GET /api/customers/demo/): one demo customer per app
// level (#28 to #33), then every customer to scroll through, tagged with
// their level, income level and spender type. Tap one to open their view.

import { useEffect, useState } from 'react'
import { getDemoDirectory, logout } from '../api.js'

function CustomerRow({ c, onEnter }) {
  const tags = [c.level_name, c.income_label, c.spender_type].filter(Boolean)
  return (
    <li>
      <button type="button" className="customer-row" onClick={() => onEnter(c.customer_id)}>
        <span className="customer-id">{c.customer_id}</span>
        <span className="customer-tags">{tags.join(' · ')}</span>
      </button>
    </li>
  )
}

export default function Landing({ onEnter }) {
  const [dir, setDir] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    const ctrl = new AbortController()
    getDemoDirectory({ signal: ctrl.signal })
      .then(setDir)
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(e.message)
      })
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
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="landing">
        {error && (
          <p className="error banner" role="alert">
            {error}
          </p>
        )}
        {!error && dir === null && <p className="muted">Loading customers…</p>}
        {dir && !dir.built && (
          <p className="muted">
            No customer index yet. Run <code>manage.py build_customer_index</code>.
          </p>
        )}

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
