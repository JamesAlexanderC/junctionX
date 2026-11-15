// Login screen: a Django user (manage.py createsuperuser) gets an API token.

import { useState } from 'react'
import { login } from '../api.js'
import Icon from './Icon.jsx'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await login(username, password)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <span className="logo" aria-hidden="true">
            S
          </span>
          <h1>Saldo</h1>
        </div>
      </header>

      <main className="landing">
        <div className="section">
          <h2 className="section-title">Log in</h2>
          <form className="panel picker" onSubmit={submit}>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Username"
              aria-label="Username"
              autoComplete="username"
              required
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              aria-label="Password"
              autoComplete="current-password"
              required
            />
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <div className="enter-row flush">
              <button type="submit" className="send" disabled={busy}>
                {!busy && <Icon name="login" size={16} />}
                {busy ? 'Logging in…' : 'Log in'}
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  )
}
