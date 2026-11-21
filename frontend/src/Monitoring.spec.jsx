import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DifficultForecast, MonitoringTab, PredictedGpaWidget, SyncBar } from './Monitoring.jsx'

afterEach(cleanup)

const course = (over = {}) => ({
  code: 'INF 451', name: 'Databases', hours: 30, limit: 8, absent: 4, pending: 0, permitted: 0,
  remaining_skips: 4, remaining_if_pending_absent: 4, absence_pct: 13.3, used_pct: 50, level: 'safe', fx: false, ...over,
})

const overview = (over = {}) => ({
  has_data: true, data_source: 'sdu_journal', last_synced: new Date(Date.now() - 5 * 60000).toISOString(),
  model: { version: 'test-1' },
  safe_to_skip: {
    items: [course(), course({ code: 'MAT 101', name: 'Math', limit: 9, absent: 11, remaining_skips: 0, level: 'danger', fx: true, used_pct: 100 })],
    level: 'danger', rule: 'A course ends in FX at 30% absence (attendance below 70%).',
  },
  risk: {
    risk: 0.62, risk_percent: 62, level: 'high', fx: true, predicted_gpa: 2.4, model_version: 'test-1',
    summary: 'Your risk is 62% (high), mainly because your worst course has 37% absence in MAT 101.',
    reasons: [{ feature: 'max_absence_pct', label: 'Highest course absence', value: 37, impact: 31.5, text: 'Your worst course has 37% absence in MAT 101' }],
    helping: [{ feature: 'avg_grade', label: 'Average grade', value: 84, impact: -12.5, text: 'Average grade is 84%' }],
  },
  alerts: [{ severity: 'high', type: 'pending_over_limit', course: 'INF 451', title: "INF 451: 3 'Not submitted' could push you over the limit",
             detail: "Warning: you have 3 'Not submitted' in INF 451. If the professor marks them as absences, you will exceed the limit." }],
  history: [],
  ...over,
})

const simulation = {
  skipped_hours: 0, lectures: 0, practices: 0, hours_per_class: { lecture: 1, practice: 1 },
  before: { risk_percent: 0, predicted_gpa: 3 }, after: { risk_percent: 0, predicted_gpa: 3 },
  gpa_change: 0, risk_change: 0, fx_courses: [], message: 'New predicted GPA: 3.0. Dropout risk: 0%.',
  course_cost: { code: 'INF 451', name: 'Databases', hours: 15, weekly_hours: 1, limit: 4, cost_per_hour_pct: 25 },
  // risk 5 points and 0.1 GPA per skipped hour; the 10th hour is FX
  curve: Array.from({ length: 31 }, (_, h) => ({ hours: h, risk: Math.min(0.9, h * 0.05), predicted_gpa: Math.max(0, 3 - h * 0.1), fx: h >= 10, fx_courses: h >= 10 ? ['INF 451'] : [] })),
}

const makeApi = (data = overview()) => vi.fn(async (path) => {
  if (path === '/api/monitoring/overview') return data
  if (path === '/api/simulate') return simulation
  if (path === '/api/monitoring/curator') return { email: null, name: null }
  throw new Error(`unexpected ${path}`)
})

const connected = { connected: true, demo_mode: false }

describe('MonitoringTab', () => {
  it('shows the safe-to-skip limit line and colours courses by level', async () => {
    render(<MonitoringTab api={makeApi()} token="t" sduStatus={connected} onConnect={() => {}} onSync={async () => {}} />)
    expect(await screen.findByText('Absence limit: 8. You have: 4. Remaining: 4.')).toBeInTheDocument()
    expect(screen.getByText('Absence limit: 9. You have: 11. Remaining: 0.')).toBeInTheDocument()
    expect(screen.getByText('Over the limit (FX)')).toBeInTheDocument()
    const bars = screen.getAllByRole('progressbar')
    expect(bars[0].querySelector('.mon-fill-safe, .mon-fill-success')).not.toBeNull()
    expect(bars[1].querySelector('.mon-fill-danger')).not.toBeNull()
  })

  it('explains the risk in words with the reasons for and against', async () => {
    render(<MonitoringTab api={makeApi()} token="t" sduStatus={connected} onConnect={() => {}} onSync={async () => {}} />)
    expect(await screen.findByText(/Your risk is 62% \(high\)/)).toBeInTheDocument()
    expect(screen.getByText('62%')).toBeInTheDocument()
    expect(screen.getByText('Pushing your risk up (top 1)')).toBeInTheDocument()
    expect(screen.getByText('+31.5 pts')).toBeInTheDocument()
    expect(screen.getByText('What is helping you')).toBeInTheDocument()
    expect(screen.getByText('Average grade is 84%')).toBeInTheDocument()
  })

  it('lists alerts including the Not submitted warning', async () => {
    render(<MonitoringTab api={makeApi()} token="t" sduStatus={connected} onConnect={() => {}} onSync={async () => {}} />)
    expect(await screen.findByText(/If the professor marks them as absences, you will exceed the limit/)).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
  })

  it('syncs when the button is pressed and then reloads the data', async () => {
    const api = makeApi()
    const onSync = vi.fn(async () => {})
    render(<MonitoringTab api={api} token="t" sduStatus={connected} onConnect={() => {}} onSync={onSync} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Sync with SDU' }))
    await waitFor(() => expect(onSync).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(api.mock.calls.filter(c => c[0] === '/api/monitoring/overview').length).toBeGreaterThanOrEqual(2))
  })

  it('loads the curve once per course and answers the sliders locally and instantly', async () => {
    const api = makeApi()
    render(<MonitoringTab api={api} token="tok" sduStatus={connected} onConnect={() => {}} onSync={async () => {}} />)
    const lectures = await screen.findByLabelText(/Lectures to skip/)
    await screen.findByText('New predicted GPA: 2.7. Dropout risk: 15%.')              // 2 lectures + 1 practice = 3 hours
    const calls = () => api.mock.calls.filter(c => c[0] === '/api/simulate')
    expect(calls()).toHaveLength(1)
    expect(JSON.parse(calls()[0][2].body)).toMatchObject({ lectures: 0, practices: 0, max_hours: 30 })
    expect(calls()[0][1]).toBe('tok')

    fireEvent.change(lectures, { target: { value: '5' } })                              // 6 hours: no new request
    expect(await screen.findByText('New predicted GPA: 2.4. Dropout risk: 30%.')).toBeInTheDocument()
    expect(calls()).toHaveLength(1)

    fireEvent.change(lectures, { target: { value: '9' } })                              // 10 hours: FX
    expect(await screen.findByText(/puts INF 451 over the 30% absence limit \(FX\)/)).toBeInTheDocument()
  })

  it('asks again only when the course changes, and explains the cost of one missed hour', async () => {
    const api = makeApi()
    render(<MonitoringTab api={api} token="t" sduStatus={connected} onConnect={() => {}} onSync={async () => {}} />)
    expect(await screen.findByText(/Databases has about 1 class hour a week \(15 in the term\), so one missed hour uses 25% of the 4 absences allowed before FX\./)).toBeInTheDocument()
    fireEvent.change(await screen.findByLabelText('Course'), { target: { value: '' } })
    await waitFor(() => expect(api.mock.calls.filter(c => c[0] === '/api/simulate')).toHaveLength(2))
    expect(await screen.findByText(/^Most sensitive course: Databases has about 1 class hour a week/)).toBeInTheDocument()
  })

  it('invites the student to connect SDU when there is nothing to show', async () => {
    const onConnect = vi.fn()
    const api = makeApi(overview({ has_data: false, risk: null, alerts: [], safe_to_skip: { items: [], level: 'unknown' } }))
    render(<MonitoringTab api={api} token="t" sduStatus={{ connected: false }} onConnect={onConnect} onSync={async () => {}} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Connect SDU' }))
    expect(onConnect).toHaveBeenCalled()
  })

  it('shows a readable error when the server fails', async () => {
    const api = vi.fn(async () => { throw new Error('Server is waking up') })
    render(<MonitoringTab api={api} token="t" sduStatus={connected} onConnect={() => {}} onSync={async () => {}} />)
    expect(await screen.findByText('Server is waking up')).toBeInTheDocument()
  })
})

describe('SyncBar', () => {
  it('says how long ago the last sync was and triggers a sync', () => {
    const onSync = vi.fn()
    render(<SyncBar updatedAt={new Date(Date.now() - 5 * 60000).toISOString()} onSync={onSync} syncing={false} />)
    expect(screen.getByText('Last synced: 5 mins ago')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sync with SDU' }))
    expect(onSync).toHaveBeenCalled()
  })

  it('disables the button while syncing', () => {
    render(<SyncBar updatedAt={null} onSync={() => {}} syncing />)
    expect(screen.getByText('Not synced yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Syncing…' })).toBeDisabled()
  })
})

describe('PredictedGpaWidget', () => {
  it('shows the predicted GPA and opens the Monitoring tab', async () => {
    const onOpen = vi.fn()
    render(<PredictedGpaWidget api={makeApi()} token="t" onOpen={onOpen} />)
    expect(await screen.findByText('2.40')).toBeInTheDocument()
    expect(screen.getByText('62% risk')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Open Monitoring/ }))
    expect(onOpen).toHaveBeenCalled()
  })

  it('renders nothing without a prediction', async () => {
    const api = makeApi(overview({ risk: null }))
    const { container } = render(<PredictedGpaWidget api={api} token="t" onOpen={() => {}} />)
    await waitFor(() => expect(api).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})

describe('DifficultForecast', () => {
  it('renders nothing when there are no subjects', async () => {
    const api = vi.fn(async () => ({ items: [] }))
    const { container } = render(<DifficultForecast api={api} token="t" />)
    await waitFor(() => expect(api).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('explains the chart when forecasts are not available yet', async () => {
    const api = vi.fn(async () => ({ items: [{ course: 'Databases', code: 'INF 451', current_score: 55, predicted_score: null }] }))
    render(<DifficultForecast api={api} token="t" />)
    expect(await screen.findByText('Forecast for difficult subjects')).toBeInTheDocument()
    expect(screen.getByText(/Forecasts appear once 70% of a course is graded/)).toBeInTheDocument()
  })
})
