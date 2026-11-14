// Alert inbox: sorted by priority, severity colours, snooze, "Fix this",
// "Looks fine / Check" and "Help me clear my alerts".

import { useState } from 'react'
import { fixAlertQuestion, sortAlerts } from '../lib/alerts.js'
import { useApp } from '../lib/context.js'
import { shortDate } from '../lib/format.js'

const SEVERITY_LABEL = { red: 'Act now', amber: 'Heads up', blue: 'Opportunity' }

function AlertRow({ alert }) {
  const { ask, actions } = useApp()
  const [snoozing, setSnoozing] = useState(false)
  return (
    <li className={`alert-row sev-${alert.severity}`} data-testid="alert-row">
      <div className="row">
        <strong>{alert.title}</strong>
        <span className={`tag tag-${alert.severity}`}>{SEVERITY_LABEL[alert.severity]}</span>
      </div>
      <p>{alert.text}</p>
      {alert.impact_date && (
        <small className="muted">Impact {shortDate(alert.impact_date)} · #{alert.inference}</small>
      )}
      <div className="btn-row wrap">
        <button
          type="button"
          className="btn small"
          onClick={() => ask(fixAlertQuestion(alert), { depth: 4, send: true })}
        >
          Fix this
        </button>
        <button
          type="button"
          className="btn small ghost"
          onClick={() => actions.snooze?.(alert.id, 30)}
        >
          Looks fine
        </button>
        <button
          type="button"
          className="btn small ghost"
          onClick={() =>
            ask(`Why did I get the "${alert.title}" alert?`, { depth: 2, send: true })
          }
        >
          Check
        </button>
        {snoozing ? (
          [1, 7, 30].map((d) => (
            <button
              key={d}
              type="button"
              className="btn small ghost"
              onClick={() => actions.snooze?.(alert.id, d)}
            >
              {d}d
            </button>
          ))
        ) : (
          <button
            type="button"
            className="btn small ghost"
            onClick={() => setSnoozing(true)}
          >
            Snooze
          </button>
        )}
      </div>
    </li>
  )
}

export default function Alerts() {
  const { profile, ask } = useApp()
  const alerts = sortAlerts(profile.alerts, profile.today)
  return (
    <div className="alerts-screen">
      <div className="card">
        <p>
          {alerts.length === 0
            ? 'No open alerts. Nice work.'
            : `${alerts.length} open alert${alerts.length === 1 ? '' : 's'}, most urgent first.`}
        </p>
        {alerts.length > 0 && (
          <button
            type="button"
            className="btn"
            onClick={() => ask('Help me clear my alerts', { depth: 4, send: true })}
          >
            Help me clear my alerts
          </button>
        )}
      </div>
      <ul className="alert-list">
        {alerts.map((a) => (
          <AlertRow key={a.id} alert={a} />
        ))}
      </ul>
    </div>
  )
}
