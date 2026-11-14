import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { axisProps, CASHFLOW, tooltipStyle } from '../../chartTheme.js'
import { eur, eurCompact, monthLabel } from '../../format.js'
import Card from './Card.jsx'

const NAMES = { income: 'Income', spend: 'Spend', net: 'Net' }

export default function CashflowCard({ data = [], onAsk }) {
  const rows = data.map((d) => ({ ...d, label: monthLabel(d.month) }))
  const totalNet = data.reduce((s, d) => s + Number(d.net || 0), 0)
  const positive = data.filter((d) => d.net >= 0).length
  return (
    <Card
      title="12-month cashflow"
      icon="calendar"
      question="How has my spending changed over the last year?"
      onAsk={onAsk}
      whole={false}
    >
      <p className="card-lede">
        <strong className={totalNet >= 0 ? 'pos' : 'neg'}>
          {totalNet >= 0 ? '+' : '−'}
          {eur(Math.abs(totalNet))}
        </strong>{' '}
        net over 12 months · {positive} of {data.length} months in the green
      </p>
      <ul className="series-legend" aria-hidden="true">
        <li>
          <span className="swatch" style={{ background: CASHFLOW.income }} /> Income
        </li>
        <li>
          <span className="swatch" style={{ background: CASHFLOW.spend }} /> Spend
        </li>
        <li>
          <span className="swatch line" style={{ background: CASHFLOW.net }} /> Net
        </li>
      </ul>
      <div
        className="cashflow-chart"
        role="img"
        aria-label="Monthly income, spend and net"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={rows}
            margin={{ top: 8, right: 4, left: 0, bottom: 0 }}
            barGap={2}
            barCategoryGap="22%"
          >
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="label" {...axisProps} interval={0} fontSize={10} />
            <YAxis {...axisProps} width={46} tickFormatter={eurCompact} />
            <ReferenceLine y={0} stroke="var(--border-strong)" />
            <Tooltip
              cursor={{ fill: 'var(--accent-soft)' }}
              formatter={(v, n) => [eur(v), NAMES[n] ?? n]}
              labelFormatter={(_, p) =>
                monthLabel(p?.[0]?.payload?.month, { year: true })
              }
              {...tooltipStyle}
            />
            <Bar dataKey="income" fill={CASHFLOW.income} radius={[3, 3, 0, 0]} />
            <Bar dataKey="spend" fill={CASHFLOW.spend} radius={[3, 3, 0, 0]} />
            <Line
              type="monotone"
              dataKey="net"
              stroke={CASHFLOW.net}
              strokeWidth={2}
              dot={{
                r: 2.5,
                fill: CASHFLOW.net,
                stroke: 'var(--surface)',
                strokeWidth: 1.5,
              }}
              activeDot={{ r: 5 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>Monthly cashflow</caption>
        <thead>
          <tr>
            <th>Month</th>
            <th>Income</th>
            <th>Spend</th>
            <th>Net</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.month}>
              <td>{monthLabel(d.month, { year: true })}</td>
              <td>{eur(d.income)}</td>
              <td>{eur(d.spend)}</td>
              <td>{eur(d.net)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
