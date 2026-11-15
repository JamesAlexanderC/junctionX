// Chart card renderer: draws the backend's chart card ({kind, title, unit,
// data: [{label, value}]}) as SVG. Numbers are only drawn and formatted here,
// never computed. Tap, hover or use the arrow keys to read a point's exact
// value; a hidden table carries every value for screen readers.
//
// Forms: a line for kind "line"; columns for bars over time (month or date
// labels); horizontal bars for named categories, so long names stay readable.

import { useState } from 'react'
import {
  fitLabel,
  labelWidth,
  longLabel,
  niceTicks,
  shortLabel,
  tickText,
} from '../lib/chart.js'
import { formatValue } from '../lib/format.js'

const W = 280
const H = 160
const PAD = { top: 12, right: 8, bottom: 24, left: 46 }
const PLOT_W = W - PAD.left - PAD.right
const PLOT_H = H - PAD.top - PAD.bottom
const MAX_BAR = 24
const TIME_LABEL = /^\d{4}-\d{2}(-\d{2})?$/

// Horizontal bars: one row per category.
const ROW_H = 30
const H_BAR = 16
const NAME_MAX = 104 // widest name column before names are shortened

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

// Horizontal bar with a 4px rounded data end and a square end on zero.
function barPath(y, h, xZero, xValue) {
  const w = Math.abs(xValue - xZero)
  const r = Math.min(4, h / 2, w)
  const d = xValue >= xZero ? 1 : -1
  return `M${xZero},${y}H${xValue - d * r}Q${xValue},${y} ${xValue},${y + r}` +
    `V${y + h - r}Q${xValue},${y + h} ${xValue - d * r},${y + h}H${xZero}Z`
}

function Readout({ picked, unit, hint }) {
  return (
    <p className="chart-readout" aria-live="polite" data-testid="chart-readout">
      {picked ? (
        <>
          <span>
            {longLabel(picked.label)}
            {FLAG_TEXT[picked.flag] && ` · ${FLAG_TEXT[picked.flag]}`}
          </span>
          <strong>{formatValue(picked.value, unit)}</strong>
          {hasRange(picked) && (
            <span className="muted">{rangeText(picked, unit)}</span>
          )}
        </>
      ) : (
        <span className="muted">{hint}</span>
      )}
    </p>
  )
}

function HorizontalBars({ data, values, unit, sel, setSel, onKey, title }) {
  const n = data.length
  const names = data.map((d) => longLabel(d.label))
  const amounts = values.map((v) => formatValue(v, unit))
  const nameW = Math.min(NAME_MAX, Math.max(...names.map(labelWidth)))
  const valueW = Math.max(...amounts.map(labelWidth)) + 8
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const x0 = nameW + 10 // gap between the names and the bars
  const x1 = W - valueW
  const x = (v) => x0 + ((v - lo) / (hi - lo || 1)) * (x1 - x0)
  const xZero = x(0)
  const height = n * ROW_H

  return (
    <svg
      className="chart-svg"
      viewBox={`0 0 ${W} ${height}`}
      role="img"
      aria-label={`${title ?? 'Chart'}, bar chart`}
      tabIndex={0}
      onKeyDown={onKey}
      onPointerLeave={(e) => e.pointerType === 'mouse' && setSel(null)}
    >
      <line className="grid" x1={xZero} x2={xZero} y1={0} y2={height} />
      {values.map((v, i) => {
        const top = i * ROW_H + (ROW_H - H_BAR) / 2
        const mid = i * ROW_H + ROW_H / 2
        const end = x(v)
        return (
          <g key={i}>
            <text className="name" x={0} y={mid} dy="0.35em">
              {fitLabel(names[i], nameW)}
            </text>
            {v !== 0 && (
              <path
                className={`col${sel === i ? ' active' : ''}`}
                d={barPath(top, H_BAR, xZero, end)}
              />
            )}
            <text
              className="tick"
              x={v < 0 ? xZero + 4 : end + 4}
              y={mid}
              dy="0.35em"
            >
              {amounts[i]}
            </text>
            <rect
              className="hit"
              data-testid="chart-hit"
              x={0}
              y={i * ROW_H}
              width={W}
              height={ROW_H}
              onClick={() => setSel(i)}
              onPointerEnter={(e) => e.pointerType === 'mouse' && setSel(i)}
            />
          </g>
        )
      })}
    </svg>
  )
}

export default function ChartCard({ card }) {
  const data = (card.data ?? []).filter((d) => Number.isFinite(Number(d.value)))
  const [sel, setSel] = useState(null)
  if (!data.length) return null

  const isLine = card.kind === 'line'
  const horizontal = !isLine && !data.every((d) => TIME_LABEL.test(String(d.label)))
  // Category bars skip zero rows (nothing to draw); the table keeps them.
  const nonZero = data.filter((d) => Number(d.value) !== 0)
  const points = horizontal && nonZero.length ? nonZero : data
  const values = points.map((d) => Number(d.value))
  const n = points.length

  const onKey = (e) => {
    const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }
    const step = keys[e.key]
    if (!step) return
    e.preventDefault()
    setSel((s) => Math.max(0, Math.min(n - 1, (s ?? (step > 0 ? -1 : n)) + step)))
  }

  const table = (
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
  )
  const picked = sel != null ? points[sel] : null
  const hint = `Tap ${isLine ? 'the line' : 'a bar'} to see the exact amount`

  if (horizontal) {
    return (
      <div className="card chart-card">
        {card.title && <strong className="chart-title">{card.title}</strong>}
        <Readout picked={picked} unit={card.unit} hint={hint} />
        <HorizontalBars
          data={points}
          values={values}
          unit={card.unit}
          sel={sel}
          setSel={setSel}
          onKey={onKey}
          title={card.title}
        />
        {table}
      </div>
    )
  }

  // FC-2: points may carry the 80% band (low, high); the scale must fit it.
  const bandIdx = isLine ? data.flatMap((d, i) => (hasRange(d) ? [i] : [])) : []
  const bandValues = bandIdx.flatMap((i) => [Number(data[i].low), Number(data[i].high)])
  let lo = Math.min(...values, ...bandValues)
  let hi = Math.max(...values, ...bandValues)
  // Bars always grow from zero; a line keeps zero in view unless far away.
  if (!isLine || (lo > 0 && lo < hi * 0.5)) lo = Math.min(lo, 0)
  if (!isLine) hi = Math.max(hi, 0)
  const ticks = niceTicks(lo, hi)
  const yMin = ticks[0]
  const yMax = ticks[ticks.length - 1]
  const y = (v) => PAD.top + PLOT_H - ((v - yMin) / (yMax - yMin || 1)) * PLOT_H
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

  return (
    <div className="card chart-card">
      {card.title && <strong className="chart-title">{card.title}</strong>}
      <Readout picked={picked} unit={card.unit} hint={hint} />
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
      {table}
    </div>
  )
}
