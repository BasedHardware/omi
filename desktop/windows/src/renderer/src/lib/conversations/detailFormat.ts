// Presentation helpers for the conversation detail header/metadata chips.
// Pure, and kept out of the page module so the page only exports components
// (react-refresh/only-export-components).

import type { Conversation } from '../omiApi.generated'

/** "5m 30s" — Mac's duration chip. Under a minute drops the minutes part. */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  const rem = s % 60
  return m === 0 ? `${rem}s` : `${m}m ${rem}s`
}

/**
 * Length of the conversation in seconds: the recorded window, falling back to
 * the last segment's end when the backend hasn't stamped `finished_at` yet
 * (which is the case for anything still in progress). null when neither is known.
 */
export function conversationDuration(c: Conversation): number | null {
  const start = c.started_at ?? c.created_at
  if (start && c.finished_at) {
    const secs = (new Date(c.finished_at).getTime() - new Date(start).getTime()) / 1000
    if (secs > 0) return secs
  }
  const last = c.transcript_segments?.at(-1)?.end
  return last && last > 0 ? last : null
}

/** "Jul 1, 2026 · 2:30 PM – 2:36 PM"; collapses to a single time with no end. */
export function formatWhen(c: Conversation): string {
  const start = c.started_at ?? c.created_at
  if (!start) return ''
  const s = new Date(start)
  const date = s.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const time = (d: Date): string =>
    d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  if (!c.finished_at) return `${date} · ${time(s)}`
  return `${date} · ${time(s)} – ${time(new Date(c.finished_at))}`
}

/** The category chip is hidden for the catch-all "other" bucket (Mac parity). */
export function displayCategory(c: Conversation): string | null {
  const cat = c.structured?.category
  return cat && cat !== 'other' ? cat : null
}
