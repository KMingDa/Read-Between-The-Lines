import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { apiRequest, getToken, setToken, setUnauthorizedHandler } from '../api/client'
import type { AuthUser, LoginResponse, RegisterResponse } from '../api/types'
import { stateAfterUnauthorized } from './session'
import { AuthContext } from './useAuth'
import type { AuthState } from './useAuth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() =>
    getToken() ? { status: 'restoring' } : { status: 'signed-out', notice: null },
  )

  // Any 401 for the current token ends the session (see stateAfterUnauthorized).
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null)
      setState(stateAfterUnauthorized)
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  // Restore a stored session once on start. Any failure signs out, as before.
  useEffect(() => {
    if (!getToken()) return

    const controller = new AbortController()
    apiRequest<AuthUser>('/api/me', { signal: controller.signal })
      .then((user) => setState({ status: 'signed-in', user }))
      .catch(() => {
        if (controller.signal.aborted) return
        setToken(null)
        setState({ status: 'signed-out', notice: null })
      })
    return () => controller.abort()
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const result = await apiRequest<LoginResponse>('/api/login', {
      method: 'POST',
      json: { email, password },
      auth: false,
    })
    setToken(result.access_token)
    setState({ status: 'signed-in', user: result.user })
  }, [])

  const register = useCallback(async (email: string, username: string, password: string) => {
    await apiRequest<RegisterResponse>('/api/register', {
      method: 'POST',
      json: { email, username, password },
      auth: false,
    })
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setState({ status: 'signed-out', notice: null })
  }, [])

  const value = useMemo(() => ({ state, login, register, logout }), [state, login, register, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
