import test from 'node:test'
import assert from 'node:assert/strict'
import { curveRows, lastSyncedLabel, riskTone, signed, skipLine } from './monitoring.js'

test('skipLine states limit, used and remaining hours', () => {
  assert.equal(skipLine({ limit: 9, absent: 4 }), 'Absence limit: 9. You have: 4. Remaining: 5.')
  assert.equal(skipLine({ limit: 8, absent: 11 }), 'Absence limit: 8. You have: 11. Remaining: 0.')
})

test('riskTone maps a percentage to green, yellow or red', () => {
  assert.deepEqual([10, 25, 49, 50, 90].map(riskTone), ['success', 'warning', 'warning', 'danger', 'danger'])
  assert.equal(riskTone(null), 'neutral')
})

test('signed shows direction with a real minus sign', () => {
  assert.equal(signed(0.24), '+0.2')
  assert.equal(signed(-0.31), '−0.3')
  assert.equal(signed(0), '0.0')
  assert.equal(signed(-12, 0, '%'), '−12%')
})

test('curveRows converts risk to percent', () => {
  assert.deepEqual(curveRows([{ hours: 2, risk: 0.153, predicted_gpa: 3.4, fx: false }]), [{ hours: 2, risk: 15, gpa: 3.4, fx: false }])
})

test('lastSyncedLabel counts minutes, hours and days', () => {
  const now = Date.parse('2026-11-21T12:00:00Z')
  assert.equal(lastSyncedLabel('2026-11-21T11:55:00Z', now), 'Last synced: 5 mins ago')
  assert.equal(lastSyncedLabel('2026-11-21T11:59:40Z', now), 'Last synced: just now')
  assert.equal(lastSyncedLabel('2026-11-21T09:00:00Z', now), 'Last synced: 3 hours ago')
  assert.equal(lastSyncedLabel(null, now), 'Not synced yet')
})
