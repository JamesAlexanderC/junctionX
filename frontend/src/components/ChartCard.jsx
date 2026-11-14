// Chart payloads streamed by the coach: { kind, title, unit, data[] }.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { axisProps as axis, SERIES, tooltipStyle } from '../chartTheme.js'
import { eur, eurCompact, formatValue } from '../format.js'

export default function ChartCard({ chart }) {
  const { kind = 'bar', title, unit, data = [] } = chart
  if (!data.length) return null
  const fmt = (v) => formatValue(v, unit)
  const tick = unit === '€' ? eurCompact : (v) => v
  // Negative values (a month in the red, a category that went down) get a
  // second colour so the sign reads at a glance.
  const barColor = (d) => (Number(d.value) < 0 ? SERIES[3] : 'var(--brand-green)')
  const rows = data.map((d) => ({
    ...d,
    shown: unit === '€' ? eur(d.value) : d.value,
  }))
  const longest = Math.max(...data.map((d) => String(d.label).length))
  const horizontal = kind === 'bar' && longest > 6
  const labelWidth = Math.min(150, Math.max(64, longest * 7 + 8))
  const tooltip = (
    <Tooltip formatter={(v) => [fmt(v), title || 'Value']} {...tooltipStyle} />
  )

  let body
  if (kind === 'pie') {
    const total = data.reduce((s, d) => s + Number(d.value || 0), 0)
    return (
      <figure className="chart-card">
        {title && <figcaption>{title}</figcaption>}
        <div className="pie-wrap">
          <div className="pie-body">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="label"
                  innerRadius="58%"
                  outerRadius="92%"
                  paddingAngle={2}
                  stroke="var(--surface)"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {data.map((d, i) => (
                    <Cell key={d.label} fill={SERIES[i % SERIES.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v, n) => [fmt(v), n]} {...tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="legend">
            {data.map((d, i) => (
              <li key={d.label}>
                <span
                  className="swatch"
                  style={{ background: SERIES[i % SERIES.length] }}
                />
                <span className="legend-label">{d.label}</span>
                <span className="legend-value">
                  {fmt(d.value)}
                  {total > 0 && (
                    <small> · {Math.round((d.value / total) * 100)}%</small>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </figure>
    )
  }
  if (kind === 'line') {
    body = (
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} width={52} tickFormatter={tick} />
        {tooltip}
        <Line
          type="monotone"
          dataKey="value"
          stroke="var(--brand-green)"
          strokeWidth={2.5}
          dot={{
            r: 4,
            fill: 'var(--brand-green)',
            stroke: 'var(--surface)',
            strokeWidth: 2,
          }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    )
  } else if (horizontal) {
    // Long category labels ("17 Sep Groceries") don't fit under vertical
    // bars on a phone, so lay the bars out sideways with the value at the end.
    body = (
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 0, right: 4, left: 0, bottom: 0 }}
      >
        <XAxis type="number" hide domain={[(min) => Math.min(0, min), 'auto']} />
        <YAxis
          yAxisId="label"
          type="category"
          dataKey="label"
          {...axis}
          tick={{ ...axis.tick, fontSize: 12, fill: 'var(--body)' }}
          width={labelWidth}
          interval={0}
        />
        <YAxis
          yAxisId="value"
          orientation="right"
          type="category"
          dataKey="shown"
          {...axis}
          tick={{ ...axis.tick, fontSize: 12, fontWeight: 700, fill: 'var(--text)' }}
          width={64}
          interval={0}
        />
        <Tooltip
          cursor={{ fill: 'var(--accent-soft)' }}
          formatter={(v) => [fmt(v), title || 'Value']}
          {...tooltipStyle}
        />
        <Bar
          yAxisId="label"
          dataKey="value"
          radius={4}
          maxBarSize={22}
          isAnimationActive={false}
        >
          {data.map((d) => (
            <Cell key={d.label} fill={barColor(d)} />
          ))}
        </Bar>
      </BarChart>
    )
  } else {
    body = (
      <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="label" {...axis} interval={data.length > 8 ? 1 : 0} />
        <YAxis {...axis} width={52} tickFormatter={tick} />
        <Tooltip
          cursor={{ fill: 'var(--accent-soft)' }}
          formatter={(v) => [fmt(v), title || 'Value']}
          {...tooltipStyle}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36}>
          {data.map((d) => (
            <Cell key={d.label} fill={barColor(d)} />
          ))}
        </Bar>
      </BarChart>
    )
  }

  return (
    <figure className="chart-card">
      {title && <figcaption>{title}</figcaption>}
      <div
        className="chart-body"
        style={horizontal ? { height: data.length * 34 + 16 } : undefined}
      >
        <ResponsiveContainer width="100%" height="100%">
          {body}
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
