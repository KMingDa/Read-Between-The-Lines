import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { CONNECTION_FAILED_MESSAGE, setToken, setUnauthorizedHandler } from './api/client.ts'
import { SESSION_CHANGED_MESSAGE, UNEXPECTED_ERROR_MESSAGE } from './api/errors.ts'
import type { ImportResult } from './api/types.ts'
import { chatFileProblem, dateOrderForUpload, fileAfter, UNREADABLE_FILE_MESSAGE, uploadChat } from './chatImport.ts'
import type { ImportOutcome } from './chatImport.ts'
import { fakeApi, json, resetFakeApi } from './testing/fakeApi.ts'

const ALREADY_IMPORTED = // the backend's message for a 409 (conversation_service.ALREADY_IMPORTED)
  'This chat has already been imported. To import it again (for example with a different date order), delete the existing conversation first.'

const IMPORT_RESULT: ImportResult = {
  conversation: {
    id: 7,
    title: 'Alex',
    source: 'whatsapp',
    original_filename: 'WhatsApp Chat with Alex.txt',
    message_count: 1,
    first_message_at: '2026-10-10T21:01:00',
    last_message_at: '2026-10-10T21:01:00',
    date_order: 'day_first',
    date_order_ambiguous: false,
    imported_at: '2026-11-19T06:00:00.123456Z',
  },
  detected_date_order: 'day_first',
  date_order_ambiguous: false,
  skipped_line_count: 0,
  warnings: [],
}

const CHAT_TEXT = '10/10/2026, 21:01 - Alex: hi\n'

function chatFile(): File {
  return new File([CHAT_TEXT], 'WhatsApp Chat with Alex.txt', { type: 'text/plain' })
}

function sentForm(): FormData {
  const call = fakeApi.calls.at(-1)
  assert.ok(call, 'no request was sent')
  assert.ok(call.init.body instanceof FormData)
  return call.init.body
}

const live = () => new AbortController().signal

beforeEach(() => {
  resetFakeApi()
  setToken('token-1')
})
afterEach(() => setUnauthorizedHandler(null))

// ---------- the browser's own checks ----------

test('a .txt export of up to 5 MB (5,242,880 bytes, as the backend counts) can be uploaded', () => {
  for (const name of ['WhatsApp Chat with Alex.txt', '_chat.txt', 'CHAT.TXT']) {
    assert.equal(chatFileProblem({ name, size: 10 }), null, name)
  }
  assert.equal(chatFileProblem({ name: 'chat.txt', size: 5_242_880 }), null)
})

test('other file types, empty files and files over 5 MB are refused before any upload', () => {
  const refused: [{ name: string; size: number }, RegExp][] = [
    [{ name: 'WhatsApp Chat with Alex.zip', size: 10 }, /“WhatsApp Chat with Alex\.zip” is not a \.txt file/],
    [{ name: 'chat.csv', size: 10 }, /is not a \.txt file/],
    [{ name: 'chat.txt.zip', size: 10 }, /is not a \.txt file/],
    [{ name: 'chat', size: 10 }, /is not a \.txt file/],
    [{ name: 'chat.txt', size: 0 }, /“chat\.txt” is empty/],
    [{ name: 'chat.txt', size: 5_242_881 }, /“chat\.txt” is 5[.,]1 MB; the limit is 5 MB/],
  ]
  for (const [file, expected] of refused) {
    assert.match(chatFileProblem(file) ?? 'no problem reported', expected, file.name)
  }
})

// ---------- date order ----------

test('date order: Auto sends none, so the backend detects it; a choice is sent as it is', () => {
  assert.equal(dateOrderForUpload('auto'), null)
  assert.equal(dateOrderForUpload('day_first'), 'day_first')
  assert.equal(dateOrderForUpload('month_first'), 'month_first')
})

test('the upload carries date_order only when one was chosen', async () => {
  fakeApi.respond = () => json(201, IMPORT_RESULT)

  await uploadChat(chatFile(), 'auto', live())
  assert.deepEqual([...sentForm().keys()], ['file'])

  await uploadChat(chatFile(), 'month_first', live())
  assert.deepEqual([...sentForm().keys()], ['file', 'date_order'])
  assert.equal(sentForm().get('date_order'), 'month_first')
})

// ---------- outcomes ----------

test('a successful import returns the nested result; the upload has the same name and content', async () => {
  fakeApi.respond = () => json(201, IMPORT_RESULT)

  const outcome = await uploadChat(chatFile(), 'auto', live())

  assert.deepEqual(outcome, { kind: 'imported', result: IMPORT_RESULT })
  const call = fakeApi.calls[0]
  assert.equal(call.url, 'http://127.0.0.1:8000/api/conversations/import')
  assert.equal(call.init.method, 'POST')
  const sent = sentForm().get('file')
  assert.ok(sent instanceof File)
  assert.equal(sent.name, 'WhatsApp Chat with Alex.txt')
  assert.equal(await sent.text(), CHAT_TEXT)
})

test('a 409 is a duplicate, with the server explanation (which names no conversation)', async () => {
  fakeApi.respond = () => json(409, { detail: ALREADY_IMPORTED })

  assert.deepEqual(await uploadChat(chatFile(), 'auto', live()), { kind: 'duplicate', message: ALREADY_IMPORTED })
})

test('413 and 422 mean the file itself cannot be imported, with the server explanation', async () => {
  const notUtf8 = 'The file is not UTF-8 text. Export the chat again from WhatsApp (Without media) and upload the .txt file.'
  for (const [status, detail] of [[413, 'The file is larger than 5 MB.'], [422, notUtf8]] as const) {
    fakeApi.respond = () => json(status, { detail })
    assert.deepEqual(await uploadChat(chatFile(), 'auto', live()), { kind: 'rejected', message: detail }, String(status))
  }
})

test('connection and server failures can be tried again, with a readable message', async () => {
  const cases: [() => Response, string][] = [
    [() => { throw new TypeError('Failed to fetch') }, CONNECTION_FAILED_MESSAGE],
    [() => new Response('<html>Internal Server Error</html>', { status: 500 }), 'Request failed with status 500'],
    [() => new Response('<html>not JSON</html>', { status: 201 }), UNEXPECTED_ERROR_MESSAGE],
  ]
  for (const [respond, message] of cases) {
    fakeApi.respond = respond
    assert.deepEqual(await uploadChat(chatFile(), 'auto', live()), { kind: 'failed', message })
  }
})

test('a 401 for the current sign-in ends the session through the shared client, once', async () => {
  let signedOut = 0
  setUnauthorizedHandler(() => {
    signedOut += 1
    setToken(null)
  })
  fakeApi.respond = () => json(401, { detail: 'Invalid or expired token.' })

  const outcome = await uploadChat(chatFile(), 'auto', live())

  assert.equal(signedOut, 1)
  // The page is normally gone by now (redirect to /login); if it stays, this is what it shows.
  assert.deepEqual(outcome, { kind: 'failed', message: SESSION_CHANGED_MESSAGE })
})

// ---------- reading the chosen file ----------

class UnreadableFile extends File {
  arrayBuffer(): Promise<ArrayBuffer> {
    return Promise.reject(new DOMException('The requested file could not be read.', 'NotReadableError'))
  }
}

test('a file that can no longer be read is reported as such, not as a connection failure, and nothing is sent', async () => {
  const outcome = await uploadChat(new UnreadableFile([CHAT_TEXT], 'chat.txt'), 'auto', live())

  assert.deepEqual(outcome, { kind: 'unreadable', message: UNREADABLE_FILE_MESSAGE })
  assert.notEqual(UNREADABLE_FILE_MESSAGE, CONNECTION_FAILED_MESSAGE)
  assert.equal(fakeApi.calls.length, 0)
})

test('a file whose size changed since it was chosen is treated as unreadable, and nothing is sent', async () => {
  const changed = chatFile()
  Object.defineProperty(changed, 'size', { value: 3 }) // its size when chosen; the file has grown since

  assert.deepEqual(await uploadChat(changed, 'auto', live()), { kind: 'unreadable', message: UNREADABLE_FILE_MESSAGE })
  assert.equal(fakeApi.calls.length, 0)
})

test('after an upload the chosen file is kept for another try, dropped after success or when unreadable', () => {
  const file = chatFile()
  const outcomes: [ImportOutcome, File | null][] = [
    [{ kind: 'imported', result: IMPORT_RESULT }, null], // the form starts over
    [{ kind: 'unreadable', message: UNREADABLE_FILE_MESSAGE }, null], // it must be chosen again
    [{ kind: 'duplicate', message: ALREADY_IMPORTED }, file],
    [{ kind: 'rejected', message: 'The file is empty.' }, file],
    [{ kind: 'failed', message: CONNECTION_FAILED_MESSAGE }, file],
  ]
  for (const [outcome, kept] of outcomes) {
    assert.equal(fileAfter(outcome, file), kept, outcome.kind)
  }
})

// ---------- cancelling ----------

test('cancelled before the reply: the outcome is cancelled', async () => {
  const controller = new AbortController()
  fakeApi.respond = () => {
    controller.abort()
    throw new DOMException('The operation was aborted.', 'AbortError')
  }

  assert.deepEqual(await uploadChat(chatFile(), 'auto', controller.signal), { kind: 'cancelled' })
})

test('cancelled while a reply arrives: still cancelled, whether the reply is an error or a success', async () => {
  for (const reply of [() => json(500, { detail: 'boom' }), () => json(201, IMPORT_RESULT)]) {
    const controller = new AbortController()
    fakeApi.respond = () => {
      controller.abort() // e.g. the page was left just as the answer came in
      return reply()
    }
    assert.deepEqual(await uploadChat(chatFile(), 'auto', controller.signal), { kind: 'cancelled' })
  }
})

test('cancelled while the file is being read: cancelled, and nothing is sent', async () => {
  const controller = new AbortController()
  class SlowFile extends File {
    async arrayBuffer(): Promise<ArrayBuffer> {
      controller.abort()
      return super.arrayBuffer()
    }
  }

  assert.deepEqual(await uploadChat(new SlowFile([CHAT_TEXT], 'chat.txt'), 'auto', controller.signal), { kind: 'cancelled' })
  assert.equal(fakeApi.calls.length, 0)
})
