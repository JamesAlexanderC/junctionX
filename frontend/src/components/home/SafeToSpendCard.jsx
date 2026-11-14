import { dayLabel, eur } from '../../format.js'
import Icon from '../Icon.jsx'
import Card from './Card.jsx'

export default function SafeToSpendCard({ data: s, onAsk }) {
  const bills = s.upcoming_bills ?? []
  const billsTotal = bills.reduce((sum, b) => sum + Number(b.amount || 0), 0)
  const days = s.days_until_payday
  const tight = Number(s.per_day) < 5
  return (
    <Card
      className="safe-card"
      title="Safe to spend"
      icon="wallet"
      question="What is safe to spend this week?"
      onAsk={onAsk}
    >
      <div className="safe-hero">
        <p className="safe-per-day">
          <span className={`safe-amount${tight ? ' is-tight' : ''}`}>
            {eur(s.per_day)}
          </span>
          <span className="safe-unit">/ day</span>
        </p>
        <p className="safe-sub">
          <strong>{eur(s.amount)}</strong> in total until payday
        </p>
      </div>
      {tight && (
        <p className="safe-warn" role="note">
          <Icon name="alert" size={16} />
          Bills due before payday take up almost all of your balance.
        </p>
      )}
      <div className="payday">
        <span className="payday-count" aria-hidden="true">
          {days}
        </span>
        <span>
          <strong>
            {days === 1 ? 'day' : 'days'} until payday
          </strong>
          <small>Next salary {dayLabel(s.next_payday)}</small>
        </span>
      </div>
      {bills.length > 0 && (
        <>
          <h3 className="mini-title">
            Bills before payday <span>{eur(billsTotal, { cents: true })}</span>
          </h3>
          <ul className="bill-list">
            {bills.map((b, i) => (
              <li key={`${b.label}-${i}`}>
                <span className="bill-date">{dayLabel(b.due)}</span>
                <span className="bill-label">{b.label}</span>
                <span className="bill-amount">{eur(b.amount, { cents: true })}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="fine-print">
        Includes a {eur(s.reserve)} reserve for surprises.
      </p>
    </Card>
  )
}
