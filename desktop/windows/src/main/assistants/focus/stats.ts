// Focus stats. Pure — port of Mac's `FocusStorage.computeStats`.
//
// The one thing to understand here: a focus_sessions ROW HAS NO DURATION. One
// row is one judgment at one instant, not a span. A session's duration is
// therefore INFERRED — it lasted until the next judgment, whenever that came, and
// the newest one is still running (so it lasts until `now`).
//
// That means duration comes from the row AFTER it in a newest-first list, i.e.
// sessions[i - 1]. Getting the direction of that lookup wrong silently swaps
// "focused" and "distracted" minutes, which is why it is spelled out.
import type { FocusSessionRecord } from '../../../shared/types'

export type FocusDayStats = {
  focusedMinutes: number
  distractedMinutes: number
  sessionCount: number
  focusedCount: number
  distractedCount: number
  /** Top 5 distracting apps by accumulated seconds. */
  topDistractions: { appOrSite: string; totalSeconds: number; count: number }[]
  /** 0–100. 0 when nothing has been measured yet (not NaN). */
  focusRate: number
}

const EMPTY: FocusDayStats = {
  focusedMinutes: 0,
  distractedMinutes: 0,
  sessionCount: 0,
  focusedCount: 0,
  distractedCount: 0,
  topDistractions: [],
  focusRate: 0
}

/** `sessions` must be NEWEST-FIRST (which is what `listFocusSessions` returns). */
export function computeStats(sessions: FocusSessionRecord[], now: number): FocusDayStats {
  if (sessions.length === 0) return EMPTY

  let focusedSeconds = 0
  let distractedSeconds = 0
  let focusedCount = 0
  let distractedCount = 0
  const byApp = new Map<string, { totalSeconds: number; count: number }>()

  for (let i = 0; i < sessions.length; i++) {
    const s = sessions[i]
    // The NEXT MORE RECENT session ended this one. For i === 0 there is none —
    // the latest judgment is still standing, so it runs up to `now`.
    const endTime = i === 0 ? now : sessions[i - 1].createdAt
    const duration = Math.max(0, (endTime - s.createdAt) / 1000)

    if (s.status === 'focused') {
      focusedSeconds += duration
      focusedCount += 1
    } else {
      distractedSeconds += duration
      distractedCount += 1
      const app = s.appOrSite ?? 'Unknown'
      const entry = byApp.get(app) ?? { totalSeconds: 0, count: 0 }
      entry.totalSeconds += duration
      entry.count += 1
      byApp.set(app, entry)
    }
  }

  const focusedMinutes = focusedSeconds / 60
  const distractedMinutes = distractedSeconds / 60
  const total = focusedMinutes + distractedMinutes

  return {
    focusedMinutes,
    distractedMinutes,
    sessionCount: sessions.length,
    focusedCount,
    distractedCount,
    topDistractions: [...byApp.entries()]
      .map(([appOrSite, v]) => ({ appOrSite, ...v }))
      .sort((a, b) => b.totalSeconds - a.totalSeconds)
      .slice(0, 5),
    // Guard the divide: a day with rows but zero elapsed time (every judgment in
    // the same millisecond — the analyzeNow dev hook can do exactly that) would
    // otherwise produce NaN and render as "NaN%".
    focusRate: total > 0 ? (focusedMinutes / total) * 100 : 0
  }
}

/** Stats for the calendar day containing `now` (local time). */
export function todayStats(sessions: FocusSessionRecord[], now: number): FocusDayStats {
  const start = new Date(now)
  start.setHours(0, 0, 0, 0)
  const startMs = start.getTime()
  return computeStats(
    sessions.filter((s) => s.createdAt >= startMs),
    now
  )
}
