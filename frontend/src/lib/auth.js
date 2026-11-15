// Re-renders on login, logout and 401s (api.js fires AUTH_EVENT), and when
// another tab changes the stored token.

import { useEffect, useState } from 'react'
import { AUTH_EVENT, isLoggedIn } from '../api.js'

export function useLoggedIn() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn)
  useEffect(() => {
    const sync = () => setLoggedIn(isLoggedIn())
    window.addEventListener(AUTH_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(AUTH_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  return loggedIn
}
