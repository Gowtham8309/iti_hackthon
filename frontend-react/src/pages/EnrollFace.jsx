import { useState, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { parseApiError } from '../api/client'

export default function EnrollFace() {
  const { token, authHeaders } = useAuth()

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)

  const [studentId, setStudentId] = useState('')
  const [cameraOn, setCameraOn] = useState(false)
  const [capturedBlob, setCapturedBlob] = useState(null)
  const [capturedUrl, setCapturedUrl] = useState(null)
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadMode, setUploadMode] = useState('camera')
  const [status, setStatus] = useState({ msg: '', type: '' })
  const [lookupStatus, setLookupStatus] = useState({ msg: '', type: '' })
  const [enrolledFace, setEnrolledFace] = useState(null)

  async function lookupStudent() {
    if (!studentId) { setLookupStatus({ msg: 'Enter a student ID.', type: 'error' }); return }
    setLookupStatus({ msg: 'Looking up…', type: '' })
    try {
      const resp = await fetch(`/api/v1/students/${studentId}`, { headers: authHeaders() })
      const data = await resp.json()
      if (!resp.ok) { setLookupStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setEnrolledFace(data)
      setLookupStatus({ msg: `Found: ${data.full_name || data.student_code}`, type: 'success' })
    } catch {
      setLookupStatus({ msg: 'Network error.', type: 'error' })
    }
  }

  async function startCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 } } })
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
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    setCameraOn(false)
  }

  function captureFrame() {
    const video = videoRef.current, canvas = canvasRef.current
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

  async function enrollFace() {
    if (!studentId) { setStatus({ msg: 'Student ID is required.', type: 'error' }); return }
    const imageBlob = uploadMode === 'camera' ? capturedBlob : uploadFile
    if (!imageBlob) { setStatus({ msg: uploadMode === 'camera' ? 'Capture a photo first.' : 'Select an image file first.', type: 'error' }); return }

    setStatus({ msg: 'Enrolling face…', type: '' })

    const selfie_image_base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsDataURL(imageBlob)
    })

    try {
      const resp = await fetch('/api/v1/face/enroll', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: Number(studentId), selfie_image_base64 }),
      })
      const data = await resp.json()
      if (!resp.ok) { setStatus({ msg: parseApiError(data.detail), type: 'error' }); return }
      setStatus({ msg: `Face enrolled successfully for student #${studentId}. Embedding dimensions: ${data.embedding_dim || 512}.`, type: 'success' })
    } catch {
      setStatus({ msg: 'Enrollment failed. Check backend server.', type: 'error' })
    }
  }

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#a78bfa' }}>GeoFace Verify</div>
        <h1>Face Enrollment Console</h1>
        <p>Register a face embedding for a student profile using camera capture or image upload. InsightFace buffalo_l generates a 512-D embedding used for attendance verification.</p>
      </header>

      <main>
        <section className="card">
          <h2 className="section-title">Student Lookup</h2>
          <p className="section-sub">Look up the student profile before enrolling their face.</p>
          <div className="row">
            <div className="col">
              <label>Student ID</label>
              <input type="number" value={studentId} onChange={e => setStudentId(e.target.value)} placeholder="Student profile ID" />
            </div>
            <div className="col" style={{ alignSelf: 'flex-end' }}>
              <button onClick={lookupStudent}>Lookup Student</button>
            </div>
          </div>
          {lookupStatus.msg && (
            <div className={`status ${lookupStatus.type === 'error' ? 'errorText' : 'successText'}`}>{lookupStatus.msg}</div>
          )}
          {enrolledFace && (
            <div style={{ marginTop: 16, padding: 16, background: '#f8fafc', borderRadius: 12, border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                {enrolledFace.photo_url && (
                  <img src={enrolledFace.photo_url} alt="Student" style={{ width: 80, height: 80, borderRadius: '50%', objectFit: 'cover', border: '2px solid #e2e8f0' }} />
                )}
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>{enrolledFace.full_name || '--'}</div>
                  <div style={{ fontSize: 13, color: '#64748b' }}>{enrolledFace.student_code || ''} • {enrolledFace.trade || ''}</div>
                  <div style={{ marginTop: 6 }}>
                    <span className={`badge ${enrolledFace.face_enrolled ? 'badge-green' : 'badge-orange'}`}>
                      {enrolledFace.face_enrolled ? 'Face Enrolled ✓' : 'Face Not Enrolled'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="card">
          <h2 className="section-title">Face Capture</h2>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <button className={uploadMode === 'camera' ? 'success' : 'secondary'} onClick={() => setUploadMode('camera')}>📷 Camera</button>
            <button className={uploadMode === 'upload' ? 'success' : 'secondary'} onClick={() => setUploadMode('upload')}>📁 Upload File</button>
          </div>

          {uploadMode === 'camera' ? (
            <>
              <div className="camera-box">
                <label>{capturedUrl ? 'Captured Photo' : 'Camera Feed'}</label>
                {capturedUrl
                  ? <img src={capturedUrl} alt="Captured face" style={{ width: '100%', maxWidth: 400, height: 280, objectFit: 'cover', borderRadius: 14, border: '1px solid #e2e8f0' }} />
                  : <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%', maxWidth: 400, height: 280, objectFit: 'cover', borderRadius: 14, background: '#0f172a', border: '1px solid #e2e8f0' }} />
                }
                <canvas ref={canvasRef} style={{ display: 'none' }} />
              </div>
              <div className="button-row" style={{ marginTop: 12 }}>
                {!cameraOn && !capturedBlob && <button onClick={startCamera}>📷 Start Camera</button>}
                {cameraOn && <>
                  <button className="success" onClick={captureFrame}>📸 Capture</button>
                  <button className="secondary" onClick={stopCamera}>Stop</button>
                </>}
                {capturedBlob && <button className="secondary" onClick={() => { if (capturedUrl) URL.revokeObjectURL(capturedUrl); setCapturedBlob(null); setCapturedUrl(null); startCamera() }}>↺ Retake</button>}
              </div>
            </>
          ) : (
            <div className="col" style={{ maxWidth: 400 }}>
              <label>Select Image File</label>
              <input type="file" accept="image/*" onChange={e => setUploadFile(e.target.files[0])} />
              {uploadFile && <div className="small" style={{ marginTop: 4, color: '#059669' }}>Selected: {uploadFile.name}</div>}
            </div>
          )}
        </section>

        <section className="card">
          <h2 className="section-title">Enroll Face Embedding</h2>
          <p className="section-sub">
            Clicking Enroll will submit the face image to InsightFace, extract a 512-D embedding, and save it to the student profile. This replaces any previously enrolled face.
          </p>
          <div className="button-row">
            <button className="success" onClick={enrollFace}>Enroll Face</button>
          </div>
          {status.msg && (
            <div className={`status ${status.type === 'error' ? 'errorText' : 'successText'}`}>{status.msg}</div>
          )}
        </section>
      </main>
    </>
  )
}
