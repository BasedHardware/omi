// Proof that the real day-sampling step math + SQL (rewindSampleSql.ts) select the
// macOS getScreenshotsSampled contract against a REAL SQLite index. db.ts's
// better-sqlite3 can't load under plain-node vitest (Electron ABI), so — same
// pattern as rewindFtsSearch/rewindEmbeddingSql tests — the DDL is replicated and
// driven via node:sqlite while the REAL step function + REAL SQL run.
import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { REWIND_DAY_COUNT_SQL, buildRewindSampledSql, rewindSampleStep } from './rewindSampleSql'

// The projection db.ts's REWIND_COLUMNS uses (only id/ts matter for these assertions).
const COLUMNS = 'id, ts, app'

function db(): DatabaseSync {
  const d = new DatabaseSync(':memory:')
  d.exec(`CREATE TABLE rewind_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    app TEXT NOT NULL DEFAULT ''
  );
  CREATE INDEX idx_rewind_frames_ts ON rewind_frames(ts);`)
  return d
}

function seed(d: DatabaseSync, count: number, base = 1_000): number[] {
  const ins = d.prepare('INSERT INTO rewind_frames (ts, app) VALUES (?, ?)')
  const ts: number[] = []
  for (let i = 0; i < count; i++) {
    const t = base + i * 1000
    ins.run(t, 'App')
    ts.push(t)
  }
  return ts
}

function sampled(d: DatabaseSync, from: number, to: number, target: number): number[] {
  const { n } = d.prepare(REWIND_DAY_COUNT_SQL).get(from, to) as { n: number }
  if (n <= target) {
    return (
      d
        .prepare(`SELECT ${COLUMNS} FROM rewind_frames WHERE ts BETWEEN ? AND ? ORDER BY ts`)
        .all(from, to) as { ts: number }[]
    ).map((r) => r.ts)
  }
  const step = rewindSampleStep(n, target)
  return (d.prepare(buildRewindSampledSql(COLUMNS)).all(from, to, step) as { ts: number }[]).map(
    (r) => r.ts
  )
}

describe('rewindSampleStep', () => {
  it('is 1 (take everything) when the day already fits, or target is non-positive', () => {
    expect(rewindSampleStep(10, 500)).toBe(1)
    expect(rewindSampleStep(500, 500)).toBe(1)
    expect(rewindSampleStep(1000, 0)).toBe(1)
  })
  it('is floor(total/target) for a busy day (macOS parity)', () => {
    expect(rewindSampleStep(1000, 500)).toBe(2)
    expect(rewindSampleStep(2500, 500)).toBe(5)
    expect(rewindSampleStep(1499, 500)).toBe(2)
  })
})

describe('day-sampling SQL', () => {
  it('returns every frame, oldest-first, when the count is within target', () => {
    const d = db()
    const ts = seed(d, 5)
    expect(sampled(d, 0, 1e12, 500)).toEqual(ts)
    d.close()
  })

  it('down-samples a busy day to ~target evenly-spaced frames, oldest-first', () => {
    const d = db()
    const ts = seed(d, 1000) // step = 2
    const out = sampled(d, 0, 1e12, 500)
    expect(out.length).toBe(500)
    // Every Nth by timestamp position: indices 0, 2, 4, … — evenly spaced, not the
    // newest/oldest 500.
    expect(out[0]).toBe(ts[0])
    expect(out[1]).toBe(ts[2])
    expect(out[2]).toBe(ts[4])
    expect(out[out.length - 1]).toBe(ts[998])
    // Strictly ascending (oldest-first).
    for (let i = 1; i < out.length; i++) expect(out[i]).toBeGreaterThan(out[i - 1])
    d.close()
  })

  it('honours the day window — frames outside [from,to] are never sampled', () => {
    const d = db()
    seed(d, 100, 1000) // ts 1000..100000
    // A window covering only the first 40 frames, target 10 → step 4 → ~10 frames.
    const from = 1000
    const to = 1000 + 39 * 1000
    const out = sampled(d, from, to, 10)
    expect(out.every((t) => t >= from && t <= to)).toBe(true)
    expect(out.length).toBeLessThanOrEqual(11)
    d.close()
  })
})
