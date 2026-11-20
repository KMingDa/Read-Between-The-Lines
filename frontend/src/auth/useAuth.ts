import { createContext, useContext } from 'react'
import type { AuthUser } from '../api/types'

export type AuthState =
  | { status: 'restoring' } // a stored token is being checked with GET /api/me
  | { status: 'signed-out'; notice: string | null } // notice: why the user was signed out
  | { status: 'signed-in'; user: AuthUser }

export type AuthContextValue = {
  state: AuthState
  login: (email: string, password: string) => Promise<void>
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth must be used inside <AuthProvider>')
  }
  return value
}
