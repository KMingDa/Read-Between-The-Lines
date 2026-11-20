import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <main className="auth-container">
      <section className="auth-card">
        <Link className="brand" to="/">
          <span className="brand-icon">R</span>
          <span>Read Between the Lines</span>
        </Link>

        <h1>Page not found</h1>
        <p className="auth-description">There is nothing at this address.</p>

        <p className="auth-switch">
          <Link className="auth-switch-button" to="/">
            Go to the start page
          </Link>
        </p>
      </section>
    </main>
  )
}
