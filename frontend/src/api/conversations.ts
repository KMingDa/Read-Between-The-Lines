// Conversation endpoints. Every call goes through apiRequest, so the bearer token, readable
// errors and the session-expired (401) handling are the same as everywhere else.
import { apiRequest } from './client.ts'
import type {
  ConversationDetail,
  ConversationSummary,
  DateOrder,
  ImportResult,
  MessagePage,
} from './types.ts'

export const MESSAGE_PAGE_SIZE = 200 // the backend default; it allows at most 500
export const MAX_IMPORT_BYTES = 5 * 1024 * 1024 // the backend's limit for one upload ("5 MB")

type Options = { signal?: AbortSignal }

/** Upload a WhatsApp .txt export. Without a dateOrder the backend detects it from the file. */
export function importChat(
  file: File,
  { dateOrder, signal }: Options & { dateOrder?: DateOrder | null } = {},
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  if (dateOrder) {
    form.append('date_order', dateOrder)
  }
  return apiRequest<ImportResult>('/api/conversations/import', { method: 'POST', form, signal })
}

/** The signed-in user's conversations, newest import first; [] when there are none. */
export function listConversations({ signal }: Options = {}): Promise<ConversationSummary[]> {
  return apiRequest<ConversationSummary[]>('/api/conversations', { signal })
}

export function getConversation(conversationId: number, { signal }: Options = {}): Promise<ConversationDetail> {
  return apiRequest<ConversationDetail>(`/api/conversations/${conversationId}`, { signal })
}

/** A page of messages in export order. A page past the end has no items. */
export function getMessages(
  conversationId: number,
  { offset = 0, limit = MESSAGE_PAGE_SIZE, signal }: Options & { offset?: number; limit?: number } = {},
): Promise<MessagePage> {
  const query = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  return apiRequest<MessagePage>(`/api/conversations/${conversationId}/messages?${query}`, { signal })
}

/** Resolves when the conversation and its messages are gone (HTTP 204). */
export function deleteConversation(conversationId: number, { signal }: Options = {}): Promise<void> {
  return apiRequest<void>(`/api/conversations/${conversationId}`, { method: 'DELETE', signal })
}
