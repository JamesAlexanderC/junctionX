// Display helpers. Numbers are never computed here, only formatted.

export function eur(value, { decimals } = {}) {
  if (value == null || Number.isNaN(Number(value))) return '–'
  const n = Number(value)
  const digits = decimals ?? (Number.isInteger(n) ? 0 : 2)
  return `€${n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

export function pct(value, { fraction = false, decimals = 0 } = {}) {
  if (value == null) return '–'
  const n = fraction ? Number(value) * 100 : Number(value)
  return `${n.toFixed(decimals)}%`
}

export function shortDate(iso) {
  if (!iso) return '–'
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

export function longDate(iso) {
  if (!iso) return '–'
  return new Date(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export const DEPTH_NAMES = { 1: 'Quick', 2: 'Explain', 3: 'What-if', 4: 'Plan' }

export const BASKETS = [
  { key: 'essential', label: 'Essentials', hint: 'Must-pay, regular' },
  { key: 'surprise', label: 'Surprises', hint: 'Must-pay, one-off' },
  { key: 'leaky', label: 'Leaky', hint: 'Everyday spending' },
  { key: 'saver', label: 'Saver', hint: 'Money put aside' },
]

export const capitalise = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)
