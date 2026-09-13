// Proven against a REAL SQLite database via node:sqlite — better-sqlite3 here is
// built for Electron's ABI and won't load under plain-node vitest.
//
// Timestamps are built with the LOCAL Date constructor so the local-hour
// bucketing under test is deterministic in whatever timezone the runner uses.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import {
  SCREEN_SAMPLE_TARGET,
  bucketByLocalHour,
  endOfLocalDay,
  projectScreenDay,
  sampleStep,
  screenDaysWithCapture,
  startOfLocalDay,
  type ScreenIndexDb
} from './screenIndex'

/** Copied from db.ts's bootstrap block. */
const REWIND_SCHEMA = `
  CREATE TABLE IF NOT EXISTS rewind_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    path TEXT NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    indexed INTEGER NOT NULL DEFAULT 0
  );
  CREATE INDEX IF NOT EXISTS idx_rewind_frames_ts ON rewind_frames(ts);
`

const at = (day: number, hour: number, minute = 0): number =>
  new Date(2026, 7, day, hour, minute, 0, 0).getTime()

const DAY_15 = startOfLocalDay(at(15, 12))

const open = (): ScreenIndexDb => {
  const db = new DatabaseSync(':memory:')
  db.exec(REWIND_SCHEMA)
  return db as unknown as ScreenIndexDb
}

const addFrame = (
  db: ScreenIndexDb,
  ts: number,
  over: { app?: string; title?: string; path?: string } = {}
): void => {
  db.prepare(`INSERT INTO rewind_frames (ts, path, app, window_title) VALUES (?, ?, ?, ?)`).all(
    ts,
    over.path ?? 'C:/frames/f.jpg',
    over.app ?? 'Chrome',
    over.title ?? 'Docs'
  )
}

describe('bucketByLocalHour', () => {
  it('counts into the local hour, not UTC', () => {
    const counts = bucketByLocalHour([at(15, 9), at(15, 9, 30), at(15, 14)])
    expect(counts[9]).toBe(2)
    expect(counts[14]).toBe(1)
    expect(counts.reduce((a, b) => a + b, 0)).toBe(3)
  })

  it('always returns 24 buckets', () => {
    expect(bucketByLocalHour([]).length).toBe(24)
  })
})

describe('endOfLocalDay', () => {
  it('ends one calendar day later, not 24 hours later', () => {
    const end = endOfLocalDay(DAY_15)
    const d = new Date(end)
    expect([d.getHours(), d.getMinutes()]).toEqual([0, 0])
    expect(d.getDate()).toBe(16)
  })

  it('lands on local midnight for every day of a year', () => {
    // Adding a fixed 86_400_000 lands an hour early or late on the two DST
    // transition days, dropping or double-counting the frames in that hour. In a
    // timezone that observes DST this loop fails for the fixed-constant version;
    // in UTC (which CI uses) no day transitions, so this asserts the property
    // holds everywhere it can be observed rather than proving the DST case.
    for (let i = 0; i < 365; i += 1) {
      const day = startOfLocalDay(new Date(2026, 0, 1 + i, 12).getTime())
      const end = new Date(endOfLocalDay(day))
      expect([end.getHours(), end.getMinutes(), end.getSeconds()]).toEqual([0, 0, 0])
    }
  })
})

describe('sampleStep', () => {
  it('takes every row when the day is under the target', () => {
    expect(sampleStep(50, 240)).toBe(1)
    expect(sampleStep(240, 240)).toBe(1)
  })

  it('steps far enough to land under the target', () => {
    expect(sampleStep(480, 240)).toBe(2)
    expect(sampleStep(1000, 240)).toBe(5)
    expect(Math.ceil(1000 / sampleStep(1000, 240))).toBeLessThanOrEqual(240)
  })
})

describe('projectScreenDay', () => {
  it('reports an exact total and an exact histogram', () => {
    const db = open()
    addFrame(db, at(15, 9))
    addFrame(db, at(15, 9, 30))
    addFrame(db, at(15, 21))
    // A frame on the next day must not leak into this one.
    addFrame(db, at(16, 9))

    const p = projectScreenDay(db, DAY_15)
    expect(p.total).toBe(3)
    expect(p.hourCounts[9]).toBe(2)
    expect(p.hourCounts[21]).toBe(1)
    expect(p.sampled.length).toBe(3)
  })

  it('returns a read-but-empty projection for a day with no capture', () => {
    const db = open()
    addFrame(db, at(16, 9))
    const p = projectScreenDay(db, DAY_15)
    // Zeroed, not absent: "read, and there was nothing" is a real answer and is
    // what lets the rail show 0 rather than "counting".
    expect(p).toEqual({
      dayId: DAY_15,
      total: 0,
      hourCounts: new Array<number>(24).fill(0),
      sampled: []
    })
  })

  it('samples a busy day down while still counting all of it', () => {
    const db = open()
    for (let i = 0; i < 600; i += 1) addFrame(db, at(15, 8) + i * 60_000)

    const p = projectScreenDay(db, DAY_15, 100)
    expect(p.total).toBe(600)
    expect(p.sampled.length).toBeLessThanOrEqual(100)
    expect(p.sampled.length).toBeGreaterThan(0)
    // The histogram is built from every timestamp, not the sample, so a busy
    // hour still reads as busy.
    expect(p.hourCounts.reduce((a, b) => a + b, 0)).toBe(600)
  })

  it('spreads the sample across the day instead of clustering it', () => {
    const db = open()
    for (let i = 0; i < 600; i += 1) addFrame(db, at(15, 8) + i * 60_000)

    const p = projectScreenDay(db, DAY_15, 100)
    const first = p.sampled[0].timestamp
    const last = p.sampled[p.sampled.length - 1].timestamp
    // A sample taken only from the start of the day would make the afternoon
    // look like it never happened.
    expect(last - first).toBeGreaterThan(500 * 60_000)
  })

  it('keeps sampling stable when retention has deleted earlier frames', () => {
    const db = open()
    for (let i = 0; i < 300; i += 1) addFrame(db, at(15, 8) + i * 60_000)
    const before = projectScreenDay(db, DAY_15, 50).sampled.map((m) => m.timestamp)
    // Retention deletes a chunk from an EARLIER day, leaving a rowid gap.
    db.prepare('DELETE FROM rewind_frames WHERE id <= 0').all()
    const after = projectScreenDay(db, DAY_15, 50).sampled.map((m) => m.timestamp)
    // Sampling on a row number over the day's own ordering, rather than on
    // rowid, is what keeps this stable.
    expect(after).toEqual(before)
  })

  it('carries the fields a strip renders and nothing more', () => {
    const db = open()
    addFrame(db, at(15, 9), { app: 'Excel', title: 'Q3 Plan', path: 'C:/frames/9.jpg' })
    const [m] = projectScreenDay(db, DAY_15).sampled
    expect(m).toEqual({
      id: expect.any(Number),
      timestamp: at(15, 9),
      appName: 'Excel',
      windowTitle: 'Q3 Plan',
      imagePath: 'C:/frames/9.jpg'
    })
  })

  it('reports an absent window title as null rather than an empty string', () => {
    const db = open()
    addFrame(db, at(15, 9), { title: '' })
    // The row falls back to the app name, which it can only do if the absence
    // is distinguishable.
    expect(projectScreenDay(db, DAY_15).sampled[0].windowTitle).toBeNull()
  })

  it('uses a default sample target when none is given', () => {
    expect(SCREEN_SAMPLE_TARGET).toBe(240)
  })
})

describe('screenDaysWithCapture', () => {
  it('lists the days holding capture, newest first', () => {
    const db = open()
    addFrame(db, at(13, 9))
    addFrame(db, at(15, 9))
    expect(screenDaysWithCapture(db)).toEqual([
      startOfLocalDay(at(15, 9)),
      startOfLocalDay(at(14, 9)),
      startOfLocalDay(at(13, 9))
    ])
  })

  it('returns nothing when there is no capture at all', () => {
    expect(screenDaysWithCapture(open())).toEqual([])
  })

  it('stops at the limit rather than walking the whole history', () => {
    const db = open()
    addFrame(db, at(1, 9))
    addFrame(db, at(28, 9))
    expect(screenDaysWithCapture(db, 5).length).toBe(5)
  })
})
