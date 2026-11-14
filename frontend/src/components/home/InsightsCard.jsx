import Icon from '../Icon.jsx'
import Card from './Card.jsx'

const TONE_ICON = { good: 'check', warn: 'alert', info: 'info' }

export default function InsightsCard({ insights = [], onAsk }) {
  if (!insights.length) return null
  return (
    <Card title="Insights" icon="bulb">
      <ul className="insights">
        {insights.map((it, i) => {
          const tone = TONE_ICON[it.tone] ? it.tone : 'info'
          return (
            <li key={i}>
              <button
                type="button"
                className={`insight tone-${tone}`}
                onClick={() => onAsk(`Tell me more about this: ${it.title}`)}
              >
                <span className="insight-icon" aria-hidden="true">
                  <Icon name={TONE_ICON[tone]} size={16} strokeWidth={2.5} />
                </span>
                <span className="insight-text">
                  <strong>{it.title}</strong>
                  <span>{it.text}</span>
                </span>
                <Icon name="chevron" size={16} className="chevron" />
              </button>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
