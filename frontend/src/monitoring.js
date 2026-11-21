// Pure helpers for the Monitoring tab (kept free of React so they can be unit-tested with `node --test`).

export const LEVEL_TONE = { safe: 'success', warning: 'warning', danger: 'danger', unknown: 'neutral' }
export const RISK_TONE = { low: 'success', medium: 'warning', high: 'danger' }
export const SEVERITY_TONE = { critical: 'danger', high: 'danger', medium: 'warning', info: 'neutral' }
export const SEVERITY_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', info: 'Info' }

/** "Absence limit: 9. You have: 4. Remaining: 5." */
export function skipLine(course) {
  return `Absence limit: ${course.limit}. You have: ${course.absent}. Remaining: ${Math.max(0, course.limit - course.absent)}.`
}

/** Colour of a risk percentage: green below 25, yellow below 50, red from 50. */
export function riskTone(percent) {
  if (percent == null) return 'neutral'
  return percent >= 50 ? 'danger' : percent >= 25 ? 'warning' : 'success'
}

/** Shape the simulation curve for the chart: risk in %, GPA as is. */
export function curveRows(curve = []) {
  return curve.map(p => ({ hours: p.hours, risk: Math.round(p.risk * 100), gpa: p.predicted_gpa, fx: !!p.fx }))
}

/** "+0.2" / "-0.3" / "0.0" for GPA and risk changes. */
export function signed(value, digits = 1, unit = '') {
  if (value == null || Number.isNaN(value)) return '—'
  const n = Number(value)
  if (Math.abs(n) < 10 ** -digits / 2) return `${(0).toFixed(digits)}${unit}`
  return `${n > 0 ? '+' : '−'}${Math.abs(n).toFixed(digits)}${unit}`
}

/** Plain-language "Last synced: 5 mins ago" from an ISO time. */
export function lastSyncedLabel(iso, now = Date.now()) {
  if (!iso) return 'Not synced yet'
  const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000))
  if (Number.isNaN(mins)) return 'Not synced yet'
  if (mins < 1) return 'Last synced: just now'
  if (mins < 60) return `Last synced: ${mins} ${mins === 1 ? 'min' : 'mins'} ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `Last synced: ${hours} ${hours === 1 ? 'hour' : 'hours'} ago`
  const days = Math.floor(hours / 24)
  return `Last synced: ${days} ${days === 1 ? 'day' : 'days'} ago`
}
