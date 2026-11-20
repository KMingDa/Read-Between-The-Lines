import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import { useAuth } from '../auth/useAuth'

/** The signed-in page frame: top bar, the current page, footer. */
export function Layout() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <main className="app-container">
      <header className="topbar">
        <Link className="brand" to="/">
          <span className="brand-icon">R</span>
          <span>Read Between the Lines</span>
        </Link>
        <span className="version-label">EARLY PREVIEW</span>
        <button
          type="button"
          className="logout-button"
          onClick={handleLogout}
        >
          Log out
        </button>
      </header>

      {/* Its own row under the top bar, so the bar keeps its layout at every width */}
      <nav className="main-nav" aria-label="Main">
        <NavLink to="/conversations" end>
          Conversations
        </NavLink>
        <NavLink to="/conversations/import">Import</NavLink>
        <NavLink to="/analyze">Analyze</NavLink>
      </nav>

      <Outlet />

      <footer className="page-footer">
        <p>Read Between the Lines</p>
        <p>Thoughtful communication starts with curiosity, not assumptions.</p>
      </footer>
    </main>
  )
}
