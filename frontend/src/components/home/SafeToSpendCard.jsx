import { dayLabel, eur } from '../../format.js'
import Icon from '../Icon.jsx'
import Card from './Card.jsx'

export default function SafeToSpendCard({ data: s, onAsk }) {
  const bills = s.upcoming_bills ?? []
  const billsTotal = bills.reduce((sum, b) => sum + Number(b.amount || 0), 0)
  const days = s.days_until_payday
  const tight = Number(s.per_day) < 5
  // Big idle balances make a per-day figure meaningless ("€3,888 a day"), so
  // lead with the total and compare it with the customer's normal pace.
  const short = billsTotal - Number(s.balance ?? billsTotal)
  const covered = Boolean(s.well_covered) && !tight
  const weekly = Number(s.typical_spend_per_day || 0) * 7
  return (
    <Card
      className="safe-card"
      title="Safe to spend"
      icon="wallet"
      question="What is safe to spend this week?"
      onAsk={onAsk}
    >
      {covered ? (
        <div className="safe-hero">
          <p className="safe-per-day">
            <span className="safe-amount">{eur(s.amount)}</span>
          </p>
          <p className="safe-sub">free until payday, after bills and a reserve</p>
        </div>
      ) : (
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
      )}
      {covered && (
        <p className="safe-note" role="note">
          <Icon name="check" size={16} strokeWidth={2.5} />
          <span>
            Well covered. Your everyday spending is usually about{' '}
            <strong>{eur(weekly)} a week</strong>.
          </span>
        </p>
      )}
      {tight && (
        <p className="safe-warn" role="note">
          <Icon name="alert" size={16} />
          {short > 0.5
            ? `Bills due before payday are ${eur(short)} more than your balance.`
            : 'Bills due before payday take up almost all of your balance.'}
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
