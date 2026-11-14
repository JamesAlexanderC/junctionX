// Hash routing: '#/' is the demo landing page, '#/c/<customer_id>' is the
// customer view. Using the hash keeps refresh and Back working without a router.

import { useEffect, useState } from 'react'

const PREFIX = '#/c/'

export const customerFromHash = (hash) =>
  hash.startsWith(PREFIX) ? decodeURIComponent(hash.slice(PREFIX.length)) || null : null

export const enterCustomer = (id) => {
  window.location.hash = PREFIX + encodeURIComponent(id)
}

export const exitToDemo = () => {
  window.location.hash = '#/'
}

export function useHashRoute() {
  const [customerId, setCustomerId] = useState(() =>
    customerFromHash(window.location.hash),
  )
  useEffect(() => {
    const onChange = () => setCustomerId(customerFromHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return customerId
}
