import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from '../auth/useAuth'

export function RestoringSession() {
  return (
    <main className="auth-container">
      <section className="auth-card">
        <p className="auth-description">Restoring your session...</p>
      </section>
    </main>
  )
}

/** Renders the child routes for signed-in users; everyone else goes to /login and comes back after. */
export function RequireAuth() {
  const { state } = useAuth()
  const location = useLocation()

  if (state.status === 'restoring') {
    return <RestoringSession />
  }
  if (state.status === 'signed-out') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return <Outlet />
}
