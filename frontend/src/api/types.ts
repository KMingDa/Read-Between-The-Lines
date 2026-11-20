// Response types of the FastAPI backend.

export type AuthUser = {
  id: number
  email: string
  username: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
  message: string
  user: AuthUser
}

export type RegisterResponse = {
  message: string
  user: AuthUser
}

export type ReplyDetail = {
  from: string
  to: string
  minutes: number
}

export type AnalysisResult = {
  observation: string
  interpretation: string
  suggested_next_step: string
  is_demo: boolean
  parsed_message_count: number
  reply_details: ReplyDetail[]
  reply_times: number[]
  average_reply_time_minutes: number | null
}

// ---------- conversations ----------

/** Clock time exactly as written in the export, e.g. "2026-10-10T21:00:00". It has no time zone:
 *  never read it as UTC or as the viewer's local time (use formatWallClock). */
export type WallClock = string

/** A real point in time, e.g. "2026-11-19T06:00:00Z" (use formatInstant). */
export type Instant = string

export type DateOrder = 'day_first' | 'month_first'

export type ConversationSummary = {
  id: number
  title: string
  source: string
  original_filename: string
  message_count: number // every stored message, system messages included
  first_message_at: WallClock // earliest message time
  last_message_at: WallClock // latest message time
  date_order: DateOrder
  date_order_ambiguous: boolean
  imported_at: Instant
}

export type Participant = {
  name: string
  message_count: number // system messages are not counted
}

export type ConversationDetail = ConversationSummary & {
  participants: Participant[]
}

export type ChatMessage = {
  position: number // 0-based export order
  sent_at: WallClock
  sender: string | null // null for a system message
  content: string
}

export type MessagePage = {
  items: ChatMessage[]
  total: number
  offset: number
  limit: number
}

export type ImportResult = {
  conversation: ConversationSummary
  detected_date_order: DateOrder
  date_order_ambiguous: boolean
  skipped_line_count: number
  warnings: string[]
}
