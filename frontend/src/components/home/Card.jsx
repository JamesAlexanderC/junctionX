// Dashboard card. Tapping the card (or its "Ask coach" button) opens the chat
// pre-filled with a relevant question. Cards holding interactive charts set
// `whole={false}` so taps on the chart only show tooltips.

import Icon from '../Icon.jsx'

export default function Card({
  title,
  icon,
  question,
  onAsk,
  whole = true,
  className = '',
  children,
  aside,
}) {
  const ask = () => onAsk?.(question)
  const onClick = (e) => {
    if (!whole || !question) return
    // Let real controls inside the card handle their own clicks.
    if (e.target.closest('button, a, input')) return
    ask()
  }
  return (
    <section
      className={`card${whole && question ? ' card-tappable' : ''} ${className}`}
      onClick={onClick}
      aria-label={title}
    >
      {(title || aside) && (
        <header className="card-head">
          {icon && (
            <span className="card-icon" aria-hidden="true">
              <Icon name={icon} size={16} />
            </span>
          )}
          <h2>{title}</h2>
          {aside}
        </header>
      )}
      {children}
      {question && (
        <button type="button" className="ask-btn" onClick={ask}>
          <Icon name="chat" size={16} />
          <span>{question}</span>
          <Icon name="chevron" size={16} className="chevron" />
        </button>
      )}
    </section>
  )
}
