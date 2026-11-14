import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { BASKET_COLORS, SERIES, tooltipStyle } from '../../chartTheme.js'
import { eur, monthLabel, pct } from '../../format.js'
import Card from './Card.jsx'

export default function BasketsCard({ baskets = [], lastMonth, onAsk }) {
  const total = baskets.reduce((s, b) => s + Number(b.monthly_avg || 0), 0)
  const color = (b, i) => BASKET_COLORS[b.key] ?? SERIES[i % SERIES.length]
  return (
    <Card
      title="Three baskets"
      icon="trend"
      question="Show my spending by basket"
      onAsk={onAsk}
      whole={false}
    >
      <div className="donut-row">
        <div className="donut">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={baskets}
                dataKey="monthly_avg"
                nameKey="label"
                innerRadius="66%"
                outerRadius="100%"
                paddingAngle={2}
                stroke="var(--surface)"
                strokeWidth={2}
                startAngle={90}
                endAngle={-270}
                isAnimationActive={false}
              >
                {baskets.map((b, i) => (
                  <Cell key={b.key} fill={color(b, i)} />
                ))}
              </Pie>
              <Tooltip formatter={(v, n) => [`${eur(v)}/mo`, n]} {...tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
          <span className="donut-center">
            <b>{eur(total)}</b>
            <small>per month</small>
          </span>
        </div>
        <p className="donut-note">
          Average monthly spend over 12 months, sorted into three baskets.
          {lastMonth && (
            <>
              {' '}
              {monthLabel(lastMonth.month, { year: true })}:{' '}
              <strong>{eur(lastMonth.spend)}</strong>.
            </>
          )}
        </p>
      </div>
      <ul className="basket-legend">
        {baskets.map((b, i) => (
          <li key={b.key}>
            <span className="swatch" style={{ background: color(b, i) }} />
            <span className="basket-name">
              <strong>{b.label}</strong>
              <small>
                {(b.top_categories ?? [])
                  .slice(0, 3)
                  .map((c) => `${c.category} ${eur(c.monthly_avg)}`)
                  .join(' · ')}
              </small>
            </span>
            <span className="basket-value">
              <strong>{eur(b.monthly_avg)}</strong>
              <small>{pct(b.share)}</small>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
