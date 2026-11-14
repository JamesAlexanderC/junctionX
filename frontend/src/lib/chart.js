// Chart axis and label helpers for Chart.jsx. Formatting only: no numbers
// are computed from the data here, apart from where to put the ticks.

import { longDate } from './format.js'

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

// "2026-07" -> "Jul", "2026-10-19" -> "19 Oct", anything else shortened.
export function shortLabel(label) {
  const s = String(label)
  let m = s.match(/^\d{4}-(\d{2})$/)
  if (m) return MONTHS[Number(m[1]) - 1] ?? s
  m = s.match(/^\d{4}-(\d{2})-(\d{2})$/)
  if (m) return `${Number(m[2])} ${MONTHS[Number(m[1]) - 1] ?? ''}`.trim()
  return s.length > 9 ? `${s.slice(0, 8)}…` : s
}

// Rough rendered width of an 11px axis label (Open Sans averages ~0.57em).
export const labelWidth = (text) => String(text).length * 6.3

// Shorten a label with "…" until it fits maxWidth (the readout shows it whole).
export function fitLabel(text, maxWidth) {
  const s = String(text)
  if (labelWidth(s) <= maxWidth) return s
  const chars = Math.max(1, Math.floor(maxWidth / 6.3) - 1)
  return `${s.slice(0, chars)}…`
}

export function longLabel(label) {
  const s = String(label)
  const m = s.match(/^(\d{4})-(\d{2})$/)
  if (m) return `${MONTHS[Number(m[2]) - 1] ?? m[2]} ${m[1]}`
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return longDate(s)
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// Axis ticks on clean steps (1, 2, 2.5, 5 x 10^n) covering [lo, hi].
export function niceTicks(lo, hi, count = 4) {
  if (lo === hi) {
    hi = lo === 0 ? 1 : lo + Math.abs(lo) * 0.1
  }
  const raw = (hi - lo) / count
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((f) => f * pow).find((s) => s >= raw)
  const start = Math.floor(lo / step) * step
  const ticks = []
  for (let t = start; t < hi + step - 1e-9; t += step) ticks.push(Number(t.toFixed(10)))
  return ticks
}

export function tickText(value, unit) {
  if (unit === '%') return `${value}%`
  const abs = Math.abs(value)
  const n = abs >= 10000 ? `${+(abs / 1000).toFixed(1)}K` : abs.toLocaleString('en-US')
  const sign = value < 0 ? '-' : ''
  return unit === 'EUR' || unit === '€' ? `${sign}€${n}` : `${sign}${n}`
}
