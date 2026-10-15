import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Spinner } from '../components/Spinner'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../lib/apiClient'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const redirectTo = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/documents'

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not sign in. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-side">
        <div className="auth-side-quote">
          “Benchmark Tesseract, EasyOCR, PaddleOCR, and docTR on the same page images, side by side.”
        </div>
        <div className="auth-side-meta">
          <div className="auth-side-rule" />
          OCRLab &mdash; reproducible OCR benchmarking
        </div>
      </div>
      <div className="auth-main">
        <div className="auth-card">
          <div className="auth-card-brand">
            <div className="sidebar-brand-mark">OL</div>
            <strong style={{ fontFamily: 'var(--font-head)', fontSize: 17 }}>OCRLab</strong>
          </div>
          <h2>Sign in</h2>
          <p className="auth-card-sub">Access your documents and benchmark history.</p>
          {error && <div style={{ marginBottom: 14 }}><Alert message={error} /></div>}
          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••••••"
              />
            </div>
            <button type="submit" className="btn btn-accent btn-block" disabled={isSubmitting}>
              {isSubmitting && <Spinner light />}
              Sign in
            </button>
          </form>
          <p className="auth-footer-note">
            Need an account? <Link to="/register">Create one</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
