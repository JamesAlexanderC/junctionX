// Search real customers via GET /api/customers/?q=.

import { useEffect, useState } from 'react'
import { getCustomers } from '../api.js'

export default function CustomerPicker({ value, onChange }) {
  const [q, setQ] = useState('')
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      getCustomers(q, { signal: ctrl.signal })
        .then((c) => {
          setList(c)
          setError(null)
          setLoading(false)
        })
        .catch((e) => {
          if (e?.name === 'AbortError') return
          setError(e.message)
          setLoading(false)
        })
    }, 200)
    return () => {
      clearTimeout(t)
      ctrl.abort()
    }
  }, [q])

  return (
    <div className="picker">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search customer id"
        aria-label="Search customer"
      />
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        aria-label="Customer"
      >
        <option value="">{loading ? 'Loading customers…' : 'Pick a customer'}</option>
        {list.map((c) => (
          <option key={c.customer_id} value={c.customer_id}>
            {c.customer_id}
            {c.customer_age != null && ` · ${c.customer_age} y`}
            {c.customer_postal_code && ` · ${c.customer_postal_code}`}
          </option>
        ))}
      </select>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
