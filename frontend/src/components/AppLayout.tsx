import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { DocumentIcon, FlaskIcon, LogoutIcon, ShieldIcon } from './icons'

const NAV_ITEMS = [
  { to: '/documents', label: 'Documents', icon: DocumentIcon },
  { to: '/benchmarks', label: 'Benchmarks', icon: FlaskIcon },
  { to: '/sessions', label: 'Sessions', icon: ShieldIcon },
]

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">OL</div>
          <div className="sidebar-brand-text">
            <strong>OCRLab</strong>
            <span>Benchmarking console</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}>
              <Icon className="sidebar-link-icon" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="sidebar-user-label">Signed in as</span>
            <span className="sidebar-user-email" title={user?.email}>
              {user?.email}
            </span>
          </div>
          <button className="sidebar-signout" onClick={() => void logout()}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <LogoutIcon width={14} height={14} />
              Sign out
            </span>
          </button>
        </div>
      </aside>
      <div className="main-area">
        <Outlet />
      </div>
    </div>
  )
}
