import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Spinner } from '../components/Spinner'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../lib/apiClient'

const MIN_PASSWORD_LENGTH = 12

export function RegisterPage() {
  const { register, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setIsSubmitting(true)
    try {
      await register(email, password)
      await login(email, password)
      navigate('/documents', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create your account. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-side">
        <div className="auth-side-quote">
          “Every engine runs independently on identical rendered pages, so comparisons stay fair.”
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
          <h2>Create your account</h2>
          <p className="auth-card-sub">Upload PDFs and compare OCR engines on your own documents.</p>
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
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 12 characters"
              />
              <span className="field-hint">Use 12+ characters. We recommend a passphrase.</span>
            </div>
            <div className="field">
              <label htmlFor="confirm-password">Confirm password</label>
              <input
                id="confirm-password"
                className="input"
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Repeat your password"
              />
            </div>
            <button type="submit" className="btn btn-accent btn-block" disabled={isSubmitting}>
              {isSubmitting && <Spinner light />}
              Create account
            </button>
          </form>
          <p className="auth-footer-note">
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
