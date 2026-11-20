import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ApiError, CONNECTION_FAILED_MESSAGE, SESSION_EXPIRED_MESSAGE } from './client.ts'
import { isConflict, isNotFound, requestErrorMessage, SESSION_CHANGED_MESSAGE, UNEXPECTED_ERROR_MESSAGE } from './errors.ts'

test('a failed request shows the readable message the client already built', () => {
  assert.equal(requestErrorMessage(new ApiError(0, CONNECTION_FAILED_MESSAGE)), CONNECTION_FAILED_MESSAGE)
  assert.equal(
    requestErrorMessage(new ApiError(404, 'Conversation not found.', 'Conversation not found.')),
    'Conversation not found.',
  )
  assert.equal(requestErrorMessage(new ApiError(500, 'Request failed with status 500')), 'Request failed with status 500')
})

test('a 401 that leaves the page in place gets a message that fits, not "session expired"', () => {
  // Normally the client has signed out and the page is gone before this is shown. It stays when the
  // sign-in changed in another tab, and then "Your session has expired" would be wrong.
  assert.equal(requestErrorMessage(new ApiError(401, SESSION_EXPIRED_MESSAGE)), SESSION_CHANGED_MESSAGE)
})

test('anything other than an ApiError gets a general message, never its internals', () => {
  assert.equal(requestErrorMessage(new SyntaxError('Unexpected token < in JSON at position 0')), UNEXPECTED_ERROR_MESSAGE)
  assert.equal(requestErrorMessage('boom'), UNEXPECTED_ERROR_MESSAGE)
  assert.equal(requestErrorMessage(null), UNEXPECTED_ERROR_MESSAGE)
})

test('only a 409 from the server is a conflict (e.g. a chat that was already imported)', () => {
  assert.equal(isConflict(new ApiError(409, 'This chat has already been imported.')), true)
  for (const error of [new ApiError(400, 'x'), new ApiError(404, 'x'), new ApiError(0, 'x'), new Error('409'), null]) {
    assert.equal(isConflict(error), false, String(error))
  }
})

test('only a 404 from the server means "not found"', () => {
  assert.equal(isNotFound(new ApiError(404, 'Conversation not found.')), true)
  for (const error of [new ApiError(400, 'x'), new ApiError(410, 'x'), new ApiError(0, 'x'), new Error('404'), null]) {
    assert.equal(isNotFound(error), false, String(error))
  }
})
