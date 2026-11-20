import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { ApiError, SESSION_EXPIRED_MESSAGE, setToken, setUnauthorizedHandler } from './client.ts'
import {
  deleteConversation,
  getConversation,
  getMessages,
  importChat,
  listConversations,
  MESSAGE_PAGE_SIZE,
} from './conversations.ts'
import type { ConversationSummary, ImportResult } from './types.ts'
import { fakeApi, headersOf, json, resetFakeApi } from '../testing/fakeApi.ts'

const BASE = 'http://127.0.0.1:8000'

const SUMMARY: ConversationSummary = {
  id: 7,
  title: 'Alex',
  source: 'whatsapp',
  original_filename: 'WhatsApp Chat with Alex.txt',
  message_count: 3,
  first_message_at: '2026-10-10T21:00:00',
  last_message_at: '2026-10-10T21:05:00',
  date_order: 'day_first',
  date_order_ambiguous: false,
  imported_at: '2026-11-19T06:00:00Z',
}

const IMPORT_RESULT: ImportResult = {
  conversation: SUMMARY,
  detected_date_order: 'day_first',
  date_order_ambiguous: false,
  skipped_line_count: 0,
  warnings: [],
}

function chatFile(): File {
  return new File(['10/10/2026, 21:01 - Alex: hi\n'], 'WhatsApp Chat with Alex.txt', { type: 'text/plain' })
}

function lastCall() {
  const call = fakeApi.calls.at(-1)
  assert.ok(call, 'no request was sent')
  return call
}

beforeEach(() => {
  resetFakeApi()
  setToken('token-1')
})
afterEach(() => setUnauthorizedHandler(null))

// ---------- import ----------

test('importChat posts the file as multipart field "file" and returns the nested result', async () => {
  fakeApi.respond = () => json(201, IMPORT_RESULT)

  const result = await importChat(chatFile())

  assert.deepEqual(result, IMPORT_RESULT)
  const call = lastCall()
  assert.equal(call.url, `${BASE}/api/conversations/import`)
  assert.equal(call.init.method, 'POST')
  assert.ok(call.init.body instanceof FormData)
  const sent = call.init.body.get('file')
  assert.ok(sent instanceof File)
  assert.equal(sent.name, 'WhatsApp Chat with Alex.txt')
  assert.equal(await sent.text(), '10/10/2026, 21:01 - Alex: hi\n')
  assert.deepEqual(headersOf(call), { Authorization: 'Bearer token-1' }) // no Content-Type: the browser sets it
})

test('importChat leaves out date_order unless one is chosen', async () => {
  fakeApi.respond = () => json(201, IMPORT_RESULT)

  for (const options of [{}, { dateOrder: undefined }, { dateOrder: null }]) {
    await importChat(chatFile(), options)
    assert.equal((lastCall().init.body as FormData).has('date_order'), false)
  }

  await importChat(chatFile(), { dateOrder: 'month_first' })
  assert.equal((lastCall().init.body as FormData).get('date_order'), 'month_first')
})

// ---------- reading ----------

test('listConversations gets the list, which may be empty', async () => {
  fakeApi.respond = () => json(200, [SUMMARY])
  assert.deepEqual(await listConversations(), [SUMMARY])
  assert.equal(lastCall().url, `${BASE}/api/conversations`)
  assert.equal(lastCall().init.method, 'GET')

  fakeApi.respond = () => json(200, [])
  assert.deepEqual(await listConversations(), [])
})

test('getConversation gets one conversation by id', async () => {
  const detail = { ...SUMMARY, participants: [{ name: 'Alex', message_count: 2 }] }
  fakeApi.respond = () => json(200, detail)

  assert.deepEqual(await getConversation(7), detail)
  assert.equal(lastCall().url, `${BASE}/api/conversations/7`)
  assert.equal(lastCall().init.method, 'GET')
})

test('getMessages asks for offset 0 and the default page size of 200', async () => {
  fakeApi.respond = () => json(200, { items: [], total: 0, offset: 0, limit: 200 })

  await getMessages(7)

  assert.equal(MESSAGE_PAGE_SIZE, 200)
  const url = new URL(lastCall().url)
  assert.equal(url.pathname, '/api/conversations/7/messages')
  assert.deepEqual(Object.fromEntries(url.searchParams), { offset: '0', limit: '200' })
})

test('getMessages passes a chosen page through', async () => {
  const page = {
    items: [{ position: 200, sent_at: '2026-10-10T21:00:00', sender: null, content: 'Alex left' }],
    total: 201,
    offset: 200,
    limit: 50,
  }
  fakeApi.respond = () => json(200, page)

  assert.deepEqual(await getMessages(7, { offset: 200, limit: 50 }), page)
  assert.deepEqual(Object.fromEntries(new URL(lastCall().url).searchParams), { offset: '200', limit: '50' })
})

test('every call sends the bearer token and passes the AbortSignal', async () => {
  const controller = new AbortController()
  fakeApi.respond = () => json(200, [])

  await importChat(chatFile(), { signal: controller.signal })
  await listConversations({ signal: controller.signal })
  await getConversation(7, { signal: controller.signal })
  await getMessages(7, { signal: controller.signal })
  await deleteConversation(7, { signal: controller.signal })

  assert.equal(fakeApi.calls.length, 5)
  for (const call of fakeApi.calls) {
    assert.equal(headersOf(call).Authorization, 'Bearer token-1')
    assert.equal(call.init.signal, controller.signal)
  }
})

// ---------- deleting ----------

test('deleteConversation sends DELETE and resolves on 204', async () => {
  fakeApi.respond = () => new Response(null, { status: 204 })

  assert.equal(await deleteConversation(7), undefined)
  assert.equal(lastCall().url, `${BASE}/api/conversations/7`)
  assert.equal(lastCall().init.method, 'DELETE')
})

// ---------- errors ----------

test('backend errors arrive as ApiError with the server message', async () => {
  const cases: [() => Promise<unknown>, number, string][] = [
    [() => importChat(chatFile()), 409, 'This chat has already been imported.'],
    [() => importChat(chatFile()), 413, 'The file is larger than 5 MB.'],
    [() => getConversation(999), 404, 'Conversation not found.'],
    [() => getMessages(999), 404, 'Conversation not found.'],
    [() => deleteConversation(999), 404, 'Conversation not found.'],
  ]
  for (const [call, status, detail] of cases) {
    fakeApi.respond = () => json(status, { detail })
    await assert.rejects(call(), (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.deepEqual([error.status, error.message, error.detail], [status, detail, detail])
      return true
    })
  }
})

test('a 401 from a conversation call ends the session through the shared client', async () => {
  let handled = 0
  setUnauthorizedHandler(() => {
    handled += 1
    setToken(null)
  })
  fakeApi.respond = () => json(401, { detail: 'Invalid or expired token.' })

  await assert.rejects(listConversations(), { status: 401, message: SESSION_EXPIRED_MESSAGE })
  assert.equal(handled, 1)
})
