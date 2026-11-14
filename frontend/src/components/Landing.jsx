// Demo landing page: pick a real customer, then open their view.

import { useState } from 'react'
import { logout } from '../api.js'
import CustomerPicker from './CustomerPicker.jsx'

export default function Landing({ onEnter }) {
  const [picked, setPicked] = useState(null)

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
        <div className="section">
          <h2 className="section-title">Customer</h2>
          <div className="panel">
            <CustomerPicker value={picked} onChange={setPicked} />
            <div className="enter-row">
              <button
                type="button"
                className="send"
                disabled={!picked}
                onClick={() => onEnter(picked)}
              >
                Open customer view
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
