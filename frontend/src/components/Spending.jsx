// Where the money went, from GET /api/spending/: spending per transaction
// category as the data names it, each against its usual month (#24 3-month
// mean), and money moved into savings listed apart (#75, not spending).
// Every number is the backend's: this file only formats them. Tapping a
// category asks the coach about it.

import { eur } from '../lib/format.js'
import { Bar } from './Cards.jsx'
import Icon from './Icon.jsx'

const payments = (n) => (n > 0 ? ` · ${n} ${n === 1 ? 'payment' : 'payments'}` : '')

// "Usually €90 a month · €10 more" from the backend's usual and vs_usual.
function usualText(row, soFar) {
  if (row.usual == null) return null
  const diff = row.vs_usual ?? 0
  const when = soFar ? ' so far' : ''
  const cmp =
    Math.round(diff) === 0
      ? 'about the same'
      : `${eur(Math.abs(diff))} ${diff > 0 ? 'more' : 'less'}${when}`
  return `Usually ${eur(row.usual)} a month · ${cmp}`
}

function CategoryRow({ row, soFar, onAsk }) {
  const usual = usualText(row, soFar)
  return (
    <li>
      <button
        type="button"
        className="row goal-row"
        onClick={() => onAsk(`Tell me about my ${row.category} spending`, 2)}
      >
        <span className="row-main">
          <span className="ins-title">{row.category}</span>
          <Bar value={(row.share ?? 0) / 100} />
          <small className="ins-text">
            {eur(row.total)}
            {payments(row.count)}
          </small>
          {usual && <small className="ins-text">{usual}</small>}
        </span>
        {row.share != null && (
          <strong className="ins-value">{Math.round(row.share)}%</strong>
        )}
        <Icon name="chevron" className="chevron" />
      </button>
    </li>
  )
}

export default function Spending({ spending, onAsk }) {
  const rows = spending?.categories ?? []
  const savings = spending?.savings ?? []
  const month = spending?.month
  return (
    <div className="section goals" aria-label="Spending by category">
      <h2 className="section-title">
        <Icon name="baskets" size={16} />
        Spending by category{month ? ` (${month})` : ''}
      </h2>
      <ul className="panel rows">
        {rows.map((r) => (
          <CategoryRow
            key={r.category}
            row={r}
            soFar={Boolean(spending?.is_current)}
            onAsk={onAsk}
          />
        ))}
        {!rows.length && (
          <li>
            <div className="row">
              <span className="row-main">
                <span className="ins-title">No spending this month yet</span>
              </span>
            </div>
          </li>
        )}
      </ul>
      {rows.length > 0 && (
        <p className="ins-text goal-note">Total spent: {eur(spending.total)}</p>
      )}
      {savings.length > 0 && (
        <>
          <h2 className="section-title">
            <Icon name="income" size={16} />
            Saved ({eur(spending.savings_total)})
          </h2>
          <ul className="panel rows" aria-label="Savings">
            {savings.map((r) => (
              <li key={r.category}>
                <div className="row">
                  <span className="row-main">
                    <span className="ins-title goal-head">
                      {r.category}
                      <span className="tag">Savings</span>
                    </span>
                    <small className="ins-text">
                      {eur(r.total)}
                      {payments(r.count)}
                    </small>
                  </span>
                </div>
              </li>
            ))}
          </ul>
          <p className="ins-text goal-note">
            Money moved into savings is not counted as spending.
          </p>
        </>
      )}
    </div>
  )
}
