import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { parseApiError } from '../api/client'

export default function CheckIn() {
  const { user, token, logout, authHeaders } = useAuth()
  const { t } = useI18n()
  const navigate = useNavigate()

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)

  const [cameraOn, setCameraOn] = useState(false)
  const [capturedBlob, setCapturedBlob] = useState(null)
  const [capturedUrl, setCapturedUrl] = useState(null)
  const [actionMode, setActionMode] = useState('check_in')
  const [demoLat, setDemoLat] = useState('')
  const [demoLon, setDemoLon] = useState('')
  const [useDemo, setUseDemo] = useState(false)
  const [checkResult, setCheckResult] = useState(null)
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [profile, setProfile] = useState(null)
  const [facing, setFacing] = useState('user')

  const isStudent = user?.role === 'student'

  useEffect(() => {
    if (isStudent) loadStudentProfile()
    return () => stopCamera()
  }, [])

  async function loadStudentProfile() {
    try {
      const resp = await fetch('/api/v1/auth/my-student-profile', { headers: authHeaders() })
      if (resp.ok) {
        const data = await resp.json()
        setProfile(data.student || data.profile || data)
        }
    } catch {}
  }

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: facing, width: { ideal: 640 }, height: { ideal: 480 } },
      })
      streamRef.current = stream
      if (videoRef.current) videoRef.current.srcObject = stream
      setCameraOn(true)
      setCapturedBlob(null)
      setCapturedUrl(null)
    } catch (err) {
      setStatus({ msg: `Camera error: ${err.message}`, type: 'error' })
    }
  }

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    setCameraOn(false)
  }

  function captureFrame() {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    canvas.width = video.videoWidth || 640
    canvas.height = video.videoHeight || 480
    canvas.getContext('2d').drawImage(video, 0, 0)
    canvas.toBlob(blob => {
      setCapturedBlob(blob)
      setCapturedUrl(URL.createObjectURL(blob))
      stopCamera()
    }, 'image/jpeg', 0.92)
  }

  function retake() {
    if (capturedUrl) URL.revokeObjectURL(capturedUrl)
    setCapturedBlob(null)
    setCapturedUrl(null)
    setCheckResult(null)
    startCamera()
  }

  async function getLocation() {
    if (useDemo && demoLat && demoLon) {
      return { latitude: parseFloat(demoLat), longitude: parseFloat(demoLon) }
    }
    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        p => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
        err => reject(new Error(`GPS error: ${err.message}`)),
        { timeout: 10000 }
      )
    })
  }

  async function submitCheckin() {
    if (!capturedBlob) { setStatus({ msg: 'Capture a photo first.', type: 'error' }); return }

    setStatus({ msg: 'Getting location…', type: '' })
    let coords
    try { coords = await getLocation() }
    catch (err) { setStatus({ msg: err.message, type: 'error' }); return }

    setStatus({ msg: 'Verifying attendance…', type: '' })

    // Convert blob to base64
    const selfie_image_base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsDataURL(capturedBlob)
    })

    const endpoint = actionMode === 'check_out' ? '/api/v1/attendance/check-out' : '/api/v1/attendance/check-in'

    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_id: 0,  // auto-filled server-side from token for students/faculty
          latitude: coords.latitude,
          longitude: coords.longitude,
          selfie_image_base64,
          selfie_captured: true,
        }),
      })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail, 'Check-in failed.'), type: 'error' }); return }
      // Flatten nested response into a shape the decision card can read
      const ev = data.attendance_event || {}
      const dec = data.decision || {}
      const checks = data.checks || {}
      const faceCheck = checks.face || {}
      const geoCheck = checks.geo || {}
      const faceScore = ev.face_match_score ?? faceCheck.face_match_score
      const threshold = faceCheck.accept_threshold ?? 0.75
      setCheckResult({
        id: ev.id,
        status: dec.status || ev.status,
        message: dec.reason || ev.decision_reason,
        face_score: faceScore,
        face_match: faceScore != null && faceScore >= threshold,
        face_liveness_passed: faceCheck.status !== 'liveness_low',
        geofence_valid: geoCheck.is_inside_geofence ?? geoCheck.geofence_valid ?? geoCheck.is_valid_location,
        distance_m: ev.distance_from_industry_meters ?? geoCheck.distance_from_industry_meters ?? geoCheck.distance_meters,
        anomaly_triggered: (data.anomalies_created || []).length > 0,
        reasons: dec.reason ? [dec.reason] : [],
      })
      setStatus({ msg: '', type: '' })
    } catch {
      setStatus({ msg: 'Network error. Check backend server.', type: 'error' })
    }
  }

  const decisionColor = checkResult
    ? checkResult.status === 'present' ? '#059669'
      : checkResult.status === 'late' ? '#d97706'
      : '#dc2626'
    : '#1d4ed8'

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#75e8c0' }}>GeoFace Verify</div>
        <h1>{t('page_title', 'checkin')}</h1>
        <p>{t('page_subtitle', 'checkin')}</p>
      </header>

      <main>
        {/* Profile Card (student only) */}
        {isStudent && profile && (
          <section className="card">
            <h2 className="section-title">Student Profile</h2>
            <div className="camera-grid">
              {profile.photo_url && (
                <div className="camera-box">
                  <label>Profile Photo</label>
                  <img src={profile.photo_url} alt="Student profile" style={{ width: '100%', height: 260, objectFit: 'cover', borderRadius: 14, background: '#0f172a' }} />
                </div>
              )}
              <div className="camera-box">
                <label>Profile Summary</label>
                <div className="explain-grid">
                  {[
                    { label: 'Student', value: profile.full_name, sub: profile.student_code },
                    { label: 'ITI / Trade', value: profile.trade, sub: profile.iti_name },
                    { label: 'Batch', value: profile.batch, sub: 'Active student batch' },
                    { label: 'Face Enrollment', value: profile.face_enrolled ? 'Enrolled ✓' : 'Not Enrolled', sub: 'Reference profile for attendance matching' },
                  ].map(c => (
                    <div className="explain-card" key={c.label}>
                      <div className="explain-label">{c.label}</div>
                      <div className="explain-value">{c.value || '--'}</div>
                      <div className="explain-sub">{c.sub || ''}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Check-In Details */}
        <section className="card">
          <h2 className="section-title">{t('details_title', 'checkin')}</h2>
          <p className="section-sub">These values are sent to the backend along with selfie evidence.</p>
          <div className="row">
            <div className="col">
              <label>Action Mode</label>
              <select value={actionMode} onChange={e => setActionMode(e.target.value)}>
                <option value="check_in">Check In</option>
                <option value="check_out">Check Out</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={useDemo} onChange={e => {
                setUseDemo(e.target.checked)
                if (e.target.checked) { setDemoLat('16.3067'); setDemoLon('80.4365') }
              }} />
              Use Demo GPS Coordinates (pre-fills Guntur geofence)
            </label>
            {useDemo && (
              <div className="row" style={{ marginTop: 8 }}>
                <div className="col">
                  <label>Demo Latitude</label>
                  <input value={demoLat} onChange={e => setDemoLat(e.target.value)} placeholder="17.3850" />
                </div>
                <div className="col">
                  <label>Demo Longitude</label>
                  <input value={demoLon} onChange={e => setDemoLon(e.target.value)} placeholder="78.4867" />
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Camera */}
        <section className="card">
          <h2 className="section-title">{t('camera_title', 'checkin')}</h2>
          <p className="section-sub">
            {cameraOn ? 'Camera live — position your face and click Capture.' : capturedUrl ? 'Photo captured.' : 'Click Start Camera to begin.'}
          </p>
          <div className="camera-grid">
            <div className="camera-box">
              <label>{capturedUrl ? 'Captured Photo' : 'Camera Feed'}</label>
              {capturedUrl
                ? <img src={capturedUrl} alt="Captured selfie" style={{ width: '100%', height: 260, objectFit: 'cover', borderRadius: 14, border: '1px solid #e2e8f0' }} />
                : <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%', height: 260, objectFit: 'cover', borderRadius: 14, background: '#0f172a', border: '1px solid #e2e8f0', display: cameraOn ? 'block' : 'block' }} />
              }
              <canvas ref={canvasRef} style={{ display: 'none' }} />
            </div>
          </div>
          <div className="button-row" style={{ marginTop: 16 }}>
            {!cameraOn && !capturedBlob && (
              <button onClick={startCamera}>📷 Start Camera</button>
            )}
            {cameraOn && (
              <>
                <button className="success" onClick={captureFrame}>📸 Capture</button>
                <button className="secondary" onClick={stopCamera}>Stop Camera</button>
                <button className="secondary" onClick={() => { setFacing(f => f === 'user' ? 'environment' : 'user'); stopCamera(); setTimeout(startCamera, 200) }}>
                  🔄 Flip Camera
                </button>
              </>
            )}
            {capturedBlob && (
              <>
                <button className="success" onClick={submitCheckin}>✔ Submit Attendance</button>
                <button className="secondary" onClick={retake}>↺ Retake</button>
              </>
            )}
          </div>
          {status.msg && (
            <div className={`status ${status.type === 'error' ? 'errorText' : ''}`}>{status.msg}</div>
          )}
        </section>

        {/* Decision */}
        {checkResult && (
          <section className="card">
            <h2 className="section-title">{t('decision_title', 'checkin')}</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
              <div style={{
                width: 80, height: 80, borderRadius: '50%',
                background: decisionColor,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 28, color: 'white', fontWeight: 800,
              }}>
                {checkResult.status === 'present' ? '✓' : checkResult.status === 'late' ? '⏱' : '✗'}
              </div>
              <div>
                <div style={{ fontSize: 24, fontWeight: 800, color: decisionColor, textTransform: 'capitalize' }}>
                  {checkResult.status?.replace(/_/g, ' ')}
                </div>
                <div style={{ fontSize: 13, color: '#64748b' }}>{checkResult.message || ''}</div>
              </div>
            </div>

            <div className="explain-grid">
              {[
                { label: 'Face Score', value: checkResult.face_score != null ? `${(checkResult.face_score * 100).toFixed(1)}%` : 'N/A', sub: 'Cosine similarity vs enrolled face' },
                { label: 'Face Match', value: checkResult.face_match ? 'MATCHED ✓' : 'FAILED ✗', sub: 'Similarity above threshold' },
                { label: 'Liveness', value: checkResult.face_liveness_passed === false ? 'FAILED ✗' : checkResult.face_liveness_passed ? 'PASSED ✓' : 'N/A', sub: 'Anti-spoofing texture check' },
                { label: 'Geofence', value: checkResult.geofence_valid ? 'INSIDE ✓' : 'OUTSIDE ✗', sub: 'GPS location check' },
                { label: 'Distance', value: checkResult.distance_m != null ? `${checkResult.distance_m.toFixed(0)}m` : 'N/A', sub: 'Distance from industry location' },
                { label: 'Anomaly', value: checkResult.anomaly_triggered ? 'YES ⚠' : 'NO ✓', sub: 'Anomaly detection result' },
                { label: 'Event ID', value: checkResult.id || checkResult.event_id || 'N/A', sub: 'Attendance record ID' },
              ].map(c => (
                <div className="explain-card" key={c.label}>
                  <div className="explain-label">{c.label}</div>
                  <div className="explain-value">{c.value}</div>
                  <div className="explain-sub">{c.sub}</div>
                </div>
              ))}
            </div>

            {checkResult.reasons?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <strong style={{ fontSize: 13 }}>Trust Reasoning:</strong>
                <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                  {checkResult.reasons.map((r, i) => (
                    <li key={i} style={{ fontSize: 13, color: '#475569', marginBottom: 4 }}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </main>
    </>
  )
}
