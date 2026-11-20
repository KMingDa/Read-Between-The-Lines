import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router'
import { authErrorMessage, returnPath } from '../auth/session'
import { useAuth } from '../auth/useAuth'
import { RestoringSession } from '../components/RequireAuth'

export function LoginPage() {
  const { state, login, register } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isRegistering, setIsRegistering] = useState(false)
  const [authError, setAuthError] = useState(() =>
    state.status === 'signed-out' ? (state.notice ?? '') : '',
  )
  const [authLoading, setAuthLoading] = useState(false)

  if (state.status === 'restoring') {
    return <RestoringSession />
  }
  if (state.status === 'signed-in') {
    return <Navigate to={returnPath(location.state)} replace />
  }

  async function handleAuth() {
    if (authLoading) return

    setAuthLoading(true)
    setAuthError('')

    try {
      if (isRegistering) {
        await register(email.trim(), email.trim().split('@')[0], password)
        setIsRegistering(false)
        setPassword('')
        setAuthError('Registration successful. Please log in.')
        return
      }

      await login(email.trim(), password) // signed in: this page now redirects
    } catch (error) {
      setAuthError(authErrorMessage(error))
    } finally {
      setAuthLoading(false)
    }
  }

  return (
    <main className="auth-container">
      <section className="auth-card">
        <Link className="brand" to="/">
          <span className="brand-icon">R</span>
          <span>Read Between the Lines</span>
        </Link>

        <h1>{isRegistering ? 'Create your account' : 'Welcome back'}</h1>
        <p className="auth-description">
          {isRegistering
            ? 'Start understanding your conversations.'
            : 'Understand the conversations that matter.'}
        </p>

        <form
          onSubmit={(event) => {
            event.preventDefault()
            void handleAuth()
          }}
        >
          <label htmlFor="auth-email" className="input-label">
            Email
          </label>
          <input
            id="auth-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />

          <label htmlFor="auth-password" className="input-label">
            Password
          </label>
          <input
            id="auth-password"
            type="password"
            autoComplete={isRegistering ? 'new-password' : 'current-password'}
            minLength={isRegistering ? 8 : undefined}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={
              isRegistering ? 'At least 8 characters' : 'Enter your password'
            }
          />

          {authError && (
            <p className="auth-message" role="alert">
              {authError}
            </p>
          )}

          <button
            className="analyze-button"
            type="submit"
            disabled={authLoading}
          >
            {authLoading
              ? 'Please wait...'
              : isRegistering
                ? 'Create account'
                : 'Log in'}
            {!authLoading && <span aria-hidden="true">→</span>}
          </button>
        </form>

        <p className="auth-switch">
          {isRegistering
            ? 'Already have an account?'
            : "Don't have an account?"}{' '}
          <button
            type="button"
            className="auth-switch-button"
            onClick={() => {
              setIsRegistering(!isRegistering)
              setAuthError('')
              setPassword('')
            }}
          >
            {isRegistering ? 'Log in' : 'Sign up'}
          </button>
        </p>
      </section>
    </main>
  )
}
