import { eur, pct } from '../../format.js'
import { MortgageBadge } from '../ui.jsx'
import Card from './Card.jsx'

export default function HomeReadinessCard({ data: h, onAsk }) {
  if (!h) return null
  const needed = Number(h.deposit_needed) || 0
  const saved = Number(h.deposit_saved_estimate) || 0
  const progress = needed > 0 ? Math.min(1, saved / needed) : 0
  const months = h.months_to_deposit
  const deal = h.decision === 'approved' ? h.application?.final : null
  if (deal) {
    // Approved: show the real deal instead of a rule-of-thumb estimate that
    // could disagree with what the bank actually signed off.
    return (
      <Card
        className="home-card"
        title="Home readiness"
        icon="house"
        question="Am I ready to buy a home?"
        onAsk={onAsk}
        aside={<MortgageBadge decision={h.decision} />}
      >
        <p className="verdict">{h.verdict}</p>
        <div className="home-figures">
          <div>
            <small>Home price</small>
            <b>{eur(deal.property_price)}</b>
          </div>
          <div>
            <small>Loan · {pct(deal.loan_to_value)} LTV</small>
            <b>{eur(deal.loan)}</b>
          </div>
        </div>
        <p className="fine-print">
          {eur(deal.equity)} of your own money. First-home buyers can borrow up
          to 90% of the price.
        </p>
      </Card>
    )
  }
  return (
    <Card
      className="home-card"
      title="Home readiness"
      icon="house"
      question="Am I ready to buy a home?"
      onAsk={onAsk}
      aside={h.has_application && <MortgageBadge decision={h.decision} />}
    >
      <p className="verdict">{h.verdict}</p>
      <div className="home-figures">
        <div>
          <small>
            {h.decision === 'rejected' ? 'Realistic target' : 'You could afford up to'}
          </small>
          <b>{eur(h.max_property_price)}</b>
        </div>
        <div>
          <small>10% deposit needed</small>
          <b>{eur(needed)}</b>
        </div>
      </div>
      <div className="progress-head">
        <span>
          Deposit saved <strong>{eur(saved)}</strong>
        </span>
        <span>{pct(progress)}</span>
      </div>
      <div
        className="progress"
        role="progressbar"
        aria-label="Deposit saved"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
      >
        <span style={{ width: `${progress * 100}%` }} />
      </div>
      <p className="fine-print">
        {months === 0
          ? 'Deposit reached.'
          : months == null
            ? 'No monthly surplus yet to save towards a deposit.'
            : `About ${months} ${months === 1 ? 'month' : 'months'} to go at your ` +
              'current savings pace.'}{' '}
        Stress-tested at 6% over 25 years
        {Number(h.existing_debt_monthly) > 0
          ? `, counting ${eur(h.existing_debt_monthly)} a month of existing loans.`
          : '.'}
      </p>
    </Card>
  )
}
