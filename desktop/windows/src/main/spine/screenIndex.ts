// Per-day screen capture, projected for the Activity spine.
//
// One day of capture is thousands of frames; the spine shows at most eight per
// strip and a 24-bar histogram. So this reads three different things at three
// different resolutions rather than shipping the day across IPC and letting the
// renderer throw most of it away:
//
//   total       exact COUNT over the day
//   hourCounts  exact, from the day's timestamps alone (one INTEGER per row)
//   sampled     a bounded, evenly-spaced sample of whole frames
//
// Hour bucketing is done in JS from the epoch-ms timestamp, deliberately not in
// SQL. SQLite's date functions would need an explicit 'localtime' modifier and
// would still bucket against the server-style UTC day; doing it here means the
// histogram matches the local calendar the spine groups days by, including on a
// DST-transition day where one local hour has twice the frames and another has
// none.

import { cachedStmt } from '../ipc/stmtCache'

/** Minimal DB surface — satisfied structurally by better-sqlite3 (production)
 *  and node:sqlite's DatabaseSync (tests). Positional `?` params only. */
export interface ScreenIndexDb {
  prepare(sql: string): {
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

export interface ScreenMoment {
  id: number
  timestamp: number
  appName: string
  windowTitle: string | null
  imagePath: string | null
}

export interface ScreenDayProjection {
  /** Local midnight, epoch ms. */
  dayId: number
  /** Exact frame count for the day. */
  total: number
  /** 24 entries, index = local hour. Exact, never sampled. */
  hourCounts: number[]
  sampled: ScreenMoment[]
}

/** Frames carried across IPC per day. The strip shows 8; the surplus is what
 *  lets a cluster split on a gap and still have frames on both sides. */
export const SCREEN_SAMPLE_TARGET = 240

export function startOfLocalDay(ts: number): number {
  const d = new Date(ts)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** Exclusive end of the local day starting at `dayId`. Computed by adding one
 *  calendar day rather than 24 hours, so a DST day is 23 or 25 hours long and
 *  no frame falls into a gap between two days. */
export function endOfLocalDay(dayId: number): number {
  const d = new Date(dayId)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1).getTime()
}

/** Buckets timestamps into 24 local-hour counts. Exported for its own test:
 *  this is the part a UTC-based implementation gets wrong. */
export function bucketByLocalHour(timestamps: number[]): number[] {
  const counts = new Array<number>(24).fill(0)
  for (const ts of timestamps) {
    const hour = new Date(ts).getHours()
    if (hour >= 0 && hour < 24) counts[hour] += 1
  }
  return counts
}

/** Evenly-spaced sample indices for `n` rows down to at most `target`. Keeping
 *  the step as an integer means the sample is spread across the whole day rather
 *  than clustered at one end. */
export function sampleStep(n: number, target: number): number {
  if (n <= target || target <= 0) return 1
  return Math.max(1, Math.ceil(n / target))
}

interface FrameRow {
  id: number
  ts: number
  app: string
  window_title: string
  path: string
}

const toMoment = (row: FrameRow): ScreenMoment => ({
  id: row.id,
  timestamp: row.ts,
  appName: row.app,
  windowTitle: row.window_title.length > 0 ? row.window_title : null,
  imagePath: row.path.length > 0 ? row.path : null
})

/**
 * Projects one local day. Returns a zeroed projection for a day with no
 * capture, which is a real answer ("read, and there was nothing") and distinct
 * from the caller never asking.
 */
export function projectScreenDay(
  db: ScreenIndexDb,
  dayId: number,
  target = SCREEN_SAMPLE_TARGET
): ScreenDayProjection {
  const from = dayId
  const to = endOfLocalDay(dayId)

  const stamps = (
    cachedStmt(db, `SELECT ts FROM rewind_frames WHERE ts >= ? AND ts < ? ORDER BY ts`).all(
      from,
      to
    ) as { ts: number }[]
  ).map((r) => r.ts)

  if (stamps.length === 0) {
    return { dayId, total: 0, hourCounts: new Array<number>(24).fill(0), sampled: [] }
  }

  const step = sampleStep(stamps.length, target)
  // The modulo is applied to a row number over the day's own ordering, so the
  // sample is stable for a given day rather than depending on rowid gaps left
  // by retention deleting frames.
  const rows = cachedStmt(
    db,
    `SELECT id, ts, app, window_title, path FROM (
       SELECT id, ts, app, window_title, path,
              ROW_NUMBER() OVER (ORDER BY ts) - 1 AS n
         FROM rewind_frames WHERE ts >= ? AND ts < ?
     ) WHERE n % ? = 0 ORDER BY ts`
  ).all(from, to, step) as FrameRow[]

  return {
    dayId,
    total: stamps.length,
    hourCounts: bucketByLocalHour(stamps),
    sampled: rows.map(toMoment)
  }
}

/** The local days that hold any capture at all, newest first. */
export function screenDaysWithCapture(db: ScreenIndexDb, limit = 30): number[] {
  const bounds = cachedStmt(
    db,
    `SELECT MIN(ts) AS min, MAX(ts) AS max FROM rewind_frames`
  ).get() as { min: number | null; max: number | null } | undefined
  if (!bounds || bounds.min === null || bounds.max === null) return []

  const days: number[] = []
  let cursor = startOfLocalDay(bounds.max)
  const earliest = startOfLocalDay(bounds.min)
  // Walked one calendar day at a time rather than by a fixed 86.4e6 step, so a
  // DST transition cannot skip or repeat a day.
  while (cursor >= earliest && days.length < limit) {
    days.push(cursor)
    const d = new Date(cursor)
    cursor = new Date(d.getFullYear(), d.getMonth(), d.getDate() - 1).getTime()
  }
  return days
}
