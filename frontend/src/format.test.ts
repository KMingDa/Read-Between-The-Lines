import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import {
  dateOrderLabel,
  formatCount,
  formatDateRange,
  formatFileSize,
  formatInstant,
  formatWallClock,
  MISSING,
  sourceLabel,
} from './format.ts'

const en = { locale: 'en-GB' }
const utc = { ...en, timeZone: 'UTC' }
const originalTimeZone = process.env.TZ

/** Runs the check as a viewer in each time zone (Node applies a changed TZ immediately). */
function inEachTimeZone(zones: string[], check: (zone: string) => void) {
  for (const zone of zones) {
    process.env.TZ = zone
    check(zone)
  }
}

afterEach(() => {
  // Assigning undefined would store the string "undefined" (an invalid zone that acts as UTC).
  if (originalTimeZone === undefined) {
    delete process.env.TZ
  } else {
    process.env.TZ = originalTimeZone
  }
})

// ---------- wall clock ----------

test('a wall-clock time is shown exactly as exported, for viewers in any time zone', () => {
  inEachTimeZone(['UTC', 'Europe/Berlin', 'America/New_York', 'Asia/Kolkata', 'Pacific/Auckland'], (zone) => {
    assert.equal(formatWallClock('2026-10-10T21:00:00', en), '10 Oct 2026, 21:00', zone)
    assert.equal(formatWallClock('2026-01-01T00:05:00', en), '1 Jan 2026, 00:05', zone)
  })
})

test('02:30 on a spring-forward day stays 02:30 (Europe/Berlin, 29 March 2026)', () => {
  inEachTimeZone(['Europe/Berlin'], () => {
    // Control: reading the value as local time would move it into the daylight-saving gap.
    assert.equal(new Date('2026-03-29T02:30:00').getHours(), 3)

    assert.equal(formatWallClock('2026-03-29T02:30:00', en), '29 Mar 2026, 02:30')
  })
})

test('02:30 on a spring-forward day stays 02:30 (America/New_York, 8 March 2026)', () => {
  inEachTimeZone(['America/New_York'], () => {
    assert.equal(new Date('2026-03-08T02:30:00').getHours(), 3) // control, as above

    assert.equal(formatWallClock('2026-03-08T02:30:00', en), '8 Mar 2026, 02:30')
  })
})

test('the repeated hour on a fall-back day is shown as written (Europe/Berlin, 25 October 2026)', () => {
  inEachTimeZone(['Europe/Berlin'], () => {
    assert.equal(formatWallClock('2026-10-25T02:50:00', en), '25 Oct 2026, 02:50')
    assert.equal(formatWallClock('2026-10-25T02:05:00', en), '25 Oct 2026, 02:05')
  })
})

test('seconds and fractions in a wall-clock value are accepted, minutes are shown', () => {
  assert.equal(formatWallClock('2026-10-10T21:30:05', en), '10 Oct 2026, 21:30')
  assert.equal(formatWallClock('2026-10-10T21:30:05.250000', en), '10 Oct 2026, 21:30')
  assert.equal(formatWallClock('2026-10-10T21:30', en), '10 Oct 2026, 21:30')
})

test("the viewer's locale decides the layout, not the time", () => {
  assert.equal(formatWallClock('2026-10-10T21:00:00', { locale: 'en-US' }), 'Oct 10, 2026, 9:00 PM')
})

// ---------- instants ----------

test('an instant with Z is shown in the given time zone', () => {
  const value = '2026-11-19T06:00:00Z'

  assert.equal(formatInstant(value, { ...en, timeZone: 'UTC' }), '19 Nov 2026, 06:00')
  assert.equal(formatInstant(value, { ...en, timeZone: 'Europe/Berlin' }), '19 Nov 2026, 07:00')
  assert.equal(formatInstant(value, { ...en, timeZone: 'America/New_York' }), '19 Nov 2026, 01:00')
  assert.equal(formatInstant(value, { ...en, timeZone: 'Asia/Kolkata' }), '19 Nov 2026, 11:30')
})

test('explicit offsets and microseconds are understood', () => {
  const berlin = { ...en, timeZone: 'Europe/Berlin' }

  assert.equal(formatInstant('2026-11-19T07:00:00+01:00', berlin), '19 Nov 2026, 07:00')
  assert.equal(formatInstant('2026-11-19T11:30:00+05:30', berlin), '19 Nov 2026, 07:00')
  assert.equal(formatInstant('2026-11-19T01:00:00-0500', berlin), '19 Nov 2026, 07:00')
  assert.equal(formatInstant('2026-11-19T06:00:00.123456Z', berlin), '19 Nov 2026, 07:00')
})

test("without a time zone option the viewer's own time zone is used", () => {
  inEachTimeZone(['Asia/Kolkata'], () => {
    assert.equal(formatInstant('2026-11-19T06:00:00Z', en), '19 Nov 2026, 11:30')
  })
})

test('an instant without an offset (SQLite) is read as UTC, not as the viewer\'s local time', () => {
  const berlin = { ...en, timeZone: 'Europe/Berlin' }

  // Viewers away from UTC, so reading it as local time would give a different answer.
  inEachTimeZone(['Asia/Kolkata', 'America/New_York'], (zone) => {
    assert.equal(formatInstant('2026-11-19T06:00:00', berlin), '19 Nov 2026, 07:00', zone)
    assert.equal(formatInstant('2026-11-19 06:00:00', berlin), '19 Nov 2026, 07:00', zone)
  })
})

test('six-digit microseconds (PostgreSQL) with Z or an offset keep the exact instant', () => {
  const berlin = { ...en, timeZone: 'Europe/Berlin' }
  const sameInstant = [
    '2026-11-19T06:00:00.123456Z', // imported_at as the backend sends it from PostgreSQL
    '2026-11-19T06:00:00.123456z',
    '2026-11-19T07:00:00.123456+01:00',
    '2026-11-19T07:00:00.123456+0100',
    '2026-11-19T01:00:00.123456-05:00',
    '2026-11-19T11:45:00.123456+05:45',
  ]
  for (const value of sameInstant) {
    assert.equal(formatInstant(value, berlin), '19 Nov 2026, 07:00', value)
  }
})

test('fractions are cut, never rounded, so the shown minute never moves', () => {
  // Rounding .999999 up would carry into the next minute, here the next day and year.
  assert.equal(formatInstant('2026-12-31T23:59:59.999999Z', utc), '31 Dec 2026, 23:59')
  assert.equal(formatInstant('2027-01-01T00:59:59.999999+01:00', utc), '31 Dec 2026, 23:59')
})

test('instants are worked out by arithmetic, never by handing the text to Date (browsers parse it differently)', () => {
  const RealDate = globalThis.Date
  const textsGivenToDate: unknown[] = []
  globalThis.Date = new Proxy(RealDate, {
    construct(target, args) {
      if (typeof args[0] === 'string') textsGivenToDate.push(args[0])
      return Reflect.construct(target, args)
    },
    get(target, key) {
      if (key !== 'parse') return Reflect.get(target, key)
      return (text: string) => {
        textsGivenToDate.push(text)
        return target.parse(text)
      }
    },
  })
  try {
    assert.equal(formatInstant('2026-11-19T07:00:00.123456+01:00', utc), '19 Nov 2026, 06:00')
  } finally {
    globalThis.Date = RealDate
  }
  assert.deepEqual(textsGivenToDate, [])
})

test('offsets from -12:00 to +14:00 are accepted; others, or invalid minutes, give the placeholder', () => {
  // The extremes in real use
  assert.equal(formatInstant('2026-11-19T20:00:00+14:00', utc), '19 Nov 2026, 06:00')
  assert.equal(formatInstant('2026-11-18T18:00:00-12:00', utc), '19 Nov 2026, 06:00')

  const invalid = [
    '+14:01', '+15:00', '-12:01', '-13:00', '+23:59', '+1401', // out of range
    '+05:60', '+13:60', '-0575', // invalid minutes (+13:60 would otherwise equal +14:00)
    '+05', '+05:30:00', // not an offset form we read
  ]
  for (const offset of invalid) {
    assert.equal(formatInstant(`2026-11-19T06:00:00${offset}`, utc), MISSING, offset)
  }
})

// ---------- date ranges ----------

test('a date range shows both days, or one day when they are the same', () => {
  assert.equal(formatDateRange('2026-10-10T21:00:00', '2026-11-12T08:15:00', en), '10 Oct 2026 – 12 Nov 2026')
  assert.equal(formatDateRange('2026-10-10T09:00:00', '2026-10-10T23:59:00', en), '10 Oct 2026')
})

test('a date range never shifts days: 23:30 stays on its own date in every time zone', () => {
  inEachTimeZone(['Pacific/Auckland', 'America/Los_Angeles'], (zone) => {
    assert.equal(formatDateRange('2026-10-10T23:30:00', '2026-10-11T00:30:00', en), '10 Oct 2026 – 11 Oct 2026', zone)
  })
})

test('a date range with one unreadable end shows the other; with none, the placeholder', () => {
  assert.equal(formatDateRange('2026-10-10T21:00:00', null, en), '10 Oct 2026')
  assert.equal(formatDateRange(undefined, '2026-11-12T08:15:00', en), '12 Nov 2026')
  assert.equal(formatDateRange('nonsense', '', en), MISSING)
})

// ---------- date order ----------

test('date-order labels; any other value from the server, even an inherited name, gives the placeholder', () => {
  assert.equal(dateOrderLabel('day_first'), 'Day first (dd/mm)')
  assert.equal(dateOrderLabel('month_first'), 'Month first (mm/dd)')
  for (const value of ['dmy', '', 'toString', 'constructor', '__proto__', 'hasOwnProperty', null, undefined]) {
    assert.equal(dateOrderLabel(value as never), MISSING, String(value))
  }
})

// ---------- source labels and counts ----------

test('source labels; an unknown source is shown as sent, never as an inherited name', () => {
  assert.equal(sourceLabel('whatsapp'), 'WhatsApp')
  assert.equal(sourceLabel('telegram'), 'telegram')
  assert.equal(sourceLabel('toString'), 'toString')
  assert.equal(sourceLabel(''), MISSING)
})

test('counts take the singular only for exactly one, with the number in the given locale', () => {
  assert.equal(formatCount(0, 'message', en), '0 messages')
  assert.equal(formatCount(1, 'message', en), '1 message')
  assert.equal(formatCount(2, 'conversation', en), '2 conversations')
  assert.equal(formatCount(1234, 'message', en), '1,234 messages')
  assert.equal(formatCount(1234, 'message', { locale: 'de-DE' }), '1.234 messages')
})

test('file sizes: bytes, then KB and MB in binary units with one decimal, rounded up', () => {
  assert.equal(formatFileSize(0, en), '0 bytes')
  assert.equal(formatFileSize(1, en), '1 byte')
  assert.equal(formatFileSize(1023, en), '1,023 bytes')
  assert.equal(formatFileSize(1024, en), '1 KB')
  assert.equal(formatFileSize(1536, en), '1.5 KB')
  assert.equal(formatFileSize(1025, en), '1.1 KB')
  assert.equal(formatFileSize(5_242_880, en), '5 MB') // the import limit itself
  assert.equal(formatFileSize(5_242_881, en), '5.1 MB') // one byte over never looks like the limit
  assert.equal(formatFileSize(1_572_864, { locale: 'de-DE' }), '1,5 MB')
})

// ---------- missing and invalid values ----------

test('missing or unreadable timestamps show the placeholder instead of a wrong date', () => {
  const unreadable = [
    null, undefined, '', 'not a date', '10/10/2026 21:00', '2026-10-10',
    '2026-02-30T10:00:00', // no 30 February
    '2026-13-01T10:00:00', // no month 13
    '2026-10-10T24:00:00', // no hour 24
    '2026-10-10T21:60:00', // no minute 60
    '2026-10-10T21:00:00.', // a dot without digits
    '2026-10-10T21:00.5', // a fraction needs seconds
  ]
  for (const value of unreadable) {
    assert.equal(formatWallClock(value, en), MISSING, `wall clock ${JSON.stringify(value)}`)
    assert.equal(formatInstant(value, en), MISSING, `instant ${JSON.stringify(value)}`)
  }
})

test('a wall-clock value carrying a time zone is rejected, not converted', () => {
  assert.equal(formatWallClock('2026-10-10T21:00:00Z', en), MISSING)
  assert.equal(formatWallClock('2026-10-10T21:00:00+02:00', en), MISSING)
})

// ---------- invalid options ----------

test('an invalid locale or time zone gives the placeholder instead of throwing', () => {
  const wall = '2026-10-10T21:00:00'
  const instant = '2026-11-19T06:00:00Z'
  for (const locale of ['!!', '', 'en_GB']) {
    assert.equal(formatWallClock(wall, { locale }), MISSING, JSON.stringify(locale))
    assert.equal(formatDateRange(wall, wall, { locale }), MISSING, JSON.stringify(locale))
    assert.equal(formatInstant(instant, { locale }), MISSING, JSON.stringify(locale))
    assert.equal(formatCount(3, 'message', { locale }), MISSING, JSON.stringify(locale))
    assert.equal(formatFileSize(2048, { locale }), MISSING, JSON.stringify(locale))
  }
  for (const timeZone of ['Mars/Olympus', '', 'Europe/Berlinn']) {
    assert.equal(formatInstant(instant, { ...en, timeZone }), MISSING, JSON.stringify(timeZone))
  }
})

test('other errors still surface instead of becoming the placeholder', () => {
  // A locale of the wrong type is a programming error, not bad input.
  assert.throws(() => formatWallClock('2026-10-10T21:00:00', { locale: null as never }), TypeError)
  assert.throws(() => formatCount(3, 'message', { locale: null as never }), TypeError)
  assert.throws(() => formatFileSize(2048, { locale: null as never }), TypeError)
})
