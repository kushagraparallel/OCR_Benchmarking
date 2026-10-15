import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div style={{ display: 'grid', placeItems: 'center', height: '100vh', textAlign: 'center' }}>
      <div>
        <h1 style={{ fontSize: 48, marginBottom: 8 }}>404</h1>
        <p style={{ color: 'var(--ink-500)', marginBottom: 18 }}>This page does not exist.</p>
        <Link to="/documents" className="btn btn-accent">
          Back to documents
        </Link>
      </div>
    </div>
  )
}
