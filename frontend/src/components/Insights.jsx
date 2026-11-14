// Lists exactly what GET /api/insights/<id>/ returned. Nothing is invented:
// an empty list renders nothing. Tapping an insight asks about it in chat.

import { formatValue } from '../lib/format.js'

export default function Insights({ items, onAsk }) {
  if (!items?.length) return null
  return (
    <ul className="insights" aria-label="Insights">
      {items.map((it) => (
        <li key={it.key}>
          <button
            type="button"
            onClick={() => onAsk(`Tell me about my ${it.title.toLowerCase()}`, 2)}
          >
            <span className="ins-title">
              {it.severity && <i className={`dot sev-${it.severity}`} />}
              {it.title}
            </span>
            {it.value != null && (
              <strong className="ins-value">{formatValue(it.value, it.unit)}</strong>
            )}
            {it.text && <small className="ins-text">{it.text}</small>}
          </button>
        </li>
      ))}
    </ul>
  )
}
