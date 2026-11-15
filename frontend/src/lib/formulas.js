// Formulas the frontend recomputes locally so sliders never call the API.
// They must match the backend (see CLAUDE.md "Shared formulas" and
// context.md #24 and #26).

const cents = (x) => Math.round(x * 100) / 100

// #24 Cut a category by p (a fraction, 0.2 = 20%).
// Monthly saving = p x mean monthly spend in that category; yearly = 12x.
export function cutSaving(monthlySpend, p) {
  const monthly = cents(Math.max(0, p) * Math.max(0, monthlySpend))
  return { monthly, yearly: cents(monthly * 12) }
}

// #26 Goal date. Months needed = ceil((target - saved) / r).
// Returns null when r <= 0 ("not reachable at the current pace").
export function goalMonths(target, saved, rate) {
  const remaining = target - saved
  if (remaining <= 0) return 0
  if (!(rate > 0)) return null
  // Match Python's months_to_goal: remove float noise, not meaningful fractions.
  return Math.ceil(Math.round((remaining / rate) * 1e9) / 1e9)
}

// Date that is `months` calendar months after `from` (ISO string or Date).
export function addMonths(from, months) {
  const d = new Date(from)
  const day = d.getUTCDate()
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + months)
  const lastDay = new Date(
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0),
  ).getUTCDate()
  d.setUTCDate(Math.min(day, lastDay))
  return d.toISOString().slice(0, 10)
}

// #26 plus #24 together: the goal date before and after a cut.
export function goalWithCut({ target, saved, monthlyRate }, extraMonthly, today) {
  const before = goalMonths(target, saved, monthlyRate)
  const after = goalMonths(target, saved, monthlyRate + extraMonthly)
  return {
    before,
    after,
    beforeDate: before == null ? null : addMonths(today, before),
    afterDate: after == null ? null : addMonths(today, after),
    monthsSooner: before != null && after != null ? before - after : null,
  }
}
