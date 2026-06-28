// Pure mappers: Google REST JSON → app item shapes. No IO; unit-testable.
import type { GmailItem, CalendarItem } from '../../shared/types'

type GmailHeader = { name: string; value: string }
export type GmailMessageJson = {
  id?: string
  snippet?: string
  internalDate?: string
  payload?: { headers?: GmailHeader[] }
}

function header(headers: GmailHeader[] | undefined, name: string): string {
  const h = headers?.find((x) => x.name.toLowerCase() === name.toLowerCase())
  return h?.value ?? ''
}

export function mapGmailMessage(m: GmailMessageJson): GmailItem | null {
  if (!m.id) return null
  const headers = m.payload?.headers
  return {
    id: m.id,
    subject: header(headers, 'Subject'),
    from: header(headers, 'From'),
    snippet: m.snippet ?? '',
    internalDateMs: m.internalDate ? Number(m.internalDate) || 0 : 0
  }
}

type CalDateTime = { dateTime?: string; date?: string }
export type CalEventJson = {
  id?: string
  summary?: string
  location?: string
  description?: string
  updated?: string
  start?: CalDateTime
  end?: CalDateTime
}

function eventMs(d: CalDateTime | undefined): number {
  const v = d?.dateTime ?? d?.date
  if (!v) return 0
  const t = Date.parse(v)
  return Number.isNaN(t) ? 0 : t
}

export function mapCalendarEvent(e: CalEventJson): CalendarItem | null {
  if (!e.id) return null
  return {
    id: e.id,
    title: e.summary ?? '(no title)',
    startMs: eventMs(e.start),
    endMs: eventMs(e.end),
    location: e.location || undefined,
    description: e.description || undefined,
    updatedMs: e.updated ? Date.parse(e.updated) || 0 : 0
  }
}
