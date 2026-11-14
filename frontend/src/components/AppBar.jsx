import Icon from './Icon.jsx'

export default function AppBar({
  title,
  subtitle,
  onBack,
  backLabel = 'Back',
  right,
}) {
  return (
    <header className="app-bar">
      {onBack && (
        <button
          type="button"
          className="icon-btn back"
          onClick={onBack}
          aria-label={backLabel}
        >
          <Icon name="back" size={24} />
        </button>
      )}
      <div className="app-bar-title">
        <h1>{title}</h1>
        {subtitle && <small>{subtitle}</small>}
      </div>
      {right && <div className="app-bar-right">{right}</div>}
    </header>
  )
}
