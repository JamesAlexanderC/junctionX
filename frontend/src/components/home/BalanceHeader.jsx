import { eur, fullDate, pct } from '../../format.js'
import { MortgageBadge } from '../ui.jsx'

export default function BalanceHeader({ overview: o }) {
  const net = o.income_monthly_avg - o.spend_monthly_avg
  return (
    <section className="balance-header" aria-label="Account balance">
      <p className="balance-label">Balance · {fullDate(o.as_of)}</p>
      <p className="balance-amount">{eur(o.balance, { cents: true })}</p>
      <div className="balance-chips">
        <span className="chip-light">{o.persona?.label}</span>
        {o.customer?.has_mortgage_application && (
          <MortgageBadge decision={o.customer.mortgage_decision} />
        )}
      </div>
      <dl className="balance-stats">
        <div>
          <dt>Income / mo</dt>
          <dd>{eur(o.income_monthly_avg)}</dd>
        </div>
        <div>
          <dt>Spend / mo</dt>
          <dd>{eur(o.spend_monthly_avg)}</dd>
        </div>
        <div>
          <dt>Savings rate</dt>
          <dd className={net >= 0 ? 'pos' : 'neg'}>{pct(o.savings_rate)}</dd>
        </div>
      </dl>
    </section>
  )
}
