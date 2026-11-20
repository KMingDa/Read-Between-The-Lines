// The single place that talks to the backend: base URL, bearer token, request bodies,
// readable errors and the "session expired" (401) signal.

export const API_BASE_URL = 'http://127.0.0.1:8000'

const TOKEN_KEY = 'access_token'

export const SESSION_EXPIRED_MESSAGE = 'Your session has expired. Please log in again.'
export const CONNECTION_FAILED_MESSAGE =
  'Unable to connect to the backend. Make sure the FastAPI server is running and try again.'

export class ApiError extends Error {
  readonly status: number // 0 when the server could not be reached
  readonly detail: string | null // the server's own message, when it sent one as text

  constructor(status: number, message: string, detail: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

let unauthorizedHandler: (() => void) | null = null

/** Called when an authenticated request gets 401 for the token that is still current. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'DELETE'
  json?: unknown
  form?: FormData
  signal?: AbortSignal
  /** Send the stored token and treat 401 as an expired session (default). False for login/register. */
  auth?: boolean
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, form, signal, auth = true } = options
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined

  if (form !== undefined) {
    body = form // the browser sets multipart/form-data with its boundary; never set it here
  } else if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  }

  const token = auth ? getToken() : null
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body, signal })
  } catch (error) {
    if (signal?.aborted) {
      throw error // a cancelled request; callers ignore it
    }
    throw new ApiError(0, CONNECTION_FAILED_MESSAGE)
  }

  if (response.status === 401 && auth) {
    // Only the token that is still current can end the session: a late 401 for an older
    // token (or a second 401 after the first one signed out) is ignored.
    if (token !== null && token === getToken()) {
      unauthorizedHandler?.()
    }
    throw new ApiError(401, SESSION_EXPIRED_MESSAGE)
  }

  if (!response.ok) {
    throw await errorFromResponse(response)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const fallback = `Request failed with status ${response.status}`
  let detail: unknown
  try {
    detail = ((await response.json()) as { detail?: unknown } | null)?.detail
  } catch {
    return new ApiError(response.status, fallback) // not JSON
  }

  if (typeof detail === 'string') {
    return new ApiError(response.status, detail, detail)
  }
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{"loc": [...], "msg": "...", ...}, ...]
    const first: unknown = detail[0]
    if (first && typeof first === 'object' && typeof (first as { msg?: unknown }).msg === 'string') {
      return new ApiError(response.status, (first as { msg: string }).msg)
    }
  }
  return new ApiError(response.status, fallback)
}
