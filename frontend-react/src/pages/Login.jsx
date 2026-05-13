import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { API_BASE, parseApiError } from '../api/client'

const ROLE_LANDING = {
  faculty: '/checkin',
  student: '/checkin',
  supervisor: '/',
  hr: '/',
  iti_coordinator: '/',
  district_officer: '/',
  admin: '/',
}

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginStatus, setLoginStatus] = useState({ msg: '', type: '' })
  const [showReset, setShowReset] = useState(false)
  const [resetIdentifier, setResetIdentifier] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [resetNewPassword, setResetNewPassword] = useState('')
  const [resetStatus, setResetStatus] = useState({ msg: '', type: '' })

  const [signup, setSignup] = useState({
    student_code: '', full_name: '', iti_name: '', trade: '',
    batch: '', mobile: '', email: '', password: '',
  })
  const [signupFile, setSignupFile] = useState(null)
  const [signupStatus, setSignupStatus] = useState({ msg: '', type: '' })

  async function handleLogin(e) {
    e.preventDefault()
    setLoginStatus({ msg: 'Logging in…', type: '' })
    try {
      const resp = await fetch(API_BASE + '/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setLoginStatus({ msg: parseApiError(data.detail, 'Login failed.'), type: 'error' })
        return
      }
      login(data.access_token, data.user)
      const role = (data.user?.role || '').toLowerCase()
      navigate(ROLE_LANDING[role] || '/', { replace: true })
    } catch {
      setLoginStatus({ msg: 'Network error. Check backend server.', type: 'error' })
    }
  }

  async function requestPasswordReset() {
    setResetStatus({ msg: 'Sending reset token…', type: '' })
    try {
      const resp = await fetch(API_BASE + '/api/v1/auth/request-password-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: resetIdentifier }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setResetStatus({ msg: parseApiError(data.detail, 'Request failed.'), type: 'error' })
        return
      }
      if (data.reset_token) setResetToken(data.reset_token)
      setResetStatus({ msg: data.message || 'Reset token sent.', type: 'success' })
    } catch {
      setResetStatus({ msg: 'Network error.', type: 'error' })
    }
  }

  async function submitPasswordReset() {
    setResetStatus({ msg: 'Updating password…', type: '' })
    try {
      const resp = await fetch(API_BASE + '/api/v1/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: resetToken, new_password: resetNewPassword }),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setResetStatus({ msg: parseApiError(data.detail, 'Reset failed.'), type: 'error' })
        return
      }
      setResetStatus({ msg: 'Password updated. You can now log in.', type: 'success' })
      setShowReset(false)
    } catch {
      setResetStatus({ msg: 'Network error.', type: 'error' })
    }
  }

  async function handleSignup(e) {
    e.preventDefault()
    setSignupStatus({ msg: 'Creating account…', type: '' })
    try {
      let selfie_image_base64 = ''
      if (signupFile) {
        selfie_image_base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result.split(',')[1])
          reader.onerror = reject
          reader.readAsDataURL(signupFile)
        })
      }
      const payload = {
        ...signup,
        role: 'student',
        selfie_image_base64,
      }
      const resp = await fetch(API_BASE + '/api/v1/auth/student-signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await resp.json()
      if (!resp.ok) {
        setSignupStatus({ msg: parseApiError(data.detail, 'Signup failed.'), type: 'error' })
        return
      }
      setSignupStatus({ msg: 'Account created! You can now log in.', type: 'success' })
      setSignup({ student_code: '', full_name: '', iti_name: '', trade: '', batch: '', mobile: '', email: '', password: '' })
      setSignupFile(null)
    } catch {
      setSignupStatus({ msg: 'Network error.', type: 'error' })
    }
  }

  return (
    <>
      <header>
        <div className="brand-kicker" style={{ color: '#75e8c0' }}>GeoFace Verify</div>
        <h1>AI-Powered In-Plant Attendance Intelligence</h1>
        <p>
          Face-authenticated trainee check-ins, geo-fenced proof of presence, selfie evidence,
          anomaly intelligence, and supervisor-ready audit trails.
        </p>
      </header>

      <main>
        <section className="card">
          <div className="auth-shell">
            {/* Login Panel */}
            <div className="auth-panel">
              <div className="auth-kicker">Portal Access</div>
              <h2 className="section-title">Secure Role Login</h2>
              <p className="section-sub">One sign-in surface for students, supervisors, HR, district staff, and admins.</p>

              <form onSubmit={handleLogin}>
                <div className="row" style={{ marginTop: 16 }}>
                  <div className="col">
                    <label>Username</label>
                    <input
                      value={username}
                      onChange={e => setUsername(e.target.value)}
                      placeholder="faculty_code, student_code, or username"
                    />
                  </div>
                  <div className="col">
                    <label>Password</label>
                    <input
                      type="password"
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                    />
                  </div>
                </div>

                <div className="button-row" style={{ marginTop: 16 }}>
                  <button type="submit">Login</button>
                  <button type="button" className="secondary" onClick={() => setShowReset(r => !r)}>
                    Forgot Password?
                  </button>
                </div>
              </form>

              {loginStatus.msg && (
                <div className={`status ${loginStatus.type === 'error' ? 'errorText' : loginStatus.type === 'success' ? 'successText' : ''}`}>
                  {loginStatus.msg}
                </div>
              )}

              {showReset && (
                <div className="reset-panel">
                  <div className="reset-panel-title">Password Reset</div>
                  <p className="section-sub" style={{ marginBottom: 14, color: '#78350f' }}>
                    Two-step process: request a token, then set your new password.
                  </p>

                  <div className="reset-step">Step 1 — Request Token</div>
                  <div className="row">
                    <div className="col">
                      <label>Username</label>
                      <input
                        value={resetIdentifier}
                        onChange={e => setResetIdentifier(e.target.value)}
                        placeholder="Your username (e.g. yash)"
                      />
                    </div>
                    <div className="col" style={{ alignSelf: 'flex-end' }}>
                      <button className="secondary" type="button" onClick={requestPasswordReset}>
                        Send Reset Token
                      </button>
                    </div>
                  </div>

                  <hr className="reset-divider" />

                  <div className="reset-step">Step 2 — Set New Password</div>
                  <div className="row">
                    <div className="col">
                      <label>Reset Token</label>
                      <input
                        value={resetToken}
                        onChange={e => setResetToken(e.target.value)}
                        placeholder="Auto-filled or paste from email"
                      />
                    </div>
                    <div className="col">
                      <label>New Password</label>
                      <input
                        type="password"
                        value={resetNewPassword}
                        onChange={e => setResetNewPassword(e.target.value)}
                        placeholder="New password"
                      />
                    </div>
                    <div className="col" style={{ alignSelf: 'flex-end' }}>
                      <button className="success" type="button" onClick={submitPasswordReset}>
                        Set New Password
                      </button>
                    </div>
                  </div>

                  {resetStatus.msg && (
                    <div className={`status ${resetStatus.type === 'error' ? 'errorText' : 'successText'}`}>
                      {resetStatus.msg}
                    </div>
                  )}
                </div>
              )}

              <div className="role-chip-grid">
                {[
                  { role: 'Faculty', desc: 'Self attendance with linked biometric profile and classroom monitoring visibility.' },
                  { role: 'Student', desc: 'Profile-based attendance with face matching against the registered photo.' },
                  { role: 'Supervisor', desc: 'Monitor attendance, investigate anomalies, and review field incidents.' },
                  { role: 'HR', desc: 'Track industry-level visibility, roster coordination, and review load.' },
                  { role: 'Admin', desc: 'Manage users, profiles, locations, face enrollment, and operational settings.' },
                ].map(r => (
                  <div className="role-chip" key={r.role}>
                    <strong>{r.role}</strong>
                    <span>{r.desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Student Signup Panel */}
            <section className="auth-panel">
              <div className="auth-kicker">New Student</div>
              <h2 className="section-title">Student Self-Signup</h2>
              <p className="section-sub">Student self-signup is public. Faculty accounts must be created by admin.</p>

              <form onSubmit={handleSignup}>
                <div className="row" style={{ marginTop: 16 }}>
                  {[
                    { key: 'student_code', label: 'Student Code', placeholder: 'STU-GNT-2026-001' },
                    { key: 'full_name', label: 'Full Name', placeholder: 'Full name' },
                    { key: 'iti_name', label: 'ITI Name', placeholder: 'Govt ITI Visakhapatnam' },
                    { key: 'trade', label: 'Trade', placeholder: 'Electrician' },
                    { key: 'batch', label: 'Batch', placeholder: '2026' },
                    { key: 'mobile', label: 'Mobile', placeholder: '9876543210' },
                    { key: 'email', label: 'Email', placeholder: 'student@example.com' },
                  ].map(f => (
                    <div className="col" key={f.key}>
                      <label>{f.label}</label>
                      <input
                        value={signup[f.key]}
                        onChange={e => setSignup(s => ({ ...s, [f.key]: e.target.value }))}
                        placeholder={f.placeholder}
                      />
                    </div>
                  ))}
                  <div className="col">
                    <label>Password</label>
                    <input
                      type="password"
                      value={signup.password}
                      onChange={e => setSignup(s => ({ ...s, password: e.target.value }))}
                      placeholder="Create password"
                    />
                  </div>
                  <div className="col">
                    <label>Profile Photo</label>
                    <input type="file" accept="image/*" onChange={e => setSignupFile(e.target.files[0])} />
                  </div>
                </div>

                <div className="button-row" style={{ marginTop: 16 }}>
                  <button className="success" type="submit">Create Student Account</button>
                </div>
              </form>

              {signupStatus.msg && (
                <div className={`status ${signupStatus.type === 'error' ? 'errorText' : 'successText'}`}>
                  {signupStatus.msg}
                </div>
              )}
            </section>
          </div>
        </section>
      </main>
    </>
  )
}
