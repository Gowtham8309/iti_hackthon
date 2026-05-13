import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { parseApiError } from '../api/client'
import KpiCard from '../components/KpiCard'
import MetricCard from '../components/MetricCard'

function safeVal(v, fb = '--') {
  return v === null || v === undefined || v === '' ? fb : v
}

export default function Dashboard() {
  const { user, token, logout, authHeaders } = useAuth()
  const { t } = useI18n()
  const navigate = useNavigate()

  const [dashDate, setDashDate] = useState('')
  const [summary, setSummary] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [seedStatus, setSeedStatus] = useState({ msg: '', type: '' })
  const [seedResult, setSeedResult] = useState(null)
  const [seedLoading, setSeedLoading] = useState(false)
  const [notifForm, setNotifForm] = useState({ channel: 'both', email: '', mobile: '', message: 'Test notification from ITI Attendance AI system.' })
  const [notifStatus, setNotifStatus] = useState({ msg: '', type: '' })
  const [notifResult, setNotifResult] = useState(null)
  const [notifLoading, setNotifLoading] = useState(false)

  async function loadDashboard() {
    setStatus({ msg: 'Loading…', type: '' })
    try {
      const params = new URLSearchParams()
      if (dashDate) params.set('date', dashDate)
      const resp = await fetch(`/api/v1/dashboard/summary?${params}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail, 'Failed'), type: 'error' }); return }
      setSummary(data)
      setStatus({ msg: `Updated ${new Date().toLocaleTimeString()}`, type: 'success' })
    } catch {
      setStatus({ msg: 'Network error. Check backend.', type: 'error' })
    }
  }

  async function loadAnalytics() {
    try {
      const resp = await fetch('/api/v1/dashboard/analytics', { headers: authHeaders() })
      if (!resp.ok) return
      const data = await resp.json()
      setAnalytics(data.days || [])
    } catch {}
  }

  async function testNotification() {
    setNotifLoading(true)
    setNotifStatus({ msg: 'Sending…', type: '' })
    setNotifResult(null)
    try {
      const resp = await fetch('/api/v1/ops/notify/test', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(notifForm),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setNotifStatus({ msg: parseApiError(data.detail, 'Test failed.'), type: 'error' })
      } else {
        const emailOk = data.email?.sent
        const smsOk = data.sms?.sent
        const msg = [
          data.email ? `Email: ${emailOk ? 'Sent ✓' : 'Failed ✗'}` : null,
          data.sms   ? `SMS: ${smsOk   ? 'Sent ✓' : 'Failed ✗'}` : null,
        ].filter(Boolean).join('  |  ')
        setNotifStatus({ msg, type: (emailOk || smsOk) ? 'success' : 'error' })
        setNotifResult(data)
      }
    } catch {
      setNotifStatus({ msg: 'Network error.', type: 'error' })
    } finally {
      setNotifLoading(false)
    }
  }

  async function runSeedDemo() {
    if (!window.confirm('This will CLEAR all transactional data and insert fresh demo records. Continue?')) return
    setSeedLoading(true)
    setSeedStatus({ msg: 'Seeding demo data…', type: '' })
    setSeedResult(null)
    try {
      const resp = await fetch('/api/v1/ops/seed-demo', { method: 'POST', headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) {
        setSeedStatus({ msg: parseApiError(data.detail, 'Seed failed.'), type: 'error' })
      } else {
        setSeedStatus({ msg: `Done! ${data.created?.attendance_events ?? ''} events created.`, type: 'success' })
        setSeedResult(data)
        loadDashboard()
        loadAnalytics()
      }
    } catch {
      setSeedStatus({ msg: 'Network error.', type: 'error' })
    } finally {
      setSeedLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
    loadAnalytics()
  }, [])

  const s = summary || {}
  const fs = s.faculty_summary || {}
  const cq = s.classroom_quality || {}
  const dov = s.district_overview || {}

  const maxPresent = analytics ? Math.max(...analytics.map(d => d.present || 0), 1) : 1

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#75e8c0' }}>GeoFace Verify</div>
        <h1>{t('hero_title', 'index')}</h1>
        <p>{t('hero_text', 'index')}</p>
      </header>

      <main>
        {/* Command Center */}
        <section className="card">
          <div className="between">
            <div>
              <div className="pill">{user?.full_name || user?.username} | {user?.role}</div>
              <h2 className="section-title">{t('command_center', 'index')}</h2>
              <p className="section-sub" id="summaryDate">
                {s.summary_date ? `Summary date: ${s.summary_date}` : 'Summary date: --'}
              </p>
            </div>
            <div className="button-row">
              <button className="secondary" onClick={loadDashboard}>↻ {t('refresh')}</button>
              <button className="danger" onClick={() => { logout(); navigate('/login', { replace: true }) }}>
                {t('logout')}
              </button>
            </div>
          </div>

          <div className="filter-box">
            <div className="row">
              <div className="col col-small">
                <label>Dashboard Date</label>
                <input type="date" value={dashDate} onChange={e => setDashDate(e.target.value)} />
              </div>
              <div className="col">
                <button className="secondary" onClick={loadDashboard}>Apply Date</button>
                <button className="secondary" onClick={() => { setDashDate(''); loadDashboard() }}>Clear Date</button>
              </div>
            </div>
            {status.msg && (
              <div className={`status ${status.type === 'error' ? 'errorText' : status.type === 'success' ? 'successText' : ''}`}>
                {status.msg}
              </div>
            )}
          </div>
        </section>

        {/* Main KPI grid */}
        <section className="card">
          <div className="hero-grid" style={{ marginTop: 8 }}>
            <div className="hero-panel" style={{ padding: 24, color: 'white' }}>
              <h2 className="hero-title" style={{ color: 'white' }}>Today's Workforce Trust Snapshot</h2>
              <p className="hero-text">
                Combines attendance, face verification, geo-fence validation, and anomaly status into one operational view.
              </p>
              <div className="hero-metrics" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))', gap: 12, marginTop: 20 }}>
                {[
                  { label: 'Total Events', value: safeVal(s.total_events) },
                  { label: 'Present Today', value: safeVal(s.present_today) },
                  { label: 'Under Review', value: safeVal(s.under_review) },
                  { label: 'Anomalies', value: safeVal(s.anomaly_count) },
                  { label: 'Face Verified', value: safeVal(s.face_verified) },
                  { label: 'Outside Fence', value: safeVal(s.outside_geofence) },
                ].map(m => (
                  <div className="hero-mini" key={m.label}>
                    <div className="hero-mini-label">{m.label}</div>
                    <div className="hero-mini-value">{m.value}</div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div className="card" style={{ margin: 0, padding: 20 }}>
                <h3 className="section-title">{t('readiness_title', 'index')}</h3>
                <div className="readiness-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
                  {[
                    { label: 'Face Enrollment', value: `${safeVal(s.face_enrollment_pct, 0)}%`, sub: 'Students with enrolled face profile' },
                    { label: 'Geo Coverage', value: `${safeVal(s.geo_coverage_pct, 0)}%`, sub: 'Industries with GPS coordinates' },
                    { label: 'Roster Coverage', value: `${safeVal(s.roster_coverage_pct, 0)}%`, sub: 'Students assigned to a roster' },
                    { label: 'Anomaly Rate', value: `${safeVal(s.anomaly_rate, 0)}%`, sub: 'Events flagged for review' },
                  ].map(r => (
                    <div className="readiness-card" key={r.label}>
                      <div className="readiness-label">{r.label}</div>
                      <div className="readiness-value">{r.value}</div>
                      <div className="readiness-sub">{r.sub}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Quick Actions */}
        <section className="card">
          <h2 className="section-title">{t('quick_actions', 'index')}</h2>
          <p className="section-sub">Navigate to key modules based on your operational needs.</p>
          <div className="button-row">
            <button onClick={() => navigate('/checkin')}>📷 Attendance Console</button>
            <button className="secondary" onClick={() => navigate('/attendance-events')}>📋 Audit Trail</button>
            <button className="secondary" onClick={() => navigate('/anomalies')}>⚠️ Anomalies</button>
            <button className="secondary" onClick={() => navigate('/classroom')}>🎓 Classroom Monitor</button>
          </div>
        </section>

        {/* Admin: Notification Test */}
        {user?.role === 'admin' && (
          <section className="card" style={{ borderLeft: '4px solid #0ea5e9' }}>
            <h2 className="section-title" style={{ color: '#0ea5e9' }}>Admin — Test Notifications</h2>
            <p className="section-sub">
              Send a test SMS and/or Email to verify your Fast2SMS and SMTP credentials in <code>.env</code>.
            </p>
            <div className="row" style={{ marginTop: 12 }}>
              <div className="col col-small">
                <label>Channel</label>
                <select value={notifForm.channel} onChange={e => setNotifForm(f => ({ ...f, channel: e.target.value }))}>
                  <option value="both">Both (SMS + Email)</option>
                  <option value="email">Email only</option>
                  <option value="sms">SMS only</option>
                </select>
              </div>
              <div className="col">
                <label>Email address</label>
                <input value={notifForm.email} onChange={e => setNotifForm(f => ({ ...f, email: e.target.value }))} placeholder="recipient@gmail.com (or leave blank for .env default)" />
              </div>
              <div className="col">
                <label>Mobile number</label>
                <input value={notifForm.mobile} onChange={e => setNotifForm(f => ({ ...f, mobile: e.target.value }))} placeholder="9876543210 (or leave blank for .env default)" />
              </div>
              <div className="col">
                <label>Message</label>
                <input value={notifForm.message} onChange={e => setNotifForm(f => ({ ...f, message: e.target.value }))} />
              </div>
            </div>
            <div className="button-row" style={{ marginTop: 12 }}>
              <button style={{ background: '#0ea5e9', borderColor: '#0ea5e9' }} onClick={testNotification} disabled={notifLoading}>
                {notifLoading ? 'Sending…' : 'Send Test Notification'}
              </button>
            </div>
            {notifStatus.msg && (
              <div className={`status ${notifStatus.type === 'error' ? 'errorText' : notifStatus.type === 'success' ? 'successText' : ''}`}>
                {notifStatus.msg}
              </div>
            )}
            {notifResult && (
              <div style={{ marginTop: 12, fontSize: 13 }}>
                <div style={{ marginBottom: 6 }}><strong>Config:</strong> Email enabled: {String(notifResult.config?.email_enabled)} | SMS enabled: {String(notifResult.config?.sms_enabled)} | SMTP: {notifResult.config?.smtp_host || 'not set'} | Fast2SMS key: {notifResult.config?.fast2sms_key_set ? 'set ✓' : 'not set ✗'}</div>
                {notifResult.email && <div style={{ color: notifResult.email.sent ? '#16a34a' : '#dc2626' }}>Email: {notifResult.email.sent ? `Sent to ${notifResult.email.recipients?.join(', ')}` : `Error — ${notifResult.email.error}`}</div>}
                {notifResult.sms && <div style={{ color: notifResult.sms.sent ? '#16a34a' : '#dc2626', marginTop: 4 }}>SMS: {notifResult.sms.sent ? `Sent to ${notifResult.sms.mobile}` : `Error — ${notifResult.sms.error}`}</div>}
              </div>
            )}
          </section>
        )}

        {/* Admin: Seed Demo Data */}
        {user?.role === 'admin' && (
          <section className="card" style={{ borderLeft: '4px solid #7c3aed' }}>
            <h2 className="section-title" style={{ color: '#7c3aed' }}>Admin — Seed Demo Data</h2>
            <p className="section-sub">
              Inserts a full set of deterministic demo records (5 students, 3 industries, 70 attendance events,
              anomaly flags, classroom observations). <strong>Clears existing transactional data first.</strong>
            </p>
            <div className="button-row" style={{ marginTop: 12 }}>
              <button
                style={{ background: '#7c3aed', borderColor: '#7c3aed' }}
                onClick={runSeedDemo}
                disabled={seedLoading}
              >
                {seedLoading ? 'Seeding…' : 'Seed Demo Data'}
              </button>
            </div>
            {seedStatus.msg && (
              <div className={`status ${seedStatus.type === 'error' ? 'errorText' : seedStatus.type === 'success' ? 'successText' : ''}`}>
                {seedStatus.msg}
              </div>
            )}
            {seedResult && (
              <div style={{ marginTop: 16 }}>
                <div className="section-title" style={{ marginBottom: 8 }}>Login Credentials</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f1f5f9' }}>
                      <th style={{ padding: '6px 10px', textAlign: 'left' }}>Role</th>
                      <th style={{ padding: '6px 10px', textAlign: 'left' }}>Username</th>
                      <th style={{ padding: '6px 10px', textAlign: 'left' }}>Password</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(seedResult.login_credentials || {}).map(([role, creds]) => (
                      <tr key={role} style={{ borderBottom: '1px solid #e2e8f0' }}>
                        <td style={{ padding: '5px 10px', fontWeight: 600 }}>{role}</td>
                        <td style={{ padding: '5px 10px', fontFamily: 'monospace' }}>{creds.username}</td>
                        <td style={{ padding: '5px 10px', fontFamily: 'monospace' }}>{creds.password}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ marginTop: 12, fontSize: 13, color: '#475569' }}>
                  <strong>Demo GPS (inside geofence):</strong> lat {seedResult.demo_gps?.inside_geofence?.lat}, lon {seedResult.demo_gps?.inside_geofence?.lon}
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  <strong>Outside:</strong> lat {seedResult.demo_gps?.outside_geofence?.lat}, lon {seedResult.demo_gps?.outside_geofence?.lon}
                </div>
              </div>
            )}
          </section>
        )}

        {/* Faculty Monitor */}
        <section className="card">
          <h2 className="section-title">Faculty Monitoring</h2>
          <p className="section-sub">Live faculty attendance and engagement status from today's sessions.</p>
          <div className="summary-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 16, marginTop: 16 }}>
            <MetricCard color="blue" label="Total Faculty" value={safeVal(fs.total_faculty)} sub="Registered faculty profiles" />
            <MetricCard color="green" label="Checked In" value={safeVal(fs.checked_in_today)} sub="Faculty checked in today" />
            <MetricCard color="green" label="Present" value={safeVal(fs.present_count)} sub="Verified present sessions" />
            <MetricCard color="orange" label="Late" value={safeVal(fs.late_count)} sub="Arrived after scheduled time" />
            <MetricCard color="orange" label="Under Review" value={safeVal(fs.under_review)} sub="Sessions needing supervisor review" />
            <MetricCard color="red" label="Recurrent Issues" value={safeVal(fs.recurrent_issues)} sub="Faculty with repeated anomalies" />
          </div>
        </section>

        {/* Classroom Quality */}
        <section className="card">
          <h2 className="section-title">Classroom Quality</h2>
          <p className="section-sub">Observer-submitted quality scores from today's classroom monitoring.</p>
          <div className="summary-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 16, marginTop: 16 }}>
            <MetricCard color="blue" label="Sessions Observed" value={safeVal(cq.sessions_observed)} sub="Total classroom observations" />
            <MetricCard color="red" label="Need Attention" value={safeVal(cq.need_attention)} sub="Sessions with anomaly signals" />
            <MetricCard color="orange" label="Avg Discipline" value={safeVal(cq.avg_discipline)} sub="Mean discipline score" />
            <MetricCard color="green" label="Avg Teaching" value={safeVal(cq.avg_teaching_quality)} sub="Mean teaching quality score" />
            <MetricCard color="purple" label="Avg Engagement" value={safeVal(cq.avg_engagement)} sub="Mean student engagement" />
          </div>
        </section>

        {/* District Overview */}
        <section className="card">
          <h2 className="section-title">District Overview</h2>
          <p className="section-sub">Cross-district aggregates for coordinator and district officer visibility.</p>
          <div className="summary-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 16, marginTop: 16 }}>
            <MetricCard color="blue" label="Active Districts" value={safeVal(dov.active_districts)} sub="Districts with recorded activity" />
            <MetricCard color="orange" label="Pending Reviews" value={safeVal(dov.pending_reviews)} sub="Anomalies awaiting review" />
            <MetricCard color="red" label="Open Anomalies" value={safeVal(dov.open_anomalies)} sub="Unresolved anomaly cases" />
            <MetricCard color="red" label="Classroom Alerts" value={safeVal(dov.classroom_alerts)} sub="Critical classroom quality signals" />
          </div>
        </section>

        {/* Analytics Trend */}
        {analytics && analytics.length > 0 && (
          <section className="card">
            <h2 className="section-title">{t('live_analytics', 'index')}</h2>
            <p className="section-sub">Daily present vs. review events for the last 14 days.</p>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 120, marginTop: 16 }}>
              {analytics.slice(-14).map((d, i) => {
                const pPct = Math.round(((d.present || 0) / maxPresent) * 100)
                const rPct = Math.round(((d.under_review || 0) / maxPresent) * 100)
                return (
                  <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: 96, gap: 2 }}>
                      <div style={{ height: `${rPct}%`, background: '#f59e0b', borderRadius: '3px 3px 0 0', minHeight: rPct > 0 ? 4 : 0 }} title={`Review: ${d.under_review || 0}`} />
                      <div style={{ height: `${pPct}%`, background: '#22c55e', borderRadius: '3px 3px 0 0', minHeight: pPct > 0 ? 4 : 0 }} title={`Present: ${d.present || 0}`} />
                    </div>
                    <span style={{ fontSize: 9, color: '#64748b', whiteSpace: 'nowrap' }}>
                      {d.date ? d.date.slice(5) : ''}
                    </span>
                  </div>
                )
              })}
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
              <span style={{ fontSize: 11, color: '#22c55e' }}>■ Present</span>
              <span style={{ fontSize: 11, color: '#f59e0b' }}>■ Review</span>
            </div>
          </section>
        )}
      </main>
    </>
  )
}
