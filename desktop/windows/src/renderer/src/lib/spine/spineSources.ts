// Maps the app's four data sources onto the spine model.
//
// Kept apart from spineModel.ts on purpose: the model is pure composition rules
// and should stay testable without knowing that a conversation arrives as an
// ISO string from the cloud while a task arrives as epoch milliseconds from
// SQLite. Every wire quirk is absorbed here.
//
// The one rule worth stating: a record that cannot be placed in time is
// DROPPED, not shown at epoch zero. A row with a broken timestamp sorts to the
// bottom of the oldest day and claims the user did something in 1970.

import type { Conversation, MemoryDB } from '../omiApi.generated'
import type { ActionItemRecord, SpineScreenDay } from '../../../../shared/types'
import type { SpineConversation, SpineDayScreen, SpineMemory, SpineTask } from './spineModel'

/** Epoch ms, or null when the value cannot be read as a time. */
export function parseWireTime(raw: string | null | undefined): number | null {
  if (typeof raw !== 'string' || raw.length === 0) return null
  const ms = Date.parse(raw)
  return Number.isFinite(ms) ? ms : null
}

/** A conversation the spine can place, or null when it cannot be timed. */
export function toSpineConversation(c: Conversation): SpineConversation | null {
  const startedAt = parseWireTime(c.started_at) ?? parseWireTime(c.created_at)
  if (startedAt === null) return null
  // An in-progress conversation has no finish time yet. Treating it as
  // zero-length would stop every frame captured during it from attaching, so it
  // stays open at its start instant until the server closes it.
  const finishedAt = parseWireTime(c.finished_at) ?? startedAt
  return {
    id: c.id,
    title: c.structured?.title?.trim() ?? '',
    overview: c.structured?.overview?.trim() ?? '',
    category: c.structured?.category ?? '',
    emoji: c.structured?.emoji ?? '💬',
    startedAt,
    finishedAt: Math.max(finishedAt, startedAt),
    starred: c.starred === true
  }
}

export function toSpineMemory(m: MemoryDB): SpineMemory | null {
  const timestamp = parseWireTime(m.created_at)
  if (timestamp === null) return null
  const text = (m.content ?? '').trim()
  if (text.length === 0) return null
  return {
    id: m.id,
    text,
    timestamp,
    conversationId: m.conversation_id ?? null
  }
}

export function toSpineTask(t: ActionItemRecord): SpineTask | null {
  const text = (t.description ?? '').trim()
  if (text.length === 0) return null
  if (!Number.isFinite(t.createdAt) || t.createdAt <= 0) return null
  return {
    id: String(t.id),
    text,
    timestamp: t.createdAt,
    conversationId: t.conversationId,
    completed: t.completed,
    // What produced the task, for the row's second line and its search text.
    sourceLabel: t.sourceApp ?? t.source ?? ''
  }
}

/** Screen projections from main, keyed by local-midnight epoch ms. */
export function toScreenMap(days: SpineScreenDay[]): Record<number, SpineDayScreen> {
  const out: Record<number, SpineDayScreen> = {}
  for (const day of days) {
    out[day.dayId] = {
      total: day.total,
      hourCounts:
        Array.isArray(day.hourCounts) && day.hourCounts.length === 24
          ? day.hourCounts
          : new Array<number>(24).fill(0),
      sampled: day.sampled.map((m) => ({
        id: m.id,
        timestamp: m.timestamp,
        appName: m.appName,
        windowTitle: m.windowTitle,
        imagePath: m.imagePath
      }))
    }
  }
  return out
}

/** Drops the nulls a mapper produced, keeping the callers free of the filter. */
export function compact<T>(items: Array<T | null>): T[] {
  return items.filter((item): item is T => item !== null)
}
