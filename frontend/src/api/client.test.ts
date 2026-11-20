import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import {
  ApiError,
  apiRequest,
  CONNECTION_FAILED_MESSAGE,
  getToken,
  SESSION_EXPIRED_MESSAGE,
  setToken,
  setUnauthorizedHandler,
} from './client.ts'
import { fakeApi, headersOf, json, resetFakeApi } from '../testing/fakeApi.ts'

beforeEach(resetFakeApi)
afterEach(() => setUnauthorizedHandler(null))

// ---------- requests ----------

test('JSON requests send the body, its content type and the stored bearer token', async () => {
  setToken('token-1')

  const result = await apiRequest<{ ok: boolean }>('/api/analyze', { method: 'POST', json: { a: 1 } })

  assert.deepEqual(result, { ok: true })
  assert.equal(fakeApi.calls[0].url, 'http://127.0.0.1:8000/api/analyze')
  assert.equal(fakeApi.calls[0].init.method, 'POST')
  assert.equal(fakeApi.calls[0].init.body, '{"a":1}')
  assert.deepEqual(headersOf(fakeApi.calls[0]), { 'Content-Type': 'application/json', Authorization: 'Bearer token-1' })
})

test('FormData is sent as it is, with no Content-Type set by the client', async () => {
  const form = new FormData()
  form.append('file', new Blob(['chat']), 'chat.txt')

  await apiRequest('/api/conversations/import', { method: 'POST', form })

  assert.equal(fakeApi.calls[0].init.body, form)
  assert.equal('Content-Type' in headersOf(fakeApi.calls[0]), false) // the browser adds the multipart boundary
})

test('without a stored token no Authorization header is sent', async () => {
  await apiRequest('/api/me')

  assert.deepEqual(headersOf(fakeApi.calls[0]), {})
  assert.equal(fakeApi.calls[0].init.method, 'GET')
})

test('204 No Content resolves without reading a body', async () => {
  fakeApi.respond = () => new Response(null, { status: 204 })

  assert.equal(await apiRequest('/api/conversations/1', { method: 'DELETE' }), undefined)
})

test('the AbortSignal is passed to fetch and a cancelled request is not turned into an ApiError', async () => {
  const controller = new AbortController()
  fakeApi.respond = (call) => {
    assert.equal(call.init.signal, controller.signal)
    controller.abort()
    throw new DOMException('The operation was aborted.', 'AbortError')
  }

  await assert.rejects(apiRequest('/api/me', { signal: controller.signal }), { name: 'AbortError' })
})

// ---------- errors ----------

test('a string detail from FastAPI becomes the message', async () => {
  fakeApi.respond = () => json(409, { detail: 'This chat has already been imported.' })

  await assert.rejects(apiRequest('/x'), (error: unknown) => {
    assert.ok(error instanceof ApiError)
    assert.deepEqual([error.status, error.message, error.detail], [409, 'This chat has already been imported.', 'This chat has already been imported.'])
    return true
  })
})

test("FastAPI's list of validation errors becomes its first message", async () => {
  fakeApi.respond = () => json(422, { detail: [{ loc: ['body', 'password'], msg: 'String should have at least 8 characters', type: 'string_too_short' }] })

  await assert.rejects(apiRequest('/x'), (error: unknown) => {
    assert.ok(error instanceof ApiError)
    assert.deepEqual([error.status, error.message, error.detail], [422, 'String should have at least 8 characters', null])
    return true
  })
})

test('a response that is not JSON, or has no detail, gets a status message', async () => {
  fakeApi.respond = () => new Response('<html>Internal Server Error</html>', { status: 500 })
  await assert.rejects(apiRequest('/x'), { status: 500, message: 'Request failed with status 500', detail: null })

  fakeApi.respond = () => json(502, { error: 'bad gateway' })
  await assert.rejects(apiRequest('/x'), { status: 502, message: 'Request failed with status 502' })
})

test('an unreachable server gives status 0 and a readable message', async () => {
  fakeApi.respond = () => {
    throw new TypeError('Failed to fetch')
  }

  await assert.rejects(apiRequest('/x'), { status: 0, message: CONNECTION_FAILED_MESSAGE })
})

// ---------- 401 handling ----------

test('a 401 for the current token calls the handler once, even when several requests fail', async () => {
  setToken('expired')
  let handled = 0
  setUnauthorizedHandler(() => {
    handled += 1
    setToken(null) // what AuthProvider does
  })
  fakeApi.respond = () => json(401, { detail: 'Invalid or expired token.' })

  const results = await Promise.allSettled([apiRequest('/a'), apiRequest('/b'), apiRequest('/c')])

  assert.equal(handled, 1)
  for (const result of results) {
    assert.equal(result.status, 'rejected')
    assert.deepEqual([result.reason.status, result.reason.message], [401, SESSION_EXPIRED_MESSAGE])
  }
})

test('a late 401 for a token that was already replaced does not end the new session', async () => {
  setToken('old-session')
  let handled = 0
  setUnauthorizedHandler(() => {
    handled += 1
  })
  fakeApi.respond = () => {
    setToken('new-session') // the user logged in again while this request was in flight
    return json(401, { detail: 'Invalid or expired token.' })
  }

  await assert.rejects(apiRequest('/a'), { status: 401 })
  assert.equal(handled, 0)
  assert.equal(getToken(), 'new-session')
})

test('auth: false sends no token and leaves a 401 to the caller (wrong password)', async () => {
  setToken('some-token')
  let handled = 0
  setUnauthorizedHandler(() => {
    handled += 1
  })
  fakeApi.respond = () => json(401, { detail: 'Invalid email or password.' })

  await assert.rejects(
    apiRequest('/api/login', { method: 'POST', json: { email: 'a@b.co', password: 'x' }, auth: false }),
    { status: 401, message: 'Invalid email or password.', detail: 'Invalid email or password.' },
  )
  assert.equal('Authorization' in headersOf(fakeApi.calls[0]), false)
  assert.equal(handled, 0)
  assert.equal(getToken(), 'some-token')
})
