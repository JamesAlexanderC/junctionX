// Where the money went, from GET /api/baskets/: each spending bucket
// (#7 to #10, #75) with its share, total, trend and the categories in it.
// Every number is the backend's: this file only formats them. Tapping a
// bucket asks the coach about it.

import { eur } from '../lib/format.js'
import { Bar } from './Cards.jsx'
import Icon from './Icon.jsx'

const TOP = 3

const catText = (c) => `${c.category} ${eur(c.total)}`

function trendText(trend) {
  if (trend == null || Math.round(trend) === 0) return null
  const pts = Math.round(Math.abs(trend))
  return `${trend > 0 ? '+' : '−'}${pts} pts vs usual`
}

function BucketRow({ bucket, onAsk }) {
  const name = bucket.name || bucket.key
  const cats = bucket.categories ?? []
  const more = cats.length - TOP
  const trend = trendText(bucket.trend)
  return (
    <li>
      <button
        type="button"
        className="row goal-row"
        onClick={() => onAsk(`What's in my ${name} spending?`, 2)}
      >
        <span className="row-main">
          <span className="ins-title">{name}</span>
          <Bar value={(bucket.share ?? 0) / 100} />
          <small className="ins-text">
            {eur(bucket.total)}
            {trend && ` · ${trend}`}
          </small>
          {cats.length > 0 && (
            <small className="ins-text basket-cats">
              {cats.slice(0, TOP).map(catText).join(' · ')}
              {more > 0 && ` · +${more} more`}
            </small>
          )}
        </span>
        {bucket.share != null && (
          <strong className="ins-value">{Math.round(bucket.share)}%</strong>
        )}
        <Icon name="chevron" className="chevron" />
      </button>
      {more > 0 && (
        <details className="goal-note basket-all">
          <summary>All {cats.length} categories</summary>
          <ul>
            {cats.map((c) => (
              <li key={c.category}>{catText(c)}</li>
            ))}
          </ul>
        </details>
      )}
    </li>
  )
}

export default function Baskets({ baskets, onAsk }) {
  const buckets = baskets?.buckets ?? []
  const month = baskets?.month
  return (
    <div className="section goals" aria-label="Spending buckets">
      <h2 className="section-title">
        <Icon name="baskets" size={16} />
        Where your money went{month ? ` (${month})` : ''}
      </h2>
      <ul className="panel rows">
        {buckets.map((b) => (
          <BucketRow key={b.key} bucket={b} onAsk={onAsk} />
        ))}
        {!buckets.length && (
          <li>
            <div className="row">
              <span className="row-main">
                <span className="ins-title">No spending this month yet</span>
              </span>
            </div>
          </li>
        )}
      </ul>
      {buckets.length > 0 && (
        <p className="ins-text goal-note">Total spent: {eur(baskets.total)}</p>
      )}
    </div>
  )
}
