// Lists exactly what GET /api/insights/<id>/ returned. Nothing is invented:
// an empty list renders nothing. Tapping an insight asks about it in chat.
// Rows are grouped by their `section`, in the order the backend sent them
// (alerts first), as S-mobiili style list sections.

import { formatValue } from '../lib/format.js'

const SECTION_NAMES = {
  alerts: 'Alerts',
  forecast: 'Forecast',
  income: 'Income',
  baskets: 'Spending',
  habits: 'Habits',
  goals: 'Goals',
  levels: 'Level',
  mortgage: 'Mortgage',
  benchmarks: 'Compared to others',
  multibank: 'Other banks',
}

const sectionName = (s) =>
  SECTION_NAMES[s] ?? (s ? s[0].toUpperCase() + s.slice(1) : 'More')

function groupBySection(items) {
  const groups = new Map()
  for (const it of items) {
    const key = it.section ?? ''
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(it)
  }
  return [...groups]
}

export default function Insights({ items, onAsk }) {
  if (!items?.length) return null
  return (
    <div className="insights" aria-label="Insights">
      {groupBySection(items).map(([section, rows]) => (
        <div className="section" key={section}>
          <h2 className="section-title">{sectionName(section)}</h2>
          <ul className="panel rows">
            {rows.map((it) => (
              <li key={it.key}>
                <button
                  type="button"
                  className="row"
                  onClick={() => onAsk(`Tell me about my ${it.title.toLowerCase()}`, 2)}
                >
                  <span className="row-main">
                    <span className="ins-title">
                      {it.severity && <i className={`dot sev-${it.severity}`} />}
                      {it.title}
                    </span>
                    {it.text && <small className="ins-text">{it.text}</small>}
                  </span>
                  {it.value != null && (
                    <strong className="ins-value">{formatValue(it.value, it.unit)}</strong>
                  )}
                  <span className="chevron" aria-hidden="true">
                    ›
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
