// Display helpers. Numbers are never computed here, only formatted.

export function eur(value) {
  if (value == null || Number.isNaN(Number(value))) return '–'
  const n = Number(value)
  const digits = Number.isInteger(n) ? 0 : 2
  return `${n < 0 ? '-' : ''}€${Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

const isEur = (unit) => unit === 'EUR' || unit === '€'

// Value with its unit, exactly as the backend gave it.
export function formatValue(value, unit) {
  // Breakdowns (e.g. baskets) are objects; their text already spells them out.
  if (value == null || typeof value === 'object') return ''
  if (unit === 'date') return longDate(value)
  if (isEur(unit)) return eur(value)
  if (unit === '%') return `${value}%`
  return unit ? `${value} ${unit}` : String(value)
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
