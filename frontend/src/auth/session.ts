// Pure session rules, kept out of the components so they can be unit-tested.
import { ApiError, SESSION_EXPIRED_MESSAGE } from '../api/client.ts'
import type { AuthState } from './useAuth.ts'

/** The state after the API reported 401 for the current token. Repeating it changes nothing. */
export function stateAfterUnauthorized(previous: AuthState): AuthState {
  if (previous.status === 'signed-out') {
    return previous
  }
  // A signed-in user is told why; a stored token that fails while restoring is dropped silently.
  return {
    status: 'signed-out',
    notice: previous.status === 'signed-in' ? SESSION_EXPIRED_MESSAGE : null,
  }
}

/** Where to go after logging in: the page that sent the user to /login, else the start page. */
export function returnPath(locationState: unknown): string {
  const from = (locationState as { from?: { pathname?: unknown; search?: unknown; hash?: unknown } } | null)
    ?.from
  if (typeof from?.pathname !== 'string' || !from.pathname.startsWith('/') || from.pathname === '/login') {
    return '/'
  }
  const search = typeof from.search === 'string' ? from.search : ''
  const hash = typeof from.hash === 'string' ? from.hash : ''
  return `${from.pathname}${search}${hash}`
}

/** The message the login/register card shows for a failed request. */
export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.detail !== null) return error.detail // e.g. "Invalid email or password."
    if (error.status === 0) return error.message // the backend could not be reached
  }
  return 'Authentication failed. Please check your details.'
}
