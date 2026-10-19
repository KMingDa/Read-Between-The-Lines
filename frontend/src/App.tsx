import { useEffect, useState } from 'react'
import { API_BASE_URL } from './api'
import './App.css'

type ReplyDetail = {
  from: string
  to: string
  minutes: number
}

type AnalysisResult = {
  observation: string
  interpretation: string
  suggested_next_step: string
  is_demo: boolean
  parsed_message_count: number
  reply_details: ReplyDetail[]
  reply_times: number[]
  average_reply_time_minutes: number | null
}

type AuthUser = {
  id: number
  email: string
  username: string
}


function App() {
  
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isRegistering, setIsRegistering] = useState(false)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [accessToken, setAccessToken] = useState(() => localStorage.getItem('access_token') ?? '')
  const [isRestoringSession, setIsRestoringSession] = useState(() => Boolean(localStorage.getItem('access_token')))
  useEffect(() => {
    if (!accessToken) return

    let cancelled = false

    async function restoreSession() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/me`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        })

        if (!response.ok) {
          throw new Error('Session expired')
        }

        const user: AuthUser = await response.json()

        if (!cancelled) {
          setAuthUser(user)
        }
      } catch {
          if (!cancelled) {
            localStorage.removeItem('access_token')
            setAccessToken('')
            setAuthUser(null)
          }
        } finally {
          if (!cancelled) {
            setIsRestoringSession(false)
          }
        }
    }

    void restoreSession()

    return () => {
      cancelled = true
    }
  }, [accessToken])
  const [authError, setAuthError] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
  const [conversation, setConversation] = useState('')
  const [userName, setUserName] = useState('')
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleAnalyze() {
    if (!conversation.trim() || isLoading) return

    setIsLoading(true)
    setError('')
    setAnalysis(null)

    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          conversation: conversation.trim(),
          user_name: userName.trim(),
        }),
      })

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const result: AnalysisResult = await response.json()
      setAnalysis(result)
    } catch {
      setError(
        'Unable to connect to the backend. Make sure the FastAPI server is running and try again.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  
  async function handleAuth() {
    if (authLoading) return

    setAuthLoading(true)
    setAuthError('')

    try {
      const endpoint = isRegistering ? '/api/register' : '/api/login'

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(
          isRegistering
            ? {
                email: email.trim(),
                username: email.trim().split('@')[0],
                password,
              }
            : {
                email: email.trim(),
                password,
              },
        ),
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(
          typeof result.detail === 'string'
            ? result.detail
            : 'Authentication failed. Please check your details.',
        )
      }

      if (isRegistering) {
        setIsRegistering(false)
        setPassword('')
        setAuthError('Registration successful. Please log in.')
        return
      }

      setAuthUser(result.user)
      setAccessToken(result.access_token)
      localStorage.setItem('access_token', result.access_token)
    } catch (error) {
      setAuthError(
        error instanceof Error
          ? error.message
          : 'Unable to connect to the backend.',
      )
    } finally {
      setAuthLoading(false)
    }
  }

  function handleLogout() {
    localStorage.removeItem('access_token')
    setAccessToken('')
    setAuthUser(null)
    setEmail('')
    setPassword('')
    setAuthError('')
  }

  function handleConversationChange(value: string) {
    setConversation(value)
    setAnalysis(null)
    setError('')
  }

  if (isRestoringSession) {
    return (
      <main className="auth-container">
        <section className="auth-card">
          <p className="auth-description">Restoring your session...</p>
        </section>
      </main>
    )
  }

  if (!authUser) {
    return (
      <main className="auth-container">
        <section className="auth-card">
          <a className="brand" href="/">
            <span className="brand-icon">R</span>
            <span>Read Between the Lines</span>
          </a>

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

            {accessToken && (
              <p className="auth-message">
                Login successful.
              </p>
            )}
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

  return (
    <main className="app-container">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-icon">R</span>
          <span>Read Between the Lines</span>
        </a>
        <span className="version-label">EARLY PREVIEW</span>
        <button
          type="button"
          className="logout-button"
          onClick={handleLogout}
        >
          Log out
        </button>
      </header>

      <section className="hero-section">
        <p className="eyebrow">CONVERSATION INTELLIGENCE</p>
        <h1>
          Understand conversations.
          <br />
          <span>Communicate with clarity.</span>
        </h1>
        <p className="hero-description">
          Explore communication patterns, consider different interpretations,
          and find a thoughtful way to respond.
        </p>
      </section>

      <section className="workspace">
        <div className="section-heading">
          <div>
            <h2>Conversation analysis</h2>
            <p>Start with a conversation you want to understand.</p>
          </div>
          <span className="step-label">STEP 01</span>
        </div>

        <label htmlFor="userName" className="input-label">
          Your name in this conversation
        </label>

        <input
          id="userName"
          type="text"
          value={userName}
          onChange={(event) => setUserName(event.target.value)}
          placeholder="e.g. Jamie"
        />

        <label htmlFor="conversation" className="input-label">
          Your conversation
        </label>

        <textarea
          id="conversation"
          value={conversation}
          onChange={(event) => handleConversationChange(event.target.value)}
          placeholder={
            'Paste a conversation here...\n\nYou: Hey, how have you been lately?\nThem: Good haha'
          }
          rows={7}
        />

        <div className="input-footer">
          <p>For this demo, you can use fictional conversations.</p>
          <span>{conversation.length} characters</span>
        </div>

        <button
          className="analyze-button"
          type="button"
          onClick={handleAnalyze}
          disabled={!conversation.trim() || !userName.trim() || isLoading}
        >
          {isLoading ? 'Analyzing...' : 'Analyze Conversation'}
          {!isLoading && <span aria-hidden="true">→</span>}
        </button>

        <p className="privacy-note">
          <span aria-hidden="true">🔒</span>
          Avoid pasting passwords, contact details, or other sensitive
          personal information.
        </p>
      </section>

      {error && (
        <section className="results-section" role="alert">
          <h2>Something went wrong</h2>
          <p>{error}</p>
        </section>
      )}

      {analysis && (
        <section className="results-section" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="eyebrow">YOUR RESULTS</p>
              <h2>Conversation insights</h2>
            </div>
            {analysis.is_demo && <span className="demo-badge">DEMO ONLY</span>}
          </div>

          {analysis.is_demo && (
            <p className="demo-disclaimer">
              Reply intervals are calculated from the submitted chat text.
              Interpretations and suggested next steps are currently demo text,
              not AI-generated conclusions.
            </p>
          )}

          <article className="result-card">
            <span className="result-number">01</span>
            <div>
              <h3>Communication observation</h3>
              <p>{analysis.observation}</p>
            </div>
          </article>

          <article className="result-card">
            <span className="result-number">02</span>
            <div>
              <h3>Possible interpretation</h3>
              <p>{analysis.interpretation}</p>
            </div>
          </article>

          <article className="result-card">
            <span className="result-number">03</span>
            <div>
              <h3>Suggested next step</h3>
              <p>{analysis.suggested_next_step}</p>
            </div>
          </article>
         
          <article className="result-card">
            <span className="result-number">04</span>
            <div>
              <h3>Reply interval analysis</h3>
              <p>
                Parsed messages: {analysis.parsed_message_count}
              </p>

              {analysis.reply_details.length > 0 ? (
                <>
                  <ul>
                    {analysis.reply_details.map((detail, index) => (
                      <li key={`${detail.from}-${detail.to}-${index}`}>
                        <strong>{detail.from}</strong> replied to{' '}
                        {detail.to} after {detail.minutes} minutes
                      </li>
                    ))}
                  </ul>

                  <p>
                    <strong>Average reply interval:</strong>{' '}
                    {analysis.average_reply_time_minutes !== null
                      ? `${analysis.average_reply_time_minutes} minutes`
                      : 'Unavailable'}
                  </p>

                  <p>
                    Based on {analysis.reply_times.length}{' '}
                    {analysis.reply_times.length === 1 ? 'reply' : 'replies'}.
                  </p>
                </>
              ) : (
                <p>
                  No reply intervals could be calculated from the parsed messages.
                </p>
              )}
            </div>
          </article>
        </section>
      )}

      <footer className="page-footer">
        <p>Read Between the Lines</p>
        <p>Thoughtful communication starts with curiosity, not assumptions.</p>
      </footer>
    </main>
  )
}

export default App
