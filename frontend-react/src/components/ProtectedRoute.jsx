import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, roles }) {
  const { user } = useAuth()

  if (!user) return <Navigate to="/login" replace />

  const role = (user.role || '').trim().toLowerCase()
  if (roles && !roles.includes(role)) {
    const landing = ['faculty', 'student'].includes(role) ? '/checkin' : '/'
    return <Navigate to={landing} replace />
  }

  return children
}
