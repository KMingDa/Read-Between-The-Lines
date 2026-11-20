// Display formatting for backend values. Two kinds of timestamps, never mixed up:
//   WallClock - the export's clock time, no time zone: shown exactly as written, in every time zone.
//   Instant   - a real moment: shown in the viewer's time zone (or a given one).
import type { DateOrder, Instant, WallClock } from './api/types.ts'

/** Shown for a missing or unreadable value. */
export const MISSING = '—'

export type FormatOptions = {
  locale?: string // default: the viewer's locale
}

export type InstantFormatOptions = FormatOptions & {
  timeZone?: string // default: the viewer's time zone
}

const WALL_CLOCK = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?$/
// The same reading (T or a space), then Z, ±hh:mm or ±hhmm; a value without one is UTC.
const INSTANT = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(?:Z|([+-])(\d{2}):?(\d{2}))?$/i

// UTC offsets in real use run from -12:00 to +14:00.
const MIN_OFFSET_MINUTES = -12 * 60
const MAX_OFFSET_MINUTES = 14 * 60

/** The reading as a Date whose UTC fields hold it, or null when it is not a real date and time. */
function wallClockAsUtc(value: string | null | undefined): Date | null {
  const match = typeof value === 'string' ? WALL_CLOCK.exec(value) : null
  if (!match) return null

  const [year, month, day, hour, minute] = match.slice(1, 6).map(Number)
  const second = match[6] === undefined ? 0 : Number(match[6])
  // Cut to milliseconds, never rounded: rounding .9999 up could carry into the next minute.
  const millisecond = match[7] === undefined ? 0 : Number(match[7].slice(0, 3).padEnd(3, '0'))
  const date = new Date(0)
  date.setUTCFullYear(year, month - 1, day) // also right for years below 100, unlike Date.UTC
  date.setUTCHours(hour, minute, second, millisecond)

  const rolledOver = // e.g. 30 February or 25:00, which Date would silently move to another day
    date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day ||
    date.getUTCHours() !== hour || date.getUTCMinutes() !== minute || date.getUTCSeconds() !== second
  return rolledOver ? null : date
}

/** A formatter, or null when the locale or time zone is not a valid identifier. */
function dateTimeFormat(locale: string | undefined, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat | null {
  try {
    return new Intl.DateTimeFormat(locale, options)
  } catch (error) {
    if (error instanceof RangeError) return null // e.g. locale "!!" or time zone "Mars/Olympus"
    throw error // anything else is a bug, not bad input
  }
}

/** A number formatter, or null when the locale is not a valid identifier. */
function numberFormat(locale: string | undefined): Intl.NumberFormat | null {
  try {
    return new Intl.NumberFormat(locale)
  } catch (error) {
    if (error instanceof RangeError) return null // e.g. locale "!!"
    throw error
  }
}

/** Export clock time, e.g. "10 Oct 2026, 21:00", identical for viewers in every time zone. */
export function formatWallClock(value: WallClock | null | undefined, { locale }: FormatOptions = {}): string {
  const date = wallClockAsUtc(value)
  if (!date) return MISSING
  // Printing UTC fields in UTC shows exactly the stored reading: no conversion and no
  // daylight-saving gap (02:30 on a spring-forward day stays 02:30).
  const format = dateTimeFormat(locale, { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' })
  return format ? format.format(date) : MISSING
}

/** The days a conversation spans, e.g. "10 Oct 2026 – 12 Nov 2026", or one day if they match. */
export function formatDateRange(
  first: WallClock | null | undefined,
  last: WallClock | null | undefined,
  { locale }: FormatOptions = {},
): string {
  const format = dateTimeFormat(locale, { timeZone: 'UTC', dateStyle: 'medium' })
  if (!format) return MISSING
  const [start, end] = [first, last].map((value) => {
    const date = wallClockAsUtc(value)
    return date ? format.format(date) : null
  })
  if (start && end) {
    return start === end ? start : `${start} – ${end}`
  }
  return start ?? end ?? MISSING
}

/** A real moment, e.g. imported_at, in the viewer's time zone. A value without an offset is
 *  read as UTC: the SQLite test backend stores CURRENT_TIMESTAMP, which is UTC. */
export function formatInstant(
  value: Instant | null | undefined,
  { locale, timeZone }: InstantFormatOptions = {},
): string {
  const match = typeof value === 'string' ? INSTANT.exec(value) : null
  if (!match) return MISSING

  const [, day, time, sign, offsetHours = '0', offsetMinutes = '0'] = match
  const reading = wallClockAsUtc(`${day}T${time}`) // null for e.g. 30 February
  const offset = (sign === '-' ? -1 : 1) * (Number(offsetHours) * 60 + Number(offsetMinutes)) // minutes ahead of UTC
  if (!reading || Number(offsetMinutes) > 59 || offset < MIN_OFFSET_MINUTES || offset > MAX_OFFSET_MINUTES) {
    return MISSING
  }

  // Arithmetic, not Date's string parsing, which differs between browsers (e.g. for microseconds).
  const format = dateTimeFormat(locale, { timeZone, dateStyle: 'medium', timeStyle: 'short' })
  return format ? format.format(reading.getTime() - offset * 60_000) : MISSING
}

const DATE_ORDER_LABELS: Record<DateOrder, string> = {
  day_first: 'Day first (dd/mm)',
  month_first: 'Month first (mm/dd)',
}

export function dateOrderLabel(order: DateOrder): string {
  // An own-key check, so an unexpected value at runtime (even "toString") gives MISSING.
  return Object.hasOwn(DATE_ORDER_LABELS, order) ? DATE_ORDER_LABELS[order] : MISSING
}

const SOURCE_LABELS: Record<string, string> = {
  whatsapp: 'WhatsApp',
}

/** The app a chat came from, e.g. "WhatsApp"; an unknown source is shown as sent. */
export function sourceLabel(source: string): string {
  return Object.hasOwn(SOURCE_LABELS, source) ? SOURCE_LABELS[source] : source || MISSING
}

/** "1 message", "1,234 messages": an English noun, with the number in the viewer's locale. */
export function formatCount(count: number, noun: string, { locale }: FormatOptions = {}): string {
  const format = numberFormat(locale)
  return format ? `${format.format(count)} ${count === 1 ? noun : `${noun}s`}` : MISSING
}

const KB = 1024
const MB = 1024 * 1024

/** "820 bytes", "14.2 KB", "5.1 MB": binary units as Windows shows them (and as the backend's
 *  5 MB limit counts), one decimal, rounded up so a file just over a limit never looks like it. */
export function formatFileSize(bytes: number, { locale }: FormatOptions = {}): string {
  if (bytes < KB) return formatCount(bytes, 'byte', { locale })
  const [size, unit] = bytes < MB ? [bytes / KB, 'KB'] : [bytes / MB, 'MB']
  const format = numberFormat(locale)
  return format ? `${format.format(Math.ceil(size * 10) / 10)} ${unit}` : MISSING
}
