// The rules of the conversation detail page, kept out of the component so they can be unit-tested.
import { getConversation, getMessages } from './api/conversations.ts'
import { isNotFound, requestErrorMessage } from './api/errors.ts'
import type { ChatMessage, ConversationDetail } from './api/types.ts'

export const MESSAGE_PREVIEW_LENGTH = 5000 // characters shown before "Show full message"

export type MessageRole = 'system' | 'own' | 'other'

/** The first page of messages, or why it could not be loaded (the details may still show). */
export type MessagesOutcome =
  | { kind: 'loaded'; messages: ChatMessage[]; total: number }
  | { kind: 'failed'; message: string }

export type ConversationOutcome =
  | { kind: 'loaded'; conversation: ConversationDetail; messages: MessagesOutcome }
  | { kind: 'not-found' } // missing, deleted, or another account's: the backend makes them look the same
  | { kind: 'failed'; message: string }
  | { kind: 'cancelled' } // aborted, e.g. the page was left: nothing to show

export type MoreMessagesOutcome =
  | { kind: 'loaded'; messages: ChatMessage[]; total: number }
  | { kind: 'not-found' } // the conversation was deleted meanwhile
  | { kind: 'failed'; message: string }
  | { kind: 'cancelled' }

/** The first `limit` characters of a message, and how many code points are left out (0: all shown). */
export type MessagePreview = { text: string; hidden: number }

/** The id in the URL, or null unless it is a plain positive whole number, as the backend's ids are. */
export function parseConversationId(param: string | undefined): number | null {
  if (param === undefined || !/^[1-9]\d*$/.test(param)) return null
  const id = Number(param)
  return Number.isSafeInteger(id) ? id : null
}

/** The loaded messages plus a page, in export order and each position once, so a retried or
 *  overlapping page cannot show a message twice. The same array comes back when nothing is new. */
export function appendMessages(loaded: ChatMessage[], page: ChatMessage[]): ChatMessage[] {
  const seen = new Set(loaded.map((message) => message.position))
  const added: ChatMessage[] = []
  for (const message of page) {
    if (seen.has(message.position)) continue
    seen.add(message.position)
    added.push(message)
  }
  return added.length === 0 ? loaded : [...loaded, ...added].sort((a, b) => a.position - b.position)
}

/** Where the next page starts: the backend's offset is the number of messages to skip. */
export function nextOffset(loaded: ChatMessage[]): number {
  return loaded.length
}

export function hasMore(loaded: ChatMessage[], total: number): boolean {
  return loaded.length < total
}

/** System messages have no sender; "own" needs the participant picked as "you" on the page. */
export function messageRole(message: Pick<ChatMessage, 'sender'>, me: string | null): MessageRole {
  if (message.sender === null) return 'system'
  return message.sender === me ? 'own' : 'other'
}

type SegmenterIntl = { Segmenter?: typeof Intl.Segmenter }

/** Splits text into characters: the ones people see where Intl.Segmenter works (a joined emoji stays
 *  whole), otherwise code points, which never split a UTF-16 surrogate pair. */
export function characterSplitter(intl: SegmenterIntl = Intl): (text: string) => Iterable<string> {
  if (typeof intl.Segmenter === 'function') {
    try {
      const segmenter = new intl.Segmenter(undefined, { granularity: 'grapheme' })
      return function* (text) {
        for (const { segment } of segmenter.segment(text)) yield segment
      }
    } catch {
      // an incomplete implementation: use code points below
    }
  }
  return (text) => text // a string iterates by code point
}

const splitCharacters = characterSplitter()

/** The start of a long message; the content itself is never changed. */
export function messagePreview(content: string, limit = MESSAGE_PREVIEW_LENGTH, split = splitCharacters): MessagePreview {
  if (content.length <= limit) return { text: content, hidden: 0 } // never more characters than UTF-16 units
  let end = 0
  let count = 0
  for (const character of split(content)) {
    if (count === limit) break
    end += character.length
    count += 1
  }
  if (end === content.length) return { text: content, hidden: 0 }
  // shortcut: "hidden" counts code points (a joined emoji counts as several); counting what people see
  // across a 5 MB message took over 2 s, against about 20 ms for code points.
  return { text: content.slice(0, end), hidden: codePointsFrom(content, end) }
}

function codePointsFrom(text: string, start: number): number {
  let count = 0
  for (let i = start; i < text.length; i += 1) {
    const unit = text.charCodeAt(i)
    if (unit < 0xdc00 || unit > 0xdfff) count += 1 // the second half of a surrogate pair starts nothing new
  }
  return count
}

/** The details and the first page of messages, requested together. Never throws. */
export async function loadConversation(conversationId: number, signal: AbortSignal): Promise<ConversationOutcome> {
  const [details, firstPage] = await Promise.allSettled([
    getConversation(conversationId, { signal }),
    getMessages(conversationId, { signal }),
  ])
  if (signal.aborted) return { kind: 'cancelled' } // whatever came back
  if (details.status === 'rejected') {
    if (isNotFound(details.reason)) return { kind: 'not-found' }
    return { kind: 'failed', message: requestErrorMessage(details.reason) }
  }
  if (firstPage.status === 'rejected') {
    if (isNotFound(firstPage.reason)) return { kind: 'not-found' } // deleted between the two requests
    const messages: MessagesOutcome = { kind: 'failed', message: requestErrorMessage(firstPage.reason) }
    return { kind: 'loaded', conversation: details.value, messages }
  }
  const messages = appendMessages([], firstPage.value.items)
  return { kind: 'loaded', conversation: details.value, messages: { kind: 'loaded', messages, total: firstPage.value.total } }
}

/** The next page, merged into the loaded messages. Never throws. */
export async function loadMoreMessages(
  conversationId: number,
  loaded: ChatMessage[],
  signal: AbortSignal,
): Promise<MoreMessagesOutcome> {
  try {
    const page = await getMessages(conversationId, { offset: nextOffset(loaded), signal })
    if (signal.aborted) return { kind: 'cancelled' }
    return { kind: 'loaded', messages: appendMessages(loaded, page.items), total: page.total }
  } catch (error) {
    if (signal.aborted) return { kind: 'cancelled' } // whatever the error says
    if (isNotFound(error)) return { kind: 'not-found' }
    return { kind: 'failed', message: requestErrorMessage(error) }
  }
}

/** The "Deleted …" notice a page passes to the list through router state, if there is one. */
export function noticeFromLocationState(state: unknown): string | null {
  const notice = (state as { notice?: unknown } | null | undefined)?.notice
  return typeof notice === 'string' && notice !== '' ? notice : null
}
