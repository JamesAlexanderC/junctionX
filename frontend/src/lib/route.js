// Hash routing: '#/' is the demo landing page, '#/c/<customer_id>' is the
// customer view and '#/c/<customer_id>/help' the help page over it. Using the
// hash keeps refresh and Back working without a router.

import { useEffect, useState } from 'react'

const CUSTOMER = /^#\/c\/([^/]+)(\/help)?$/

// {customerId, help} for the current hash; customerId is null on the landing.
export function parseHash(hash) {
  const m = CUSTOMER.exec(hash)
  if (!m) return { customerId: null, help: false }
  return { customerId: decodeURIComponent(m[1]) || null, help: Boolean(m[2]) }
}

export const customerFromHash = (hash) => parseHash(hash).customerId

export const enterCustomer = (id) => {
  window.location.hash = `#/c/${encodeURIComponent(id)}`
}

export const openHelp = (id) => {
  window.location.hash = `#/c/${encodeURIComponent(id)}/help`
}

export const exitToDemo = () => {
  window.location.hash = '#/'
}

// The current location hash, updated on every change.
export function useHash() {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash
}
