import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { CONNECTION_FAILED_MESSAGE, setToken, setUnauthorizedHandler } from './api/client.ts'
import { SESSION_CHANGED_MESSAGE } from './api/errors.ts'
import type { ChatMessage, ConversationDetail, MessagePage } from './api/types.ts'
import {
  appendMessages,
  characterSplitter,
  hasMore,
  loadConversation,
  loadMoreMessages,
  messagePreview,
  messageRole,
  nextOffset,
  noticeFromLocationState,
  parseConversationId,
} from './conversationView.ts'
import { fakeApi, json, resetFakeApi } from './testing/fakeApi.ts'

const BASE = 'http://127.0.0.1:8000'

const DETAIL: ConversationDetail = {
  id: 7,
  title: 'Alex',
  source: 'whatsapp',
  original_filename: 'WhatsApp Chat with Alex.txt',
  message_count: 3,
  first_message_at: '2026-10-10T21:00:00',
  last_message_at: '2026-10-10T21:05:00',
  date_order: 'day_first',
  date_order_ambiguous: false,
  imported_at: '2026-11-19T06:00:00.123456Z',
  participants: [
    { name: 'Alex', message_count: 2 },
    { name: 'Sam', message_count: 1 },
  ],
}

function message(position: number, sender: string | null = 'Alex'): ChatMessage {
  return { position, sent_at: '2026-10-10T21:00:00', sender, content: `message ${position}` }
}

/** The messages at positions from to to - 1, as the backend returns them. */
function page(from: number, to: number, total: number): MessagePage {
  return { items: Array.from({ length: to - from }, (_, i) => message(from + i)), total, offset: from, limit: 200 }
}

const positions = (messages: ChatMessage[]) => messages.map((m) => m.position)
const live = () => new AbortController().signal

/** Answers the details request and the messages request separately. */
function answer(details: () => Response, messages: () => Response) {
  fakeApi.respond = (call) => (new URL(call.url).pathname.endsWith('/messages') ? messages() : details())
}

// Built from code points, so the source file holds no invisible joiner characters.
const FAMILY = String.fromCodePoint(0x1f468, 0x200d, 0x1f469, 0x200d, 0x1f467) // one emoji on screen, 5 code points
const SMILE = String.fromCodePoint(0x1f600) // one code point, two UTF-16 units

beforeEach(() => {
  resetFakeApi()
  setToken('token-1')
})
afterEach(() => setUnauthorizedHandler(null))

// ---------- the id in the URL ----------

test('a conversation id in the URL must be a plain positive whole number', () => {
  assert.equal(parseConversationId('7'), 7)
  assert.equal(parseConversationId('1234567'), 1234567)
  assert.equal(parseConversationId(String(Number.MAX_SAFE_INTEGER)), Number.MAX_SAFE_INTEGER)
  const refused = [undefined, '', '0', '-1', '007', '1.5', '1e3', ' 7', '7 ', 'abc', '0x1F', '9007199254740993']
  for (const param of refused) {
    assert.equal(parseConversationId(param), null, String(param))
  }
})

// ---------- pages of messages ----------

test('pages are added in export order, each position once', () => {
  const first = [message(0), message(1)]
  assert.deepEqual(positions(appendMessages(first, [message(2), message(3)])), [0, 1, 2, 3])
  // a retried page that overlaps what is shown adds only what is new
  assert.deepEqual(positions(appendMessages(first, [message(1), message(2)])), [0, 1, 2])
  // repeated and out-of-order positions within one page
  assert.deepEqual(positions(appendMessages([], [message(4), message(4), message(3)])), [3, 4])
})

test('a page that adds nothing gives back the same array, so nothing re-renders', () => {
  const loaded = [message(0)]
  assert.equal(appendMessages(loaded, []), loaded)
  assert.equal(appendMessages(loaded, [message(0)]), loaded)
})

test('the next page starts after the messages already loaded, until all are loaded', () => {
  const loaded = (count: number) => page(0, count, count).items
  assert.deepEqual([nextOffset(loaded(0)), hasMore(loaded(0), 450)], [0, true])
  assert.deepEqual([nextOffset(loaded(200)), hasMore(loaded(200), 450)], [200, true])
  assert.deepEqual([nextOffset(loaded(450)), hasMore(loaded(450), 450)], [450, false])
  assert.equal(hasMore(loaded(0), 0), false)
})

// ---------- long messages ----------

test('messages of up to 5,000 characters are shown whole', () => {
  for (const length of [0, 4_999, 5_000]) {
    const content = 'a'.repeat(length)
    assert.deepEqual(messagePreview(content), { text: content, hidden: 0 }, String(length))
  }
  // 5,000 emoji are 10,000 UTF-16 units but still 5,000 characters
  assert.deepEqual(messagePreview(SMILE.repeat(5_000)), { text: SMILE.repeat(5_000), hidden: 0 })
})

test('a longer message shows its first 5,000 characters and how many are left out', () => {
  assert.deepEqual(messagePreview('a'.repeat(5_001)), { text: 'a'.repeat(5_000), hidden: 1 })
  assert.deepEqual(messagePreview(`${'a'.repeat(5_000)}b${SMILE}c`), { text: 'a'.repeat(5_000), hidden: 3 })
})

test('the cut never splits an emoji, and line breaks are kept', () => {
  const content = `a\nb\n${FAMILY}cd` // characters: a, line break, b, line break, the emoji, c, d
  assert.deepEqual(messagePreview(content, 5), { text: `a\nb\n${FAMILY}`, hidden: 2 })
  // cut just before the emoji: it is left out whole; "hidden" counts its 5 code points
  assert.deepEqual(messagePreview(content, 4), { text: 'a\nb\n', hidden: 7 })
})

test('with Intl.Segmenter, an emoji joined from several code points is one character', () => {
  assert.deepEqual([...characterSplitter()(`a${FAMILY}b`)], ['a', FAMILY, 'b'])
})

test('without a working Intl.Segmenter: code points, so no crash and no split surrogate pair', () => {
  const broken = {
    Segmenter: class {
      constructor() {
        throw new RangeError('Intl.Segmenter is not supported here')
      }
    },
  } as unknown as { Segmenter: typeof Intl.Segmenter }

  for (const split of [characterSplitter({}), characterSplitter(broken)]) {
    assert.deepEqual([...split(`a${SMILE}b`)], ['a', SMILE, 'b'])
    assert.deepEqual(messagePreview(`a${SMILE}${SMILE}b`, 2, split), { text: `a${SMILE}`, hidden: 2 })
    // the joined emoji may be cut between its code points, but never inside one
    assert.deepEqual(messagePreview(FAMILY, 1, split), { text: String.fromCodePoint(0x1f468), hidden: 4 })
  }
})

// ---------- who wrote a message ----------

test('message roles: system without a sender; own only for the participant picked as "you"', () => {
  assert.equal(messageRole({ sender: null }, 'Alex'), 'system')
  assert.equal(messageRole({ sender: null }, null), 'system')
  assert.equal(messageRole({ sender: 'Alex' }, 'Alex'), 'own')
  assert.equal(messageRole({ sender: 'Sam' }, 'Alex'), 'other')
  assert.equal(messageRole({ sender: 'Alex' }, null), 'other') // "Not chosen"
  assert.equal(messageRole({ sender: 'alex' }, 'Alex'), 'other') // names come from the same export: exact
})

// ---------- loading a conversation ----------

test('the details and the first 200 messages are requested together', async () => {
  answer(() => json(200, DETAIL), () => json(200, page(0, 3, 3)))

  const outcome = await loadConversation(7, live())

  assert.deepEqual(outcome, {
    kind: 'loaded',
    conversation: DETAIL,
    messages: { kind: 'loaded', messages: page(0, 3, 3).items, total: 3 },
  })
  assert.deepEqual(fakeApi.calls.map((call) => call.url.replace(BASE, '')).sort(), [
    '/api/conversations/7',
    '/api/conversations/7/messages?offset=0&limit=200',
  ])
})

test('a 404 from either request means the conversation is not there', async () => {
  const gone = () => json(404, { detail: 'Conversation not found.' })
  answer(gone, gone)
  assert.deepEqual(await loadConversation(7, live()), { kind: 'not-found' })

  answer(() => json(200, DETAIL), gone) // deleted between the two requests
  assert.deepEqual(await loadConversation(7, live()), { kind: 'not-found' })
})

test('if only the messages fail, the details still show, with a messages error to retry', async () => {
  answer(() => json(200, DETAIL), () => new Response('<html>busy</html>', { status: 503 }))

  assert.deepEqual(await loadConversation(7, live()), {
    kind: 'loaded',
    conversation: DETAIL,
    messages: { kind: 'failed', message: 'Request failed with status 503' },
  })
})

test('connection and server failures of the details can be tried again', async () => {
  const cases: [() => Response, string][] = [
    [() => { throw new TypeError('Failed to fetch') }, CONNECTION_FAILED_MESSAGE],
    [() => new Response('<html>Internal Server Error</html>', { status: 500 }), 'Request failed with status 500'],
  ]
  for (const [details, message] of cases) {
    answer(details, () => json(200, page(0, 3, 3)))
    assert.deepEqual(await loadConversation(7, live()), { kind: 'failed', message })
  }
})

test('a 401 on both requests signs out once, through the shared client', async () => {
  let signedOut = 0
  setUnauthorizedHandler(() => {
    signedOut += 1
    setToken(null)
  })
  const expired = () => json(401, { detail: 'Invalid or expired token.' })
  answer(expired, expired)

  const outcome = await loadConversation(7, live())

  assert.equal(signedOut, 1)
  // The page is normally gone by now (redirect to /login); if it stays, this is what it shows.
  assert.deepEqual(outcome, { kind: 'failed', message: SESSION_CHANGED_MESSAGE })
})

test('cancelled before or while the replies arrive: cancelled, whatever came back', async () => {
  const replies = [
    () => { throw new DOMException('The operation was aborted.', 'AbortError') },
    () => json(200, DETAIL),
    () => json(500, { detail: 'boom' }),
  ]
  for (const reply of replies) {
    const controller = new AbortController()
    answer(
      () => {
        controller.abort() // e.g. the page was left
        return reply()
      },
      () => json(200, page(0, 3, 3)),
    )
    assert.deepEqual(await loadConversation(7, controller.signal), { kind: 'cancelled' })
  }
})

// ---------- loading more ----------

test('load more asks for the 200 after those loaded and merges them in order', async () => {
  const loaded = page(0, 200, 450).items
  fakeApi.respond = () => json(200, page(200, 400, 450))

  const outcome = await loadMoreMessages(7, loaded, live())

  assert.equal(fakeApi.calls[0].url, `${BASE}/api/conversations/7/messages?offset=200&limit=200`)
  assert.ok(outcome.kind === 'loaded')
  assert.equal(outcome.total, 450)
  assert.deepEqual(positions(outcome.messages), Array.from({ length: 400 }, (_, i) => i))
})

test('load more: deleted meanwhile is not found, failures can be tried again', async () => {
  const loaded = page(0, 200, 450).items
  const cases: [() => Response, unknown][] = [
    [() => json(404, { detail: 'Conversation not found.' }), { kind: 'not-found' }],
    [() => { throw new TypeError('Failed to fetch') }, { kind: 'failed', message: CONNECTION_FAILED_MESSAGE }],
    [() => new Response('<html>busy</html>', { status: 503 }), { kind: 'failed', message: 'Request failed with status 503' }],
  ]
  for (const [respond, expected] of cases) {
    fakeApi.respond = respond
    assert.deepEqual(await loadMoreMessages(7, loaded, live()), expected)
  }
})

test('load more cancelled while the reply arrives: cancelled, whether it is a page or an error', async () => {
  const loaded = page(0, 200, 450).items
  for (const reply of [() => json(200, page(200, 400, 450)), () => json(500, { detail: 'boom' })]) {
    const controller = new AbortController()
    fakeApi.respond = () => {
      controller.abort()
      return reply()
    }
    assert.deepEqual(await loadMoreMessages(7, loaded, controller.signal), { kind: 'cancelled' })
  }
})

// ---------- the notice after a delete ----------

test('the deletion notice passed through router state, and nothing for anything else', () => {
  assert.equal(noticeFromLocationState({ notice: 'Deleted “Alex”.' }), 'Deleted “Alex”.')
  for (const state of [null, undefined, 'x', 42, {}, { notice: '' }, { notice: 7 }, { notice: null }]) {
    assert.equal(noticeFromLocationState(state), null, JSON.stringify(state))
  }
})
