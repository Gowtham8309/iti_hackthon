import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { API_BASE, parseApiError } from '../api/client'
import KpiCard from '../components/KpiCard'
import ScoreBar from '../components/ScoreBar'

const TIER_COLORS = {
  excellent: '#059669', satisfactory: '#2563eb',
  needs_improvement: '#d97706', critical: '#dc2626',
}

export default function Classroom() {
  const { user, authHeaders } = useAuth()
  const { t } = useI18n()

  const [form, setForm] = useState({
    faculty_id: '', industry_id: '', session_status: 'on_track',
    discipline_score: 75, teaching_quality_score: 75, student_engagement_score: 75,
    notes: '', observed_at: '',
  })
  const [filterFacultyId, setFilterFacultyId] = useState('')
  const [filterLimit, setFilterLimit] = useState('50')
  const [observations, setObservations] = useState([])
  const [createStatus, setCreateStatus] = useState({ msg: '', type: '' })
  const [listStatus, setListStatus] = useState({ msg: '', type: '' })

  useEffect(() => { loadObservations() }, [])

  async function loadObservations() {
    setListStatus({ msg: 'Loading…', type: '' })
    const params = new URLSearchParams()
    if (filterFacultyId) params.set('faculty_id', filterFacultyId)
    if (filterLimit) params.set('limit', filterLimit)
    try {
      const resp = await fetch(`/api/v1/classroom-observations?${params}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setListStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setObservations(Array.isArray(data) ? data : (data.items || []))
      setListStatus({ msg: '', type: '' })
    } catch {
      setListStatus({ msg: 'Load failed. Check backend server.', type: 'error' })
    }
  }

  async function createObservation() {
    const facultyId = Number(form.faculty_id)
    if (!facultyId || facultyId <= 0) { setCreateStatus({ msg: 'Faculty ID is required.', type: 'error' }); return }
    setCreateStatus({ msg: 'Submitting observation…', type: '' })
    const payload = {
      faculty_id: facultyId,
      industry_id: Number(form.industry_id) || null,
      session_status: form.session_status,
      discipline_score: Number(form.discipline_score),
      teaching_quality_score: Number(form.teaching_quality_score),
      student_engagement_score: Number(form.student_engagement_score),
      notes: form.notes.trim() || null,
      observed_at: form.observed_at ? new Date(form.observed_at).toISOString() : null,
    }
    try {
      const resp = await fetch(API_BASE + '/api/v1/classroom-observations', {
        method: 'POST', headers: authHeaders(), body: JSON.stringify(payload),
      })
      const data = await resp.json()
      if (!resp.ok) { setCreateStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setCreateStatus({
        msg: `Observation #${data.id} recorded. Composite: ${Number(data.anomaly_signals?.composite_score || 0).toFixed(1)} — ${data.anomaly_signals?.performance_tier || '--'}.`,
        type: 'success',
      })
      setForm({ faculty_id: '', industry_id: '', session_status: 'on_track', discipline_score: 75, teaching_quality_score: 75, student_engagement_score: 75, notes: '', observed_at: '' })
      await loadObservations()
    } catch {
      setCreateStatus({ msg: 'Request failed. Check backend server.', type: 'error' })
    }
  }

  async function recomputeOne(id) {
    setListStatus({ msg: `Recomputing signals for #${id}…`, type: '' })
    try {
      const resp = await fetch(`/api/v1/classroom-observations/${id}/recompute`, { method: 'POST', headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setListStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setListStatus({ msg: `Observation #${id} signals updated.`, type: 'success' })
      await loadObservations()
    } catch {
      setListStatus({ msg: 'Recompute failed.', type: 'error' })
    }
  }

  async function bulkRecompute() {
    const role = user?.role
    if (role !== 'admin' && role !== 'supervisor') {
      setListStatus({ msg: 'Bulk recompute requires admin or supervisor role.', type: 'error' }); return
    }
    setListStatus({ msg: 'Running bulk recompute…', type: '' })
    try {
      const resp = await fetch(API_BASE + '/api/v1/classroom-observations/recompute-all', { method: 'POST', headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setListStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setListStatus({ msg: `Done. ${data.updated ?? 0} of ${data.total_observations ?? 0} updated.`, type: 'success' })
      await loadObservations()
    } catch {
      setListStatus({ msg: 'Bulk recompute failed.', type: 'error' })
    }
  }

  const today = new Date().toISOString().slice(0, 10)
  const todayObs = observations.filter(ob => (ob.observed_at || '').slice(0, 10) === today)
  const needsAttention = observations.filter(ob => ob.anomaly_signals?.needs_attention === true).length
  const avg = key => { const vals = observations.map(ob => Number(ob[key])).filter(n => !isNaN(n)); return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : '--' }
  const avgComposite = () => { const vals = observations.map(ob => Number(ob.anomaly_signals?.composite_score)).filter(n => !isNaN(n)); return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : '--' }

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#34d399' }}>GeoFace Verify</div>
        <h1>{t('header_title', 'classroom')}</h1>
        <p>{t('header_subtitle', 'classroom')}</p>
      </header>

      <main>
        {/* KPI Snapshot */}
        <section className="card">
          <h2 className="section-title">{t('snapshot_title', 'classroom')}</h2>
          <div className="kpi-grid">
            <KpiCard color="blue" label={t('kpi_observed', 'classroom')} value={todayObs.length} sub="Classroom sessions recorded today" />
            <KpiCard color="red" label={t('kpi_attention', 'classroom')} value={needsAttention} sub="Sessions with anomaly signals" />
            <KpiCard color="orange" label={t('kpi_discipline', 'classroom')} value={avg('discipline_score')} sub="Mean discipline score" />
            <KpiCard color="green" label={t('kpi_teaching', 'classroom')} value={avg('teaching_quality_score')} sub="Mean teaching quality score" />
            <KpiCard color="purple" label={t('kpi_engagement', 'classroom')} value={avg('student_engagement_score')} sub="Mean student engagement score" />
            <KpiCard label={t('kpi_composite', 'classroom')} value={avgComposite()} sub="Teaching 40% + Discipline 35% + Engagement 25%" />
          </div>
        </section>

        {/* Create Observation */}
        <section className="card">
          <h2 className="section-title">{t('form_title', 'classroom')}</h2>
          <p className="section-sub">Submit an observation for any faculty session. Threshold: &lt;60 on any dimension flags the session.</p>

          <div className="form-shell">
            <div className="row">
              <div className="col">
                <label>Faculty ID</label>
                <input type="number" value={form.faculty_id} onChange={e => setForm(f => ({ ...f, faculty_id: e.target.value }))} placeholder="Faculty profile ID" />
              </div>
              <div className="col">
                <label>Industry / Location ID (optional)</label>
                <input type="number" value={form.industry_id} onChange={e => setForm(f => ({ ...f, industry_id: e.target.value }))} placeholder="Industry ID (optional)" />
              </div>
              <div className="col">
                <label>Session Status</label>
                <select value={form.session_status} onChange={e => setForm(f => ({ ...f, session_status: e.target.value }))}>
                  <option value="on_track">On Track</option>
                  <option value="late_start">Late Start</option>
                  <option value="low_engagement">Low Engagement</option>
                  <option value="needs_review">Needs Review</option>
                  <option value="absent_faculty">Absent Faculty</option>
                </select>
              </div>
              <div className="col">
                <label>Observed At (optional)</label>
                <input type="datetime-local" value={form.observed_at} onChange={e => setForm(f => ({ ...f, observed_at: e.target.value }))} />
              </div>
            </div>

            <br />

            <div className="row">
              {[
                { key: 'discipline_score', label: 'Discipline Score (0–100)', desc: 'Punctuality, classroom order, rule compliance' },
                { key: 'teaching_quality_score', label: 'Teaching Quality Score (0–100)', desc: 'Lesson clarity, content depth, practical demos' },
                { key: 'student_engagement_score', label: 'Student Engagement Score (0–100)', desc: 'Participation, Q&A activity, hands-on involvement' },
              ].map(s => (
                <div className="col" key={s.key}>
                  <label>{s.label}</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <input type="range" min={0} max={100} value={form[s.key]}
                      onChange={e => setForm(f => ({ ...f, [s.key]: e.target.value }))}
                      style={{ flex: 1, accentColor: '#2563eb' }}
                    />
                    <span style={{
                      minWidth: 44, textAlign: 'center', fontSize: 14, fontWeight: 800,
                      background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '4px 8px', color: '#1d4ed8',
                    }}>
                      {form[s.key]}
                    </span>
                  </div>
                  <p className="section-sub" style={{ marginTop: 4 }}>{s.desc}</p>
                </div>
              ))}
            </div>

            <br />

            <div className="row">
              <div className="col">
                <label>Observer Notes (optional)</label>
                <textarea
                  rows={3} value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="Describe what was observed. Example: Faculty started 15 minutes late, used only chalk-and-talk…"
                  style={{ width: '100%', border: '1px solid #e2e8f0', borderRadius: 10, padding: 10, fontSize: 13, resize: 'vertical' }}
                />
              </div>
            </div>

            <br />

            <div className="button-row">
              <button className="success" onClick={createObservation}>{t('btn_submit', 'classroom')}</button>
              <button className="secondary" onClick={() => setForm({ faculty_id: '', industry_id: '', session_status: 'on_track', discipline_score: 75, teaching_quality_score: 75, student_engagement_score: 75, notes: '', observed_at: '' })}>
                {t('btn_reset', 'classroom')}
              </button>
            </div>

            {createStatus.msg && (
              <div className={`status ${createStatus.type === 'error' ? 'errorText' : 'successText'}`}>{createStatus.msg}</div>
            )}
          </div>
        </section>

        {/* Observation History */}
        <section className="card">
          <h2 className="section-title">{t('history_title', 'classroom')}</h2>
          <div className="row">
            <div className="col">
              <label>Faculty ID Filter</label>
              <input type="number" value={filterFacultyId} onChange={e => setFilterFacultyId(e.target.value)} placeholder="Optional" />
            </div>
            <div className="col">
              <label>Limit</label>
              <input type="number" value={filterLimit} onChange={e => setFilterLimit(e.target.value)} min="1" max="200" />
            </div>
            <div className="col" style={{ alignSelf: 'flex-end' }}>
              <button onClick={loadObservations}>{t('btn_load', 'classroom')}</button>
              <button className="secondary" onClick={bulkRecompute}>Bulk Recompute Signals</button>
            </div>
          </div>

          {listStatus.msg && (
            <div className={`status ${listStatus.type === 'error' ? 'errorText' : listStatus.type === 'success' ? 'successText' : ''}`}>{listStatus.msg}</div>
          )}

          <br />
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>ID / Time</th><th>Faculty</th><th>Session Status</th>
                  <th>Scores</th><th>Composite / Tier</th><th>Anomaly Signals</th><th>Action</th>
                </tr>
              </thead>
              <tbody>
                {observations.length === 0 ? (
                  <tr><td colSpan={7}>No observations loaded yet.</td></tr>
                ) : observations.map(ob => {
                  const signals = ob.anomaly_signals || {}
                  const tier = signals.performance_tier || '--'
                  const composite = signals.composite_score !== undefined ? Number(signals.composite_score).toFixed(1) : '--'
                  const tierColor = TIER_COLORS[tier] || '#64748b'
                  const items = signals.items || []
                  const s = ob.session_status || 'on_track'
                  const sCls = s === 'on_track' ? 'badge-green' : s === 'absent_faculty' ? 'badge-red' : 'badge-orange'
                  return (
                    <tr key={ob.id}>
                      <td>
                        <strong>#{ob.id}</strong>
                        <div className="small">{ob.observed_at?.slice(0, 16) || '--'}</div>
                        <div className="small">Observer: {ob.observer_user_id || '--'}</div>
                      </td>
                      <td>
                        <strong>Faculty {ob.faculty_id}</strong>
                        <div className="small">Industry: {ob.industry_id || '--'}</div>
                      </td>
                      <td><span className={`badge ${sCls}`}>{s.replace(/_/g, ' ')}</span></td>
                      <td>
                        <ScoreBar label="Discipline" score={ob.discipline_score} />
                        <ScoreBar label="Teaching" score={ob.teaching_quality_score} />
                        <ScoreBar label="Engagement" score={ob.student_engagement_score} />
                      </td>
                      <td>
                        <strong style={{ fontSize: 18, fontWeight: 800 }}>{composite}</strong>
                        <div style={{ fontSize: 12, fontWeight: 700, color: tierColor }}>{tier.replace(/_/g, ' ')}</div>
                      </td>
                      <td>
                        {items.length === 0
                          ? <span style={{ fontSize: 12, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '4px 10px', color: '#16a34a' }}>Clean</span>
                          : items.map((s, i) => (
                            <div key={i} style={{ fontSize: 12, background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '4px 10px', color: '#dc2626', margin: '2px 0' }}>{s}</div>
                          ))
                        }
                      </td>
                      <td>
                        <button className="secondary" onClick={() => recomputeOne(ob.id)}>Recompute</button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  )
}
