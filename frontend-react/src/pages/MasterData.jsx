import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { parseApiError } from '../api/client'

function safeVal(v, fb = '--') { return v === null || v === undefined || v === '' ? fb : v }

const TABS = ['students', 'industries', 'rosters', 'pilotImport', 'dayStates', 'evaluation', 'payroll']

export default function MasterData() {
  const { token, authHeaders } = useAuth()
  const { t } = useI18n()
  const [activeTab, setActiveTab] = useState('students')

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#38bdf8' }}>GeoFace Verify</div>
        <h1>{t('page_title', 'master_data')}</h1>
        <p>{t('page_subtitle', 'master_data')}</p>
      </header>

      <main>
        <section className="card">
          <div className="tab-bar">
            {TABS.map(tab => (
              <button
                key={tab}
                className={`tab-button${activeTab === tab ? ' active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {t(`${tab === 'pilotImport' ? 'pilot_import_tab' : tab === 'dayStates' ? 'day_states_tab' : tab + '_tab'}`, 'master_data')}
              </button>
            ))}
          </div>
        </section>

        {activeTab === 'students' && <StudentsTab authHeaders={authHeaders} token={token} />}
        {activeTab === 'industries' && <IndustriesTab authHeaders={authHeaders} token={token} />}
        {activeTab === 'rosters' && <RostersTab authHeaders={authHeaders} token={token} />}
        {activeTab === 'pilotImport' && <PilotImportTab authHeaders={authHeaders} token={token} />}
        {activeTab === 'dayStates' && <DayStatesTab authHeaders={authHeaders} token={token} />}
        {activeTab === 'evaluation' && <EvaluationTab authHeaders={authHeaders} token={token} />}
        {activeTab === 'payroll' && <PayrollTab authHeaders={authHeaders} token={token} t={t} />}
      </main>
    </>
  )
}

function StudentsTab({ authHeaders, token }) {
  const [students, setStudents] = useState([])
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [form, setForm] = useState({ student_code: '', full_name: '', iti_name: '', trade: '', batch: '', mobile: '', email: '', industry_id: '' })

  async function loadStudents() {
    setStatus({ msg: 'Loading…', type: '' })
    try {
      const resp = await fetch('/api/v1/students?limit=100', { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStudents(Array.isArray(data) ? data : (data.items || []))
      setStatus({ msg: '', type: '' })
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  async function createStudent() {
    try {
      const resp = await fetch('/api/v1/students', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ ...form, batch: form.batch || null, industry_id: Number(form.industry_id) || null }) })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Student #${data.id} created.`, type: 'success' })
      setForm({ student_code: '', full_name: '', iti_name: '', trade: '', batch: '', mobile: '', email: '', industry_id: '' })
      loadStudents()
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  useEffect(() => { loadStudents() }, [])

  return (
    <section className="card">
      <h2 className="section-title">Student Profiles</h2>
      <p className="section-sub">Create and manage student profiles used for attendance check-ins.</p>

      <div className="form-shell">
        <div className="row">
          {[
            { key: 'student_code', label: 'Student Code', placeholder: 'STU-GNT-2026-001' },
            { key: 'full_name', label: 'Full Name', placeholder: 'Full name' },
            { key: 'iti_name', label: 'ITI Name', placeholder: 'Govt ITI Visakhapatnam' },
            { key: 'trade', label: 'Trade', placeholder: 'Electrician' },
            { key: 'batch', label: 'Batch', placeholder: '2026' },
            { key: 'mobile', label: 'Mobile', placeholder: '9876543210' },
            { key: 'email', label: 'Email', placeholder: 'student@example.com' },
            { key: 'industry_id', label: 'Industry ID', placeholder: 'Assigned industry' },
          ].map(f => (
            <div className="col" key={f.key}>
              <label>{f.label}</label>
              <input value={form[f.key]} onChange={e => setForm(s => ({ ...s, [f.key]: e.target.value }))} placeholder={f.placeholder} />
            </div>
          ))}
        </div>
        <div className="button-row" style={{ marginTop: 16 }}>
          <button className="success" onClick={createStudent}>Create Student</button>
          <button className="secondary" onClick={loadStudents}>↻ Refresh List</button>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      <br />
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead><tr><th>ID</th><th>Code</th><th>Name</th><th>Trade</th><th>Batch</th><th>Face</th><th>Industry</th></tr></thead>
          <tbody>
            {students.length === 0 ? <tr><td colSpan={7}>No students loaded.</td></tr>
              : students.map(s => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td><strong>{s.student_code || '--'}</strong></td>
                  <td>{s.full_name || '--'}</td>
                  <td>{s.trade || '--'}</td>
                  <td>{s.batch || '--'}</td>
                  <td><span className={`badge ${s.face_enrolled ? 'badge-green' : 'badge-orange'}`}>{s.face_enrolled ? 'Enrolled' : 'Pending'}</span></td>
                  <td>{s.industry_id || '--'}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function IndustriesTab({ authHeaders, token }) {
  const [industries, setIndustries] = useState([])
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [form, setForm] = useState({ name: '', address: '', district: '', state: 'Andhra Pradesh', latitude: '', longitude: '', geofence_radius_m: '200' })

  async function loadIndustries() {
    try {
      const resp = await fetch('/api/v1/industries?limit=100', { headers: authHeaders() })
      const data = await resp.json()
      if (resp.ok) setIndustries(Array.isArray(data) ? data : (data.items || []))
    } catch {}
  }

  async function createIndustry() {
    const payload = { ...form, latitude: parseFloat(form.latitude) || null, longitude: parseFloat(form.longitude) || null, geofence_radius_m: parseInt(form.geofence_radius_m) || 200 }
    try {
      const resp = await fetch('/api/v1/industries', { method: 'POST', headers: authHeaders(), body: JSON.stringify(payload) })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Industry #${data.id} created.`, type: 'success' })
      setForm({ name: '', address: '', district: '', state: 'Andhra Pradesh', latitude: '', longitude: '', geofence_radius_m: '200' })
      loadIndustries()
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  async function geocodeMissing() {
    setStatus({ msg: 'Geocoding missing coordinates…', type: '' })
    try {
      const resp = await fetch('/api/v1/ops/industries/geocode-missing', { method: 'POST', headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Geocoded: ${data.updated ?? 0} industries updated.`, type: 'success' })
      loadIndustries()
    } catch { setStatus({ msg: 'Geocode failed.', type: 'error' }) }
  }

  useEffect(() => { loadIndustries() }, [])

  return (
    <section className="card">
      <h2 className="section-title">Industry Partners</h2>
      <p className="section-sub">Manage training locations used for GPS geo-fence validation.</p>

      <div className="form-shell">
        <div className="row">
          {[
            { key: 'name', label: 'Industry Name', placeholder: 'XYZ Manufacturing Pvt Ltd' },
            { key: 'address', label: 'Address', placeholder: 'Full address' },
            { key: 'district', label: 'District', placeholder: 'Guntur' },
            { key: 'state', label: 'State', placeholder: 'Andhra Pradesh' },
            { key: 'latitude', label: 'Latitude', placeholder: '16.3067' },
            { key: 'longitude', label: 'Longitude', placeholder: '80.4365' },
            { key: 'geofence_radius_m', label: 'Geofence Radius (m)', placeholder: '200' },
          ].map(f => (
            <div className="col" key={f.key}>
              <label>{f.label}</label>
              <input value={form[f.key]} onChange={e => setForm(s => ({ ...s, [f.key]: e.target.value }))} placeholder={f.placeholder} />
            </div>
          ))}
        </div>
        <div className="button-row" style={{ marginTop: 16 }}>
          <button className="success" onClick={createIndustry}>Add Industry</button>
          <button className="secondary" onClick={loadIndustries}>↻ Refresh</button>
          <button className="secondary" onClick={geocodeMissing}>🌍 Geocode Missing Coordinates</button>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      <br />
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>District</th><th>Latitude</th><th>Longitude</th><th>Radius (m)</th></tr></thead>
          <tbody>
            {industries.length === 0 ? <tr><td colSpan={6}>No industries loaded.</td></tr>
              : industries.map(i => (
                <tr key={i.id}>
                  <td>{i.id}</td>
                  <td><strong>{i.name}</strong><div className="small">{i.address || '--'}</div></td>
                  <td>{i.district || '--'}</td>
                  <td>{i.latitude != null ? Number(i.latitude).toFixed(4) : <span style={{ color: '#dc2626' }}>Missing</span>}</td>
                  <td>{i.longitude != null ? Number(i.longitude).toFixed(4) : <span style={{ color: '#dc2626' }}>Missing</span>}</td>
                  <td>{i.geofence_radius_m || 200}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function RostersTab({ authHeaders }) {
  const [rosters, setRosters] = useState([])
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [form, setForm] = useState({ student_id: '', industry_id: '', start_date: '', end_date: '', shift_start_time: '09:00', shift_end_time: '17:00' })

  async function loadRosters() {
    try {
      const resp = await fetch('/api/v1/rosters?limit=100', { headers: authHeaders() })
      const data = await resp.json()
      if (resp.ok) setRosters(Array.isArray(data) ? data : (data.items || []))
    } catch {}
  }

  async function createRoster() {
    const payload = { ...form, student_id: Number(form.student_id), industry_id: Number(form.industry_id) }
    try {
      const resp = await fetch('/api/v1/rosters', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Roster #${data.id} created.`, type: 'success' })
      loadRosters()
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  async function assignRosters() {
    setStatus({ msg: 'Auto-assigning rosters…', type: '' })
    try {
      const resp = await fetch('/api/v1/ops/pilot-data/assign-rosters', { method: 'POST', headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Auto-assigned: ${data.assigned ?? 0} rosters created.`, type: 'success' })
      loadRosters()
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  useEffect(() => { loadRosters() }, [])

  return (
    <section className="card">
      <h2 className="section-title">Training Rosters</h2>
      <p className="section-sub">Assign students to industries with schedule start/end times for attendance timing validation.</p>

      <div className="form-shell">
        <div className="row">
          {[
            { key: 'student_id', label: 'Student ID', placeholder: '1' },
            { key: 'industry_id', label: 'Industry ID', placeholder: '1' },
            { key: 'start_date', label: 'Start Date', type: 'date' },
            { key: 'end_date', label: 'End Date', type: 'date' },
            { key: 'shift_start_time', label: 'Start Time', placeholder: '09:00' },
            { key: 'shift_end_time', label: 'End Time', placeholder: '17:00' },
          ].map(f => (
            <div className="col" key={f.key}>
              <label>{f.label}</label>
              <input type={f.type || 'text'} value={form[f.key]} onChange={e => setForm(s => ({ ...s, [f.key]: e.target.value }))} placeholder={f.placeholder || ''} />
            </div>
          ))}
        </div>
        <div className="button-row" style={{ marginTop: 16 }}>
          <button className="success" onClick={createRoster}>Create Roster</button>
          <button className="secondary" onClick={loadRosters}>↻ Refresh</button>
          <button className="secondary" onClick={assignRosters}>⚡ Auto-Assign Rosters</button>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      <br />
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead><tr><th>ID</th><th>Student</th><th>Industry</th><th>Period</th><th>Schedule</th></tr></thead>
          <tbody>
            {rosters.length === 0 ? <tr><td colSpan={6}>No rosters loaded.</td></tr>
              : rosters.map(r => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.student_id}</td>
                  <td>{r.industry_id}</td>
                  <td><div className="small">{r.start_date || '--'} → {r.end_date || '--'}</div></td>
                  <td><div className="small">{r.shift_start_time || '--'} – {r.shift_end_time || '--'}</div></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function PilotImportTab({ authHeaders }) {
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)

  async function previewImport() {
    if (!file) { setStatus({ msg: 'Select a CSV file first.', type: 'error' }); return }
    setStatus({ msg: 'Previewing…', type: '' })
    const fd = new FormData(); fd.append('file', file)
    try {
      const resp = await fetch('/api/v1/ops/pilot-data/preview', { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('iti_attendance_token')}` }, body: fd })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setPreview(data)
      setStatus({ msg: 'Preview ready.', type: 'success' })
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  async function executeImport() {
    if (!file) { setStatus({ msg: 'Select a CSV file first.', type: 'error' }); return }
    setStatus({ msg: 'Importing…', type: '' })
    const fd = new FormData(); fd.append('file', file)
    try {
      const resp = await fetch('/api/v1/ops/pilot-data/import', { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('iti_attendance_token')}` }, body: fd })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Import done. ${data.students_created ?? 0} students, ${data.industries_created ?? 0} industries, ${data.rosters_created ?? 0} rosters created.`, type: 'success' })
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  return (
    <section className="card">
      <h2 className="section-title">Pilot Data Import</h2>
      <p className="section-sub">Upload a CSV file to bulk-import students, industries, and rosters for pilot deployments.</p>

      <div className="form-shell">
        <div className="col" style={{ maxWidth: 400 }}>
          <label>CSV File</label>
          <input type="file" accept=".csv" onChange={e => setFile(e.target.files[0])} />
        </div>
        <div className="button-row" style={{ marginTop: 16 }}>
          <button className="secondary" onClick={previewImport}>Preview Import</button>
          <button className="success" onClick={executeImport}>Execute Import</button>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      {preview && (
        <div style={{ marginTop: 16, padding: 16, background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0' }}>
          <strong>Preview:</strong>
          <div className="small" style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>{JSON.stringify(preview, null, 2)}</div>
        </div>
      )}
    </section>
  )
}

function DayStatesTab({ authHeaders }) {
  const [dayStates, setDayStates] = useState([])
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [form, setForm] = useState({ date: '', state_type: 'working', notes: '' })

  async function loadDayStates() {
    try {
      const resp = await fetch('/api/v1/day-states?limit=30', { headers: authHeaders() })
      const data = await resp.json()
      if (resp.ok) setDayStates(Array.isArray(data) ? data : (data.items || []))
    } catch {}
  }

  async function createDayState() {
    try {
      const resp = await fetch('/api/v1/day-states', { method: 'POST', headers: authHeaders(), body: JSON.stringify(form) })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Day state for ${form.date} set to "${form.state_type}".`, type: 'success' })
      loadDayStates()
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  useEffect(() => { loadDayStates() }, [])

  return (
    <section className="card">
      <h2 className="section-title">Daily Attendance State Monitor</h2>
      <p className="section-sub">Mark days as holidays, working days, or half-days to control attendance validation logic.</p>

      <div className="form-shell">
        <div className="row">
          <div className="col">
            <label>Date</label>
            <input type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} />
          </div>
          <div className="col">
            <label>State Type</label>
            <select value={form.state_type} onChange={e => setForm(f => ({ ...f, state_type: e.target.value }))}>
              <option value="working">Working Day</option>
              <option value="holiday">Holiday</option>
              <option value="half_day">Half Day</option>
              <option value="shutdown">Shutdown</option>
            </select>
          </div>
          <div className="col">
            <label>Notes (optional)</label>
            <input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="e.g., Independence Day" />
          </div>
          <div className="col" style={{ alignSelf: 'flex-end' }}>
            <button className="success" onClick={createDayState}>Set Day State</button>
            <button className="secondary" onClick={loadDayStates}>↻ Refresh</button>
          </div>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      <br />
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead><tr><th>Date</th><th>State Type</th><th>Notes</th><th>Created</th></tr></thead>
          <tbody>
            {dayStates.length === 0 ? <tr><td colSpan={4}>No day states configured.</td></tr>
              : dayStates.map(d => (
                <tr key={d.id}>
                  <td><strong>{d.date}</strong></td>
                  <td>
                    <span className={`badge ${d.state_type === 'working' ? 'badge-green' : d.state_type === 'holiday' ? 'badge-orange' : 'badge-blue'}`}>
                      {d.state_type}
                    </span>
                  </td>
                  <td>{d.notes || '--'}</td>
                  <td className="small">{d.created_at?.slice(0, 10) || '--'}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function EvaluationTab({ authHeaders }) {
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [results, setResults] = useState(null)
  const [studentId, setStudentId] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  async function runEvaluation() {
    setStatus({ msg: 'Running evaluation…', type: '' })
    const params = new URLSearchParams()
    if (studentId) params.set('student_id', studentId)
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    try {
      const resp = await fetch(`/api/v1/ops/evaluation?${params}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setResults(data)
      setStatus({ msg: 'Evaluation complete.', type: 'success' })
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  return (
    <section className="card">
      <h2 className="section-title">Evaluation Framework</h2>
      <p className="section-sub">Run attendance-based performance evaluations for trainees over a date range.</p>

      <div className="form-shell">
        <div className="row">
          <div className="col">
            <label>Student ID (optional)</label>
            <input type="number" value={studentId} onChange={e => setStudentId(e.target.value)} placeholder="Leave blank for all" />
          </div>
          <div className="col">
            <label>Start Date</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className="col">
            <label>End Date</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <div className="col" style={{ alignSelf: 'flex-end' }}>
            <button className="success" onClick={runEvaluation}>Run Evaluation</button>
          </div>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      {results && (
        <div style={{ marginTop: 16, overflowX: 'auto' }}>
          <table>
            <thead>
              <tr><th>Student ID</th><th>Name</th><th>Total Days</th><th>Present Days</th><th>Attendance %</th><th>Grade</th></tr>
            </thead>
            <tbody>
              {(Array.isArray(results) ? results : (results.records || [])).map((r, i) => (
                <tr key={i}>
                  <td>{r.student_id}</td>
                  <td>{r.full_name || '--'}</td>
                  <td>{r.total_days ?? '--'}</td>
                  <td>{r.present_days ?? '--'}</td>
                  <td><strong>{r.attendance_pct != null ? `${Number(r.attendance_pct).toFixed(1)}%` : '--'}</strong></td>
                  <td>
                    <span className={`badge ${r.grade === 'A' || r.grade === 'B' ? 'badge-green' : r.grade === 'C' ? 'badge-orange' : 'badge-red'}`}>
                      {r.grade || '--'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function PayrollTab({ authHeaders, t }) {
  const today = new Date().toISOString().slice(0, 10)
  const firstOfMonth = today.slice(0, 7) + '-01'

  const [startDate, setStartDate] = useState(firstOfMonth)
  const [endDate, setEndDate] = useState(today)
  const [payroll, setPayroll] = useState(null)
  const [status, setStatus] = useState({ msg: '', type: '' })

  async function loadPayroll() {
    if (!startDate || !endDate) { setStatus({ msg: 'Select both start and end dates.', type: 'error' }); return }
    setStatus({ msg: 'Loading payroll summary…', type: '' })
    try {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
      const resp = await fetch(`/api/v1/ops/payroll/summary?${params}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setPayroll(data)
      setStatus({ msg: `Loaded ${data.total_students ?? 0} trainees.`, type: 'success' })
    } catch { setStatus({ msg: 'Network error.', type: 'error' }) }
  }

  const records = payroll?.records || []

  return (
    <section className="card">
      <h2 className="section-title">{t('payroll_title', 'master_data')}</h2>
      <p className="section-sub">{t('payroll_subtitle', 'master_data')}</p>

      <div className="form-shell">
        <div className="row">
          <div className="col">
            <label>Period Start</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className="col">
            <label>Period End</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <div className="col" style={{ alignSelf: 'flex-end' }}>
            <button onClick={loadPayroll}>Load Payroll Summary</button>
          </div>
        </div>
        {status.msg && <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>}
      </div>

      {payroll && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 16, margin: '16px 0' }}>
            {[
              { label: 'Period', value: `${payroll.period_start?.slice(0, 10) || '--'} → ${payroll.period_end?.slice(0, 10) || '--'}` },
              { label: 'Total Trainees', value: safeVal(payroll.total_students) },
              { label: 'Avg Attendance', value: payroll.summary?.avg_attendance_pct != null ? `${Number(payroll.summary.avg_attendance_pct).toFixed(1)}%` : '--' },
              { label: 'Fully Eligible', value: safeVal(payroll.summary?.fully_present_count) },
              { label: 'Needs Review', value: safeVal(payroll.summary?.needs_review_count) },
            ].map(m => (
              <div key={m.label} className="metric-card">
                <div className="metric-label">{m.label}</div>
                <div className="metric-value" style={{ fontSize: 20 }}>{m.value}</div>
              </div>
            ))}
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr><th>Student ID</th><th>Name</th><th>Total Days</th><th>Present Days</th><th>Late Days</th><th>Attendance %</th><th>Eligibility</th></tr>
              </thead>
              <tbody>
                {records.length === 0 ? <tr><td colSpan={7}>No payroll records found for this period.</td></tr>
                  : records.map(r => {
                    const pct = Number(r.attendance_pct || 0)
                    const eligible = pct >= 75 ? { label: 'Eligible', cls: 'badge-green' }
                      : pct >= 50 ? { label: 'Partial', cls: 'badge-orange' }
                      : { label: 'Ineligible', cls: 'badge-red' }
                    return (
                      <tr key={r.student_id}>
                        <td>{r.student_id}</td>
                        <td>{r.full_name || '--'}</td>
                        <td>{r.total_working_days ?? '--'}</td>
                        <td>{r.present_days ?? '--'}</td>
                        <td>{r.late_days ?? '--'}</td>
                        <td><strong>{pct.toFixed(1)}%</strong></td>
                        <td><span className={`badge ${eligible.cls}`}>{eligible.label}</span></td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
