import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiError, CONNECTION_FAILED_MESSAGE, SESSION_EXPIRED_MESSAGE } from '../api/client.ts'
import { authErrorMessage, returnPath, stateAfterUnauthorized } from './session.ts'

const user = { id: 1, email: 'alice@example.com', username: 'alice' }

// ---------- 401 ----------

test('a 401 while signed in signs out and says the session expired', () => {
  assert.deepEqual(stateAfterUnauthorized({ status: 'signed-in', user }), {
    status: 'signed-out',
    notice: SESSION_EXPIRED_MESSAGE,
  })
})

test('a 401 while restoring a stored session signs out silently, as before', () => {
  assert.deepEqual(stateAfterUnauthorized({ status: 'restoring' }), { status: 'signed-out', notice: null })
})

test('a repeated 401 changes nothing and keeps the first notice', () => {
  const signedOut = { status: 'signed-out', notice: SESSION_EXPIRED_MESSAGE } as const

  assert.equal(stateAfterUnauthorized(signedOut), signedOut)
})

// ---------- return URL ----------

test('after login the user returns to the page that sent them to /login', () => {
  assert.equal(returnPath({ from: { pathname: '/analyze', search: '?x=1', hash: '#top' } }), '/analyze?x=1#top')
  assert.equal(returnPath({ from: { pathname: '/conversations/7' } }), '/conversations/7')
})

test('without a usable return URL the start page is used', () => {
  for (const state of [null, undefined, 'x', {}, { from: null }, { from: { pathname: 42 } },
    { from: { pathname: '/login' } }, { from: { pathname: 'https://evil.example/' } }]) {
    assert.equal(returnPath(state), '/', JSON.stringify(state))
  }
})

// ---------- login card messages ----------

test('the login card shows the server message, the connection message, or the old generic text', () => {
  assert.equal(authErrorMessage(new ApiError(401, 'Invalid email or password.', 'Invalid email or password.')),
    'Invalid email or password.')
  assert.equal(authErrorMessage(new ApiError(409, 'Email is already registered.', 'Email is already registered.')),
    'Email is already registered.')
  assert.equal(authErrorMessage(new ApiError(0, CONNECTION_FAILED_MESSAGE)), CONNECTION_FAILED_MESSAGE)
  // FastAPI validation lists and non-JSON errors kept their generic text, as before
  assert.equal(authErrorMessage(new ApiError(422, 'String should have at least 8 characters')),
    'Authentication failed. Please check your details.')
  assert.equal(authErrorMessage(new Error('boom')), 'Authentication failed. Please check your details.')
})
