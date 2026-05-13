import { useState, useEffect } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const NAV_ITEMS = [
  { icon: '🏠', label: 'Dashboard', to: '/', roles: ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'] },
  { icon: '📷', label: 'Attendance Console', to: '/checkin', roles: ['faculty', 'student', 'supervisor', 'hr', 'iti_coordinator', 'admin'] },
  { icon: '📋', label: 'Audit Trail', to: '/attendance-events', roles: ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'] },
  { icon: '⚠️', label: 'Anomalies', to: '/anomalies', roles: ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'] },
  { icon: '🗄️', label: 'Master Data', to: '/master-data', roles: ['admin'] },
  { icon: '👤', label: 'Face Enrollment', to: '/enroll-face', roles: ['admin'] },
  { icon: '🎓', label: 'Classroom Monitor', to: '/classroom', roles: ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'] },
]

function initials(name) {
  return (name || 'U')
    .split(' ')
    .slice(0, 2)
    .map(w => w[0] || '')
    .join('')
    .toUpperCase() || 'U'
}

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const role = ((user?.role) || '').trim().toLowerCase()
  const visibleItems = NAV_ITEMS.filter(item => !item.roles || item.roles.includes(role))

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  useEffect(() => {
    function handleClick(e) {
      const sidebar = document.querySelector('.app-sidebar')
      const toggle = document.querySelector('.sidebar-toggle')
      if (open && sidebar && !sidebar.contains(e.target) && e.target !== toggle) {
        setOpen(false)
      }
    }
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [open])

  return (
    <>
      <button className="sidebar-toggle" aria-label="Toggle navigation" onClick={() => setOpen(o => !o)}>
        ☰
      </button>

      <aside className={`app-sidebar${open ? ' open' : ''}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-kicker">ITI Attendance AI</div>
          <div className="sidebar-brand-name">
            <div className="sidebar-brand-logo">🔵</div>
            GeoFace Verify
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Navigation</div>
          {visibleItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
              onClick={() => setOpen(false)}
            >
              <span className="sidebar-link-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">{initials(user?.full_name || user?.username)}</div>
            <div style={{ overflow: 'hidden', minWidth: 0 }}>
              <div className="sidebar-user-name">{user?.full_name || user?.username || 'User'}</div>
              <div className="sidebar-user-role">{user?.role || ''}</div>
            </div>
          </div>
          <button className="sidebar-logout-btn" onClick={handleLogout}>
            <span>🚪</span> Logout
          </button>
        </div>
      </aside>
    </>
  )
}
