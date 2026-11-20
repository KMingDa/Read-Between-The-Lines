// What a page shows when a request fails. The API client has already turned every failure into a
// readable ApiError and, for a 401 on the current session, signed the user out.
import { ApiError } from './client.ts'

export const UNEXPECTED_ERROR_MESSAGE = 'Something went wrong. Please try again.'
export const SESSION_CHANGED_MESSAGE = 'Your sign-in changed in another tab. Try again, or reload the page.'

/**
 * The message for a failed request. After a 401 the client has normally signed the user out, and
 * the page is replaced by the login page before this message can be seen. It is only seen when the
 * page stays, which happens when the sign-in changed in another tab (a new login or a logout).
 */
export function requestErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return UNEXPECTED_ERROR_MESSAGE // e.g. a reply that was not JSON
  return error.status === 401 ? SESSION_CHANGED_MESSAGE : error.message
}

/** True when the server answered 409 Conflict, e.g. for a chat this account already imported. */
export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409
}

/** True when the server answered 404 Not Found. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}
