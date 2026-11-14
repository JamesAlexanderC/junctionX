// Where the money went, from GET /api/spending/: spending per transaction
// category as the data names it. Every number is the backend's: this file
// only formats them. Tapping a category asks the coach about it.

import { eur } from '../lib/format.js'
import { Bar } from './Cards.jsx'

function CategoryRow({ row, onAsk }) {
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
            {row.count > 0 && ` · ${row.count} ${row.count === 1 ? 'payment' : 'payments'}`}
          </small>
        </span>
        {row.share != null && (
          <strong className="ins-value">{Math.round(row.share)}%</strong>
        )}
        <span className="chevron" aria-hidden="true">
          ›
        </span>
      </button>
    </li>
  )
}

export default function Spending({ spending, onAsk }) {
  const rows = spending?.categories ?? []
  const month = spending?.month
  return (
    <div className="section goals" aria-label="Spending by category">
      <h2 className="section-title">
        Spending by category{month ? ` (${month})` : ''}
      </h2>
      <ul className="panel rows">
        {rows.map((r) => (
          <CategoryRow key={r.category} row={r} onAsk={onAsk} />
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
    </div>
  )
}
