/** Format timestamps that reach the desktop-chat model.
 *
 * SQLite / GRDB cells and Windows epoch-ms integers are UTC instants. Printing
 * the UTC wall-clock without a zone made the model quote 7:59 PM for a 3:59 PM
 * Eastern event (#12321). Always convert in an injected IANA zone and label it.
 */

const TIMESTAMP_COLUMN = /^(timestamp|ts|.*(?:At|_at|Date|_date))$/

export function isTimestampColumn(name: string): boolean {
  return TIMESTAMP_COLUMN.test(name.trim())
}

function localParts(
  now: Date,
  timeZone: string
): { year: string; month: string; day: string; hour: string; minute: string; second: string } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).formatToParts(now)
  const value = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? ''
  return {
    year: value('year'),
    month: value('month'),
    day: value('day'),
    hour: value('hour'),
    minute: value('minute'),
    second: value('second')
  }
}

function hour12(hour23: number): { hour: number; period: 'AM' | 'PM' } {
  const period: 'AM' | 'PM' = hour23 >= 12 ? 'PM' : 'AM'
  const hour = hour23 % 12 === 0 ? 12 : hour23 % 12
  return { hour, period }
}

/** `2026-08-27 3:59:51 PM EDT (America/New_York)` */
export function formatUserFacingTimestamp(date: Date, timeZone: string): string {
  const parts = localParts(date, timeZone)
  const { hour, period } = hour12(Number(parts.hour))
  const short = new Intl.DateTimeFormat('en-US', {
    timeZone,
    timeZoneName: 'short'
  })
    .formatToParts(date)
    .find((part) => part.type === 'timeZoneName')?.value
  const zoneToken = short && short !== timeZone ? short : timeZone
  return `${parts.year}-${parts.month}-${parts.day} ${hour}:${parts.minute}:${parts.second} ${period} ${zoneToken} (${timeZone})`
}

function parseCellDate(value: unknown): Date | null {
  if (value == null) return null
  if (value instanceof Date) {
    return Number.isFinite(value.getTime()) ? value : null
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (value >= 1_000_000_000_000) return new Date(value)
    if (value >= 1_000_000_000) return new Date(value * 1000)
    return null
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return null
    const naive = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/.exec(trimmed)
    if (naive) {
      const parsed = Date.parse(`${naive[1]}T${naive[2]}Z`)
      if (Number.isFinite(parsed)) return new Date(parsed)
    }
    const iso = Date.parse(trimmed)
    if (Number.isFinite(iso)) return new Date(iso)
  }
  return null
}

/** Convert a UTC-naive SQL cell when the column is a datetime field. */
export function formatSqlTimestampCell(
  column: string,
  value: unknown,
  timeZone: string
): string | null {
  if (!isTimestampColumn(column)) return null
  const date = parseCellDate(value)
  if (!date) return null
  return formatUserFacingTimestamp(date, timeZone)
}

export function resolveChatTimeZone(timeZone?: string): string {
  if (timeZone?.trim()) return timeZone.trim()
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}
