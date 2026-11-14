// Shared formatting helpers. Money is always shown as "€1,234" (whole euros)
// or "€1,234.50" when cents matter, everywhere in the app.

const whole = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
})
const cents = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const compact = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  notation: 'compact',
  maximumFractionDigits: 1,
})

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0)

/** "€1,234"; pass `{ cents: true }` for "€1,234.50". */
export function eur(value, opts = {}) {
  return (opts.cents ? cents : whole).format(num(value))
}

/** Axis ticks: "€1.2K". */
export const eurCompact = (value) => compact.format(num(value))

export const pct = (value) => `${Math.round(num(value) * 100)}%`

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
  'Oct', 'Nov', 'Dec']

/** "2026-09" -> "Sep"; with `year` -> "Sep 2026". */
export function monthLabel(ym, { year = false } = {}) {
  const [y, m] = String(ym).split('-')
  const name = MONTHS[Number(m) - 1] ?? ym
  return year ? `${name} ${y}` : name
}

/** "2026-10-05" -> "5 Oct". */
export function dayLabel(iso) {
  if (!iso) return ''
  const [, m, d] = String(iso).split('-')
  return `${Number(d)} ${MONTHS[Number(m) - 1] ?? ''}`.trim()
}

/** "2026-09-30" -> "30 Sep 2026". */
export const fullDate = (iso) =>
  iso ? `${dayLabel(iso)} ${String(iso).slice(0, 4)}` : ''

/** Formats a chart value according to the chart's unit. */
export function formatValue(value, unit) {
  if (unit === '€') return eur(value, { cents: !Number.isInteger(num(value)) })
  return `${num(value).toLocaleString('en-IE')}${unit ? ` ${unit}` : ''}`
}

export const personaInitials = (label = '') =>
  label
    .split(/[\s-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')

// Friendlier names for a few dataset categories (matches the coach's wording).
const CATEGORY_NAMES = {
  Restaurants: 'Dining out',
  Lifestyle: 'Shopping & lifestyle',
  Transportation: 'Transport',
}
export const categoryName = (category) => CATEGORY_NAMES[category] ?? category
