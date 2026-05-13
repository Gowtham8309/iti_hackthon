import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { parseApiError } from '../api/client'
import KpiCard from '../components/KpiCard'

const STATUS_COLORS = {
  present: 'badge-green', late: 'badge-orange', outside_geofence: 'badge-red',
  face_mismatch: 'badge-red', under_review: 'badge-orange', absent: 'badge-red',
}

export default function AttendanceEvents() {
  const { token, authHeaders } = useAuth()
  const { t } = useI18n()

  const [filters, setFilters] = useState({ student_id: '', status: '', date: '', today_only: false, limit: '100' })
  const [events, setEvents] = useState([])
  const [status, setStatus] = useState({ msg: '', type: '' })

  async function loadEvents() {
    setStatus({ msg: 'Loading events…', type: '' })
    const params = new URLSearchParams()
    if (filters.student_id) params.set('student_id', filters.student_id)
    if (filters.status) params.set('status', filters.status)
    if (filters.date) params.set('date', filters.date)
    if (filters.today_only) params.set('today_only', 'true')
    if (filters.limit) params.set('limit', filters.limit)
    try {
      const resp = await fetch(`/api/v1/attendance/events?${params}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      const items = Array.isArray(data) ? data : (data.items || [])
      setEvents(items)
      setStatus({ msg: `${items.length} events loaded.`, type: 'success' })
    } catch {
      setStatus({ msg: 'Network error.', type: 'error' })
    }
  }

  async function exportExcel() {
    const params = new URLSearchParams()
    if (filters.student_id) params.set('student_id', filters.student_id)
    if (filters.status) params.set('status', filters.status)
    if (filters.date) params.set('date', filters.date)
    if (filters.today_only) params.set('today_only', 'true')
    try {
      const resp = await fetch(`/api/v1/attendance/export?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!resp.ok) { setStatus({ msg: 'Export failed.', type: 'error' }); return }
      const blob = await resp.blob()
      const cd = resp.headers.get('Content-Disposition') || ''
      const match = cd.match(/filename[^;=\n]*=(['"]?)(.+?)\1/)
      const filename = match ? match[2] : 'attendance.xlsx'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
    } catch {
      setStatus({ msg: 'Export error.', type: 'error' })
    }
  }

  const kpiPresent = events.filter(e => e.status === 'present').length
  const kpiReview = events.filter(e => ['under_review', 'face_mismatch', 'outside_geofence'].includes(e.status)).length
  const kpiSelfies = events.filter(e => e.selfie_url).length

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#38bdf8' }}>GeoFace Verify</div>
        <h1>{t('header_title', 'attendance_events')}</h1>
        <p>{t('header_subtitle', 'attendance_events')}</p>
      </header>

      <main>
        <section className="card">
          <h2 className="section-title">{t('snapshot_title', 'attendance_events')}</h2>
          <div className="kpi-grid">
            <KpiCard color="blue" label={t('kpi_events_loaded', 'attendance_events')} value={events.length} sub="Records currently visible" />
            <KpiCard color="green" label={t('kpi_present', 'attendance_events')} value={kpiPresent} sub="Trusted or accepted entries" />
            <KpiCard color="orange" label={t('kpi_review', 'attendance_events')} value={kpiReview} sub="Needs review or mismatch" />
            <KpiCard color="purple" label={t('kpi_selfies', 'attendance_events')} value={kpiSelfies} sub="Events with captured evidence" />
          </div>
        </section>

        <section className="card">
          <h2 className="section-title">Filters</h2>
          <div className="filter-box">
            <div className="row">
              <div className="col">
                <label>Student ID</label>
                <input type="number" value={filters.student_id} onChange={e => setFilters(f => ({ ...f, student_id: e.target.value }))} placeholder="Optional" />
              </div>
              <div className="col">
                <label>Status</label>
                <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}>
                  <option value="">All</option>
                  <option value="present">Present</option>
                  <option value="late">Late</option>
                  <option value="under_review">Under Review</option>
                  <option value="outside_geofence">Outside Geofence</option>
                  <option value="face_mismatch">Face Mismatch</option>
                </select>
              </div>
              <div className="col">
                <label>Date</label>
                <input type="date" value={filters.date} onChange={e => setFilters(f => ({ ...f, date: e.target.value }))} />
              </div>
              <div className="col">
                <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input type="checkbox" checked={filters.today_only} onChange={e => setFilters(f => ({ ...f, today_only: e.target.checked }))} />
                  Today Only
                </label>
              </div>
              <div className="col">
                <label>Limit</label>
                <input type="number" value={filters.limit} onChange={e => setFilters(f => ({ ...f, limit: e.target.value }))} min="1" max="1000" />
              </div>
              <div className="col" style={{ alignSelf: 'flex-end' }}>
                <button onClick={loadEvents}>{t('btn_load', 'attendance_events')}</button>
                <button className="secondary" onClick={() => { setFilters({ student_id: '', status: '', date: '', today_only: false, limit: '100' }); setEvents([]) }}>
                  {t('btn_reset', 'attendance_events')}
                </button>
                <button className="secondary" onClick={exportExcel}>⬇ Export Excel</button>
              </div>
            </div>
            {status.msg && (
              <div className={`status ${status.type === 'error' ? 'errorText' : status.type === 'success' ? 'successText' : ''}`}>{status.msg}</div>
            )}
          </div>
        </section>

        <section className="card">
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>ID / Time</th>
                  <th>Student</th>
                  <th>Status</th>
                  <th>Face Score</th>
                  <th>Distance</th>
                  <th>Industry</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr><td colSpan={7}>No events loaded. Apply filters and click Load.</td></tr>
                ) : events.map(ev => (
                  <tr key={ev.id}>
                    <td>
                      <strong>#{ev.id}</strong>
                      <div className="small">{ev.checked_in_at?.slice(0, 16) || '--'}</div>
                    </td>
                    <td>
                      <strong>ID {ev.student_id}</strong>
                      <div className="small">{ev.student_name || ''}</div>
                    </td>
                    <td>
                      <span className={`badge ${STATUS_COLORS[ev.status] || 'badge-blue'}`}>
                        {ev.status?.replace(/_/g, ' ') || '--'}
                      </span>
                    </td>
                    <td>
                      {ev.face_similarity != null
                        ? <strong>{(ev.face_similarity * 100).toFixed(1)}%</strong>
                        : '--'
                      }
                    </td>
                    <td>{ev.distance_meters != null ? `${ev.distance_meters.toFixed(0)}m` : '--'}</td>
                    <td><div className="small">{ev.industry_id ? `#${ev.industry_id}` : '--'}</div></td>
                    <td>
                      {ev.selfie_url
                        ? <a href={ev.selfie_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>View Selfie</a>
                        : <span style={{ fontSize: 12, color: '#94a3b8' }}>No selfie</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  )
}
