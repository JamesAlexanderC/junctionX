// One chat turn. Assistant turns can carry tool status, charts and concepts.

import ChartCard from './ChartCard.jsx'
import Icon from './Icon.jsx'
import RichText from './RichText.jsx'

function ToolStatus({ tools, pending, answering }) {
  if (!tools?.length) return null
  // While the coach is still looking things up, show the latest step live.
  if (pending && !answering) {
    const current = tools[tools.length - 1]
    return (
      <p className="tool-status live">
        <span className="spinner" aria-hidden="true" />
        <span key={current.label} className="tool-label">
          {current.label || 'Looking into your data…'}
        </span>
      </p>
    )
  }
  const n = tools.length
  return (
    <p
      className="tool-status done"
      title={tools.map((t) => t.label || t.name).join('\n')}
    >
      <Icon name="check" size={13} strokeWidth={2.5} />
      Based on your data · {n} {n === 1 ? 'check' : 'checks'}
    </p>
  )
}

export default function Message({ msg }) {
  if (msg.role === 'user') {
    return <div className="bubble user">{msg.content}</div>
  }
  const answering = Boolean(msg.content)
  const waiting = msg.pending && !answering
  const showTyping = waiting && !msg.tools?.length

  return (
    <div className="assistant" aria-busy={msg.pending || undefined}>
      <span className="coach-avatar" aria-hidden="true">
        <Icon name="sparkle" size={16} />
      </span>
      <div className="assistant-body">
        <ToolStatus tools={msg.tools} pending={msg.pending} answering={answering} />
        {(answering || showTyping || msg.error) && (
          <div className={`bubble coach${msg.error ? ' error' : ''}`}>
            {showTyping ? (
              <span className="typing" role="status" aria-label="Coach is thinking">
                <i />
                <i />
                <i />
              </span>
            ) : (
              <RichText text={msg.content} />
            )}
          </div>
        )}
        {msg.stopped && (
          <p className="stopped-note">
            <Icon name="stop" size={12} /> Stopped
          </p>
        )}
        {msg.charts?.map((c, i) => (
          <ChartCard key={i} chart={c} />
        ))}
        {msg.concepts?.map((c, i) => (
          <aside key={i} className="concept">
            <span className="concept-icon" aria-hidden="true">
              <Icon name="bulb" size={18} />
            </span>
            <div>
              <strong>{c.title}</strong>
              <p>{c.text}</p>
            </div>
          </aside>
        ))}
      </div>
    </div>
  )
}
