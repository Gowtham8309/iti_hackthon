import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { parseApiError } from '../api/client'
import KpiCard from '../components/KpiCard'

const SEVERITY_COLORS = {
  critical: 'badge-red', high: 'badge-red', medium: 'badge-orange',
  low: 'badge-green', info: 'badge-blue',
}

export default function Anomalies() {
  const { token, authHeaders } = useAuth()
  const { t } = useI18n()

  const [filters, setFilters] = useState({ student_id: '', severity: '', review_status: '', limit: '50' })
  const [anomalies, setAnomalies] = useState([])
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [reviewNote, setReviewNote] = useState({})
  const [reviewStatus, setReviewStatus] = useState({})

  async function loadAnomalies() {
    setStatus({ msg: 'Loading anomalies…', type: '' })
    const params = new URLSearchParams()
    if (filters.student_id) params.set('student_id', filters.student_id)
    if (filters.severity) params.set('severity', filters.severity)
    if (filters.review_status) params.set('review_status', filters.review_status)
    if (filters.limit) params.set('limit', filters.limit)
    try {
      const resp = await fetch(`/api/v1/anomalies?${params}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setAnomalies(Array.isArray(data) ? data : (data.items || []))
      setStatus({ msg: `${anomalies.length} anomalies loaded.`, type: 'success' })
    } catch {
      setStatus({ msg: 'Network error.', type: 'error' })
    }
  }

  async function submitReview(id, action) {
    const note = reviewNote[id] || ''
    try {
      const resp = await fetch(`/api/v1/anomalies/${id}/review`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ action, supervisor_notes: note }),
      })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setReviewStatus(rs => ({ ...rs, [id]: `${action} applied.` }))
      setStatus({ msg: `Anomaly #${id} reviewed: ${action}.`, type: 'success' })
    } catch {
      setStatus({ msg: 'Review request failed.', type: 'error' })
    }
  }

  async function exportExcel() {
    const params = new URLSearchParams()
    if (filters.student_id) params.set('student_id', filters.student_id)
    if (filters.severity) params.set('severity', filters.severity)
    if (filters.review_status) params.set('review_status', filters.review_status)
    try {
      const resp = await fetch(`/api/v1/anomalies/export?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!resp.ok) { setStatus({ msg: 'Export failed.', type: 'error' }); return }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'anomalies.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setStatus({ msg: 'Export error.', type: 'error' })
    }
  }

  const kpiTotal = anomalies.length
  const kpiPending = anomalies.filter(a => a.review_status === 'pending').length
  const kpiHigh = anomalies.filter(a => ['critical', 'high'].includes(a.severity)).length
  const kpiReviewed = anomalies.filter(a => a.review_status !== 'pending').length

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#fbbf24' }}>GeoFace Verify</div>
        <h1>{t('header_title', 'anomalies')}</h1>
        <p>{t('header_subtitle', 'anomalies')}</p>
      </header>

      <main>
        <section className="card">
          <h2 className="section-title">{t('snapshot_title', 'anomalies')}</h2>
          <div className="kpi-grid">
            <KpiCard color="blue" label={t('kpi_total_loaded', 'anomalies')} value={kpiTotal} sub="Anomalies currently loaded" />
            <KpiCard color="orange" label={t('kpi_pending', 'anomalies')} value={kpiPending} sub="Waiting for supervisor action" />
            <KpiCard color="red" label={t('kpi_high_risk', 'anomalies')} value={kpiHigh} sub="High-priority investigation cases" />
            <KpiCard color="green" label={t('kpi_reviewed', 'anomalies')} value={kpiReviewed} sub="Approved, rejected, or escalated" />
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
                <label>Severity</label>
                <select value={filters.severity} onChange={e => setFilters(f => ({ ...f, severity: e.target.value }))}>
                  <option value="">All</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              <div className="col">
                <label>Review Status</label>
                <select value={filters.review_status} onChange={e => setFilters(f => ({ ...f, review_status: e.target.value }))}>
                  <option value="">All</option>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="escalated">Escalated</option>
                </select>
              </div>
              <div className="col">
                <label>Limit</label>
                <input type="number" value={filters.limit} onChange={e => setFilters(f => ({ ...f, limit: e.target.value }))} min="1" max="500" />
              </div>
              <div className="col" style={{ alignSelf: 'flex-end' }}>
                <button onClick={loadAnomalies}>{t('btn_load', 'anomalies')}</button>
                <button className="secondary" onClick={() => { setFilters({ student_id: '', severity: '', review_status: '', limit: '50' }); setAnomalies([]) }}>
                  {t('btn_reset', 'anomalies')}
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
          <h2 className="section-title">{t('queue_title', 'anomalies')}</h2>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>ID / Time</th>
                  <th>Student</th>
                  <th>Severity</th>
                  <th>Type</th>
                  <th>Risk Score</th>
                  <th>Status</th>
                  <th>Review Action</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.length === 0 ? (
                  <tr><td colSpan={7}>No anomalies loaded. Apply filters and click Load.</td></tr>
                ) : anomalies.map(a => (
                  <tr key={a.id}>
                    <td>
                      <strong>#{a.id}</strong>
                      <div className="small">{a.created_at?.slice(0, 16) || '--'}</div>
                    </td>
                    <td>
                      <strong>Student {a.student_id}</strong>
                      <div className="small">{a.event_id ? `Event #${a.event_id}` : ''}</div>
                    </td>
                    <td>
                      <span className={`badge ${SEVERITY_COLORS[a.severity] || 'badge-blue'}`}>
                        {a.severity || '--'}
                      </span>
                    </td>
                    <td>
                      <div className="small">{a.anomaly_type?.replace(/_/g, ' ') || '--'}</div>
                    </td>
                    <td>
                      <strong>{a.risk_score != null ? Number(a.risk_score).toFixed(2) : '--'}</strong>
                    </td>
                    <td>
                      <span className={`badge ${a.review_status === 'pending' ? 'badge-orange' : a.review_status === 'approved' ? 'badge-green' : a.review_status === 'rejected' ? 'badge-red' : 'badge-blue'}`}>
                        {a.review_status || 'pending'}
                      </span>
                      {reviewStatus[a.id] && <div className="small" style={{ color: '#059669' }}>{reviewStatus[a.id]}</div>}
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <textarea
                          rows={2}
                          placeholder="Supervisor notes…"
                          style={{ fontSize: 12, padding: '6px 8px', borderRadius: 8, border: '1px solid #e2e8f0', width: '100%', resize: 'vertical' }}
                          value={reviewNote[a.id] || ''}
                          onChange={e => setReviewNote(rn => ({ ...rn, [a.id]: e.target.value }))}
                        />
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button className="success" style={{ padding: '6px 10px', fontSize: 11 }} onClick={() => submitReview(a.id, 'approve')}>Approve</button>
                          <button className="danger" style={{ padding: '6px 10px', fontSize: 11 }} onClick={() => submitReview(a.id, 'reject')}>Reject</button>
                          <button className="secondary" style={{ padding: '6px 10px', fontSize: 11 }} onClick={() => submitReview(a.id, 'escalate')}>Escalate</button>
                        </div>
                      </div>
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
