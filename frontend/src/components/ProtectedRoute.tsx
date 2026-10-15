import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { LoadingRow } from './Spinner'

export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'bootstrapping') {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
        <LoadingRow label="Restoring your session…" />
      </div>
    )
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
