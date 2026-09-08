// Pure view-model helpers for the chat-sessions popover: client-side search
// filtering and date-bucket grouping. Kept free of React/DOM so they unit-test
// in the node env and the popover just renders their output.

import type { ChatSession } from '../../../shared/chatSessions'

/** Normalize a wire timestamp (epoch-ms number OR ISO-8601 string) to epoch ms.
 *  Returns 0 for unparseable input so a bad row sorts to the bottom, never NaN. */
export function toEpochMs(value: number | string | undefined): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  if (typeof value === 'string') {
    const ms = Date.parse(value)
    return Number.isFinite(ms) ? ms : 0
  }
  return 0
}

/**
 * Client-side substring filter (case-insensitive) over already-loaded sessions —
 * matches the Mac popover's live `searchQuery` filter, NOT a server query.
 * Matches the title and the preview (so searching for message text works). An
 * empty/whitespace query returns the input unchanged.
 */
export function filterSessions(sessions: ChatSession[], query: string): ChatSession[] {
  const q = query.trim().toLowerCase()
  if (!q) return sessions
  return sessions.filter((s) => {
    const title = (s.title ?? '').toLowerCase()
    const preview = (s.preview ?? '').toLowerCase()
    return title.includes(q) || preview.includes(q)
  })
}

/** A date-bucketed group of sessions, in display order. */
export interface SessionGroup {
  label: string
  sessions: ChatSession[]
}

const DAY_MS = 86_400_000

function startOfLocalDay(ms: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/**
 * Group sessions into the four macOS buckets, VERBATIM from
 * `ChatProvider.computeGroupedSessions()`: **Today** (same calendar day),
 * **Yesterday** (previous calendar day), **This Week** (`updatedAt` newer than
 * a rolling 7 days ago), then **Older**. Only non-empty buckets appear, always
 * in that fixed order. Input order is preserved within a bucket (the server
 * returns `updated_at DESC`, so newest-first is kept). `now` is injectable for
 * deterministic tests.
 */
export function groupSessionsByDate(
  sessions: ChatSession[],
  now: number = Date.now()
): SessionGroup[] {
  const todayStart = startOfLocalDay(now)
  const yesterdayStart = todayStart - DAY_MS
  const weekAgo = now - 7 * DAY_MS

  const today: ChatSession[] = []
  const yesterday: ChatSession[] = []
  const thisWeek: ChatSession[] = []
  const older: ChatSession[] = []

  for (const s of sessions) {
    const t = toEpochMs(s.updatedAt)
    const dayStart = startOfLocalDay(t)
    if (dayStart === todayStart) today.push(s)
    else if (dayStart === yesterdayStart) yesterday.push(s)
    else if (t > weekAgo) thisWeek.push(s)
    else older.push(s)
  }

  const groups: SessionGroup[] = []
  if (today.length) groups.push({ label: 'Today', sessions: today })
  if (yesterday.length) groups.push({ label: 'Yesterday', sessions: yesterday })
  if (thisWeek.length) groups.push({ label: 'This Week', sessions: thisWeek })
  if (older.length) groups.push({ label: 'Older', sessions: older })
  return groups
}
