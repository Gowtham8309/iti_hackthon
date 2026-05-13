import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Sidebar from './components/Sidebar'
import ProtectedRoute from './components/ProtectedRoute'
import LanguageToggle from './components/LanguageToggle'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import CheckIn from './pages/CheckIn'
import Anomalies from './pages/Anomalies'
import AttendanceEvents from './pages/AttendanceEvents'
import MasterData from './pages/MasterData'
import Classroom from './pages/Classroom'
import EnrollFace from './pages/EnrollFace'

const PAGE_ROLES = {
  '/': ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'],
  '/checkin': ['faculty', 'student', 'supervisor', 'hr', 'iti_coordinator', 'admin'],
  '/enroll-face': ['admin'],
  '/master-data': ['admin'],
  '/attendance-events': ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'],
  '/anomalies': ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'],
  '/classroom': ['supervisor', 'hr', 'iti_coordinator', 'district_officer', 'admin'],
}

function AuthenticatedLayout({ children }) {
  return (
    <>
      <Sidebar />
      <div style={{ paddingLeft: 'var(--sidebar-w)' }}>
        {children}
      </div>
    </>
  )
}

export default function App() {
  const { user } = useAuth()

  return (
    <>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />

        <Route path="/" element={
          <ProtectedRoute roles={PAGE_ROLES['/']}>
            <AuthenticatedLayout><Dashboard /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="/checkin" element={
          <ProtectedRoute roles={PAGE_ROLES['/checkin']}>
            <AuthenticatedLayout><CheckIn /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="/anomalies" element={
          <ProtectedRoute roles={PAGE_ROLES['/anomalies']}>
            <AuthenticatedLayout><Anomalies /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="/attendance-events" element={
          <ProtectedRoute roles={PAGE_ROLES['/attendance-events']}>
            <AuthenticatedLayout><AttendanceEvents /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="/master-data" element={
          <ProtectedRoute roles={PAGE_ROLES['/master-data']}>
            <AuthenticatedLayout><MasterData /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="/classroom" element={
          <ProtectedRoute roles={PAGE_ROLES['/classroom']}>
            <AuthenticatedLayout><Classroom /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="/enroll-face" element={
          <ProtectedRoute roles={PAGE_ROLES['/enroll-face']}>
            <AuthenticatedLayout><EnrollFace /></AuthenticatedLayout>
          </ProtectedRoute>
        } />

        <Route path="*" element={<Navigate to={user ? '/' : '/login'} replace />} />
      </Routes>
      <LanguageToggle />
    </>
  )
}
