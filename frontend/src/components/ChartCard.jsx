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
import { eurCompact, formatValue } from '../format.js'

export default function ChartCard({ chart }) {
  const { kind = 'bar', title, unit, data = [] } = chart
  if (!data.length) return null
  const fmt = (v) => formatValue(v, unit)
  const tick = unit === '€' ? eurCompact : (v) => v
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
  } else {
    body = (
      <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey="label" {...axis} />
        <YAxis {...axis} width={52} tickFormatter={tick} />
        <Tooltip
          cursor={{ fill: 'var(--accent-soft)' }}
          formatter={(v) => [fmt(v), title || 'Value']}
          {...tooltipStyle}
        />
        <Bar
          dataKey="value"
          fill="var(--brand-green)"
          radius={[4, 4, 0, 0]}
          maxBarSize={36}
        />
      </BarChart>
    )
  }

  return (
    <figure className="chart-card">
      {title && <figcaption>{title}</figcaption>}
      <div className="chart-body">
        <ResponsiveContainer width="100%" height="100%">
          {body}
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
