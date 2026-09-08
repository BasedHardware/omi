// Authenticated Gmail + Calendar REST reads (main). Reads Gmail metadata only
// (Subject/From/snippet — never the body) and the next 14 days of Calendar.
import { getAccessToken, invalidateAccessToken } from './oauth'
import { mapGmailMessage, mapCalendarEvent } from './googleMap'
import type { GmailMessageJson, CalEventJson } from './googleMap'
import type { GmailItem, CalendarItem } from '../../shared/types'

const GMAIL_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me'
const CAL_BASE = 'https://www.googleapis.com/calendar/v3'

async function authedJson<T>(url: string): Promise<T> {
  let token = await getAccessToken()
  let res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (res.status === 401) {
    // Cached token rejected — force a refresh and retry once.
    invalidateAccessToken()
    token = await getAccessToken()
    res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  }
  if (!res.ok) throw new Error(`Google API ${res.status}: ${await res.text()}`)
  return (await res.json()) as T
}

export async function fetchGmail(): Promise<GmailItem[]> {
  const q = encodeURIComponent('in:inbox newer_than:7d')
  const list = await authedJson<{ messages?: { id: string }[] }>(
    `${GMAIL_BASE}/messages?q=${q}&maxResults=25`
  )
  const ids = (list.messages ?? []).map((m) => m.id)
  const items: GmailItem[] = []
  for (const id of ids) {
    const msg = await authedJson<GmailMessageJson>(
      `${GMAIL_BASE}/messages/${id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From`
    )
    const item = mapGmailMessage(msg)
    if (item) items.push(item)
  }
  return items
}

export async function fetchCalendar(): Promise<CalendarItem[]> {
  const now = new Date()
  const params = new URLSearchParams({
    timeMin: now.toISOString(),
    timeMax: new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000).toISOString(),
    singleEvents: 'true',
    orderBy: 'startTime',
    maxResults: '50'
  })
  const data = await authedJson<{ items?: CalEventJson[] }>(
    `${CAL_BASE}/calendars/primary/events?${params.toString()}`
  )
  const items: CalendarItem[] = []
  for (const e of data.items ?? []) {
    const item = mapCalendarEvent(e)
    if (item) items.push(item)
  }
  return items
}
