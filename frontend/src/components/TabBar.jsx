import Icon from './Icon.jsx'

const TABS = [
  { key: 'home', label: 'Home', icon: 'home' },
  { key: 'chat', label: 'Coach', icon: 'chat' },
]

export default function TabBar({ tab, onChange, busy }) {
  return (
    <nav className="tab-bar" aria-label="Customer sections">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          className={tab === t.key ? 'active' : ''}
          aria-current={tab === t.key ? 'page' : undefined}
          onClick={() => onChange(t.key)}
        >
          <span className="tab-icon">
            <Icon name={t.icon} size={22} />
            {t.key === 'chat' && busy && tab !== 'chat' && (
              <span className="tab-dot" aria-label="Coach is answering" />
            )}
          </span>
          {t.label}
        </button>
      ))}
    </nav>
  )
}
