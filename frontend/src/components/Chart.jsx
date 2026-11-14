// Chart card renderer: draws the backend's chart card ({kind, title, unit,
// data: [{label, value}]}) as an SVG bar or line chart. Numbers are only
// drawn and formatted here, never computed. Tap, hover or use the arrow keys
// to read a point's exact value; a hidden table carries every value for
// screen readers.

import { useState } from 'react'
import { longLabel, niceTicks, shortLabel, tickText } from '../lib/chart.js'
import { formatValue } from '../lib/format.js'

const W = 280
const H = 160
const PAD = { top: 12, right: 8, bottom: 24, left: 46 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom
const MAX_BAR = 24
// FC-2: what a flagged day means; the backend decides which days are which.
const FLAG_TEXT = { danger: 'Tight day', bill: 'Bill due', payday: 'Payday' }

const isNum = (v) => v != null && Number.isFinite(Number(v))
const hasRange = (d) => isNum(d.low) && isNum(d.high)
const rangeText = (d, unit) =>
  `likely ${formatValue(d.low, unit)} to ${formatValue(d.high, unit)}`
// Which x labels to print so they never collide (always the first and last).
function labelIndexes(n) {
  if (n <= 6) return new Set([...Array(n).keys()])
  const every = Math.ceil(n / 4)
  const out = new Set([0, n - 1])
  // Stop short of the end so the last label keeps clear of its neighbour.
  for (let i = every; i <= n - 1 - every * 0.75; i += every) out.add(i)
  return out
}

// Column with a 4px rounded data end and a square end on the zero line.
function columnPath(x, w, yZero, yValue) {
  const h = Math.abs(yZero - yValue)
  const r = Math.min(4, w / 2, h)
  if (yValue <= yZero) {
    return `M${x},${yZero}V${yValue + r}Q${x},${yValue} ${x + r},${yValue}` +
      `H${x + w - r}Q${x + w},${yValue} ${x + w},${yValue + r}V${yZero}Z`
  }
  return `M${x},${yZero}V${yValue - r}Q${x},${yValue} ${x + r},${yValue}` +
    `H${x + w - r}Q${x + w},${yValue} ${x + w},${yValue - r}V${yZero}Z`
}

export default function ChartCard({ card }) {
  const data = (card.data ?? []).filter((d) => Number.isFinite(Number(d.value)))
  const [sel, setSel] = useState(null)
  if (!data.length) return null

  const isLine = card.kind === 'line'
  const values = data.map((d) => Number(d.value))
  // FC-2: points may carry the 80% band (low, high); the scale must fit it.
  const bandIdx = isLine ? data.flatMap((d, i) => (hasRange(d) ? [i] : [])) : []
  const bandValues = bandIdx.flatMap((i) => [Number(data[i].low), Number(data[i].high)])
  let lo = Math.min(...values, ...bandValues)
  let hi = Math.max(...values, ...bandValues)
  // Bars always grow from zero; a line keeps zero in view unless far away.
  if (!isLine || lo > 0 && lo < hi * 0.5) lo = Math.min(lo, 0)
  if (!isLine) hi = Math.max(hi, 0)
  const ticks = niceTicks(lo, hi)
  const yMin = ticks[0]
  const yMax = ticks[ticks.length - 1]
  const y = (v) => PAD.top + PLOT_H - ((v - yMin) / (yMax - yMin || 1)) * PLOT_H
  const n = data.length
  const band = PLOT_W / n
  const cx = (i) => PAD.left + band * (i + 0.5)
  const shown = labelIndexes(n)
  const yZero = y(Math.max(yMin, Math.min(0, yMax)))

  const linePath = values.map((v, i) => `${i ? 'L' : 'M'}${cx(i)},${y(v)}`).join('')
  const areaPath = `${linePath}L${cx(n - 1)},${yZero}L${cx(0)},${yZero}Z`
  const bandPath = bandIdx.length
    ? bandIdx.map((i, k) => `${k ? 'L' : 'M'}${cx(i)},${y(Number(data[i].high))}`).join('') +
      [...bandIdx].reverse().map((i) => `L${cx(i)},${y(Number(data[i].low))}`).join('') +
      'Z'
    : ''
  const lastBand = bandIdx[bandIdx.length - 1]

  // Edge labels on a dense line hug the plot so they never spill out.
  const xAnchor = (i) => {
    if (!isLine || n <= 6) return 'middle'
    return i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'
  }

  const onKey = (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const step = e.key === 'ArrowRight' ? 1 : -1
    setSel((s) => Math.max(0, Math.min(n - 1, (s ?? (step > 0 ? -1 : n)) + step)))
  }

  const picked = sel != null ? data[sel] : null

  return (
    <div className="card chart-card">
      {card.title && <strong className="chart-title">{card.title}</strong>}
      <p className="chart-readout" aria-live="polite" data-testid="chart-readout">
        {picked ? (
          <>
            <span>
              {longLabel(picked.label)}
              {FLAG_TEXT[picked.flag] && ` · ${FLAG_TEXT[picked.flag]}`}
            </span>
            <strong>{formatValue(picked.value, card.unit)}</strong>
            {hasRange(picked) && (
              <span className="muted">{rangeText(picked, card.unit)}</span>
            )}
          </>
        ) : (
          <span className="muted">
            Tap {isLine ? 'the line' : 'a bar'} to see the exact amount
          </span>
        )}
      </p>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`${card.title ?? 'Chart'}, ${isLine ? 'line' : 'bar'} chart`}
        tabIndex={0}
        onKeyDown={onKey}
        onPointerLeave={(e) => e.pointerType === 'mouse' && setSel(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              className="grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
            />
            <text
              className="tick"
              x={PAD.left - 6}
              y={y(t)}
              textAnchor="end"
              dy="0.32em"
            >
              {tickText(t, card.unit)}
            </text>
          </g>
        ))}

        {isLine ? (
          <>
            {bandPath ? (
              <>
                <path className="band" d={bandPath} />
                <text
                  className="band-label"
                  x={cx(lastBand)}
                  y={Math.max(PAD.top + 8, y(Number(data[lastBand].high)) - 4)}
                  textAnchor="end"
                >
                  likely range
                </text>
              </>
            ) : (
              <path className="area" d={areaPath} />
            )}
            <path className="line" d={linePath} />
            {data.map((d, i) =>
              FLAG_TEXT[d.flag] ? (
                <circle
                  key={`m${i}`}
                  className={`marker ${d.flag}`}
                  cx={cx(i)}
                  cy={y(values[i])}
                  r={3.5}
                />
              ) : null,
            )}
            {sel != null && (
              <line
                className="crosshair"
                x1={cx(sel)}
                x2={cx(sel)}
                y1={PAD.top}
                y2={PAD.top + PLOT_H}
              />
            )}
            {/* End dot by default, so even a one-point line shows. */}
            <circle
              className="dot"
              cx={cx(sel ?? n - 1)}
              cy={y(values[sel ?? n - 1])}
              r={4.5}
            />
          </>
        ) : (
          values.map((v, i) => {
            const w = Math.min(MAX_BAR, band * 0.6)
            return (
              <path
                key={i}
                className={`col${sel === i ? ' active' : ''}`}
                d={columnPath(cx(i) - w / 2, w, yZero, y(v))}
              />
            )
          })
        )}

        {data.map((d, i) =>
          shown.has(i) ? (
            <text
              key={i}
              className="tick"
              x={cx(i)}
              y={H - 6}
              textAnchor={xAnchor(i)}
            >
              {shortLabel(d.label)}
            </text>
          ) : null,
        )}

        {/* Hit targets: the whole column band, bigger than the mark. */}
        {data.map((d, i) => (
          <rect
            key={i}
            className="hit"
            data-testid="chart-hit"
            x={PAD.left + band * i}
            y={PAD.top}
            width={band}
            height={PLOT_H}
            onClick={() => setSel(i)}
            onPointerEnter={(e) => e.pointerType === 'mouse' && setSel(i)}
          />
        ))}
      </svg>

      <table className="sr-only">
        <caption>{card.title}</caption>
        <tbody>
          {data.map((d, i) => (
            <tr key={i}>
              <th scope="row">
                {longLabel(d.label)}
                {FLAG_TEXT[d.flag] && ` (${FLAG_TEXT[d.flag]})`}
              </th>
              <td>
                {formatValue(d.value, card.unit)}
                {hasRange(d) && `, ${rangeText(d, card.unit)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
