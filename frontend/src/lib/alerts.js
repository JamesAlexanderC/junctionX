// Alert ordering for the inbox and the home nudge (context.md "Alert coach").
// priority = w_severity / max(1, days until impact); red 3, amber 2, blue 1.
// The backend sends `priority`; we only recompute it when it is missing.

export const SEVERITY_WEIGHT = { red: 3, amber: 2, blue: 1 }

const DAY = 24 * 60 * 60 * 1000

export function alertPriority(alert, today) {
  if (typeof alert.priority === 'number') return alert.priority
  const w = SEVERITY_WEIGHT[alert.severity] ?? 1
  if (!alert.impact_date || !today) return w
  const days = Math.round((new Date(alert.impact_date) - new Date(today)) / DAY)
  return w / Math.max(1, days)
}

export function isSnoozed(alert, today) {
  return Boolean(alert.snoozed_until && today && alert.snoozed_until > today)
}

export function sortAlerts(alerts = [], today) {
  return alerts
    .filter((a) => !isSnoozed(a, today))
    .map((a) => ({ ...a, priority: alertPriority(a, today) }))
    .sort(
      (a, b) =>
        b.priority - a.priority ||
        (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0),
    )
}

// Home shows at most one red or amber nudge: the highest priority one.
export function topNudgeAlert(alerts, today) {
  return (
    sortAlerts(alerts, today).find(
      (a) => a.severity === 'red' || a.severity === 'amber',
    ) ?? null
  )
}

export const fixAlertQuestion = (alert) =>
  `Help me fix this alert: ${alert.title}`
