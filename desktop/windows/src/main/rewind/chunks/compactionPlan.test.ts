// Grouping is where compaction decides which JPEGs stop existing, so each rule
// is pinned against the reason it exists rather than against a golden shape.
import { describe, expect, it } from 'vitest'
import {
  CHUNK_WINDOW_MS,
  COMPACTION_MIN_AGE_MS,
  MIN_FRAMES_PER_CHUNK,
  localDayKey,
  plannedJpegBytes,
  planChunks,
  type CompactableFrame
} from './compactionPlan'

const NOW = new Date('2026-08-17T18:00:00').getTime()
/**
 * Comfortably older than the compaction delay, with enough headroom that a case
 * can offset hours forward and still be old enough to compact. (Set an hour
 * back originally, which silently made the "far apart in time" case land in the
 * future and get age-filtered away rather than grouped.)
 */
const BASE = NOW - 24 * 60 * 60_000

function run(
  count: number,
  opts: Partial<CompactableFrame> & { startMs?: number; stepMs?: number } = {}
) {
  const step = opts.stepMs ?? 1000
  const start = opts.startMs ?? BASE
  return Array.from({ length: count }, (_, i) => ({
    id: (opts.id ?? 1000) + i,
    tsMs: start + i * step,
    width: opts.width ?? 1280,
    height: opts.height ?? 720,
    imagePath: `C:/rewind/day/${start + i * step}.jpg`
  }))
}

describe('grouping frames into chunks', () => {
  it('packs a one-per-second minute into a single chunk', () => {
    const plan = planChunks(run(45), NOW)
    expect(plan).toHaveLength(1)
    expect(plan[0].frames).toHaveLength(45)
    expect(plan[0].width).toBe(1280)
    expect(plan[0].height).toBe(720)
  })

  it('gives each frame the offset it will be addressed by', () => {
    // The array index IS the stored chunk_offset, so order is not cosmetic.
    const plan = planChunks(run(20), NOW)
    const tsInOrder = plan[0].frames.map((f) => f.tsMs)
    expect(tsInOrder).toEqual([...tsInOrder].sort((a, b) => a - b))
  })

  it('sorts frames the caller handed over out of order', () => {
    // Offsets are positions in the returned array. One out-of-order frame would
    // mis-address every frame after it, and nothing downstream could detect it.
    const ordered = run(12)
    const shuffled = [ordered[5], ordered[0], ...ordered.slice(6), ...ordered.slice(1, 5)]
    const plan = planChunks(shuffled, NOW)
    expect(plan[0].frames.map((f) => f.tsMs)).toEqual(ordered.map((f) => f.tsMs))
  })

  it('breaks a chunk once it spans more than the window', () => {
    const frames = run(90) // 90 seconds at one per second
    const plan = planChunks(frames, NOW)
    expect(plan.length).toBeGreaterThan(1)
    for (const chunk of plan) {
      const span = chunk.frames[chunk.frames.length - 1].tsMs - chunk.frames[0].tsMs
      expect(span).toBeLessThanOrEqual(CHUNK_WINDOW_MS)
    }
  })

  it('breaks a chunk when the screen geometry changes', () => {
    // A video track has exactly one size; a chunk cannot hold two.
    const first = run(12)
    const second = run(12, { id: 5000, startMs: BASE + 12_000, width: 2560, height: 1440 })
    const plan = planChunks([...first, ...second], NOW)
    expect(plan).toHaveLength(2)
    expect(plan[0].width).toBe(1280)
    expect(plan[1].width).toBe(2560)
  })

  it('never lets a chunk span two local days', () => {
    // Chunks are filed in a day directory and retention deletes by day.
    const beforeMidnight = new Date('2026-08-16T23:59:50').getTime()
    const frames = run(20, { startMs: beforeMidnight })
    const plan = planChunks(frames, new Date('2026-08-18T12:00:00').getTime())
    for (const chunk of plan) {
      const days = new Set(chunk.frames.map((f) => localDayKey(f.tsMs)))
      expect(days.size).toBe(1)
      expect(chunk.day).toBe(localDayKey(chunk.frames[0].tsMs))
    }
  })

  it('separates runs that are far apart in time', () => {
    const morning = run(15)
    const evening = run(15, { id: 9000, startMs: BASE + 6 * 60 * 60_000 })
    const plan = planChunks([...morning, ...evening], NOW)
    expect(plan).toHaveLength(2)
  })
})

describe('what is left alone', () => {
  it('pins the floor at 8 frames', () => {
    // A literal, because the cases below size their fixtures from it. Deriving
    // those sizes from the constant instead made them unable to fail: lowering
    // the floor to 1 also shrank every fixture, so a mutation audit walked
    // straight past it. The value itself is the measured one (a 5-frame run
    // reached only 2.4x against a 60-frame run's 51x).
    expect(MIN_FRAMES_PER_CHUNK).toBe(8)
  })

  it('drops runs shorter than the floor instead of merging them', () => {
    // Merging distant short runs is exactly the case where inter-frame
    // compression has nothing to work with.
    const a = run(7)
    const b = run(7, { id: 7000, startMs: BASE + 10 * 60_000 })
    expect(planChunks([...a, ...b], NOW)).toHaveLength(0)
  })

  it('keeps a run exactly at the floor', () => {
    expect(planChunks(run(8), NOW)).toHaveLength(1)
  })

  it('leaves frames younger than the compaction delay alone', () => {
    const fresh = run(40, { startMs: NOW - 60_000 })
    expect(planChunks(fresh, NOW)).toHaveLength(0)
  })

  it('does not let a fresh frame extend a chunk of older ones', () => {
    // The age filter runs before grouping, so a frame inside the delay cannot
    // be swept in by a neighbour that is old enough.
    const old = run(20, { startMs: NOW - COMPACTION_MIN_AGE_MS - 20_000 })
    const plan = planChunks(old, NOW)
    const youngest = Math.max(...plan.flatMap((c) => c.frames.map((f) => f.tsMs)))
    expect(NOW - youngest).toBeGreaterThanOrEqual(COMPACTION_MIN_AGE_MS)
  })

  it('skips frames with no recorded geometry', () => {
    // There is no honest video track size for a row that never stored one.
    const frames = run(20).map((f, i) => (i === 10 ? { ...f, width: 0, height: 0 } : f))
    const plan = planChunks(frames, NOW)
    expect(plan.flatMap((c) => c.frames).some((f) => f.width === 0)).toBe(false)
  })

  it('breaks the chunk at a frame with no geometry rather than skipping over it', () => {
    // Offsets must stay contiguous with capture order; silently omitting a
    // middle frame would leave the two halves adjacent in one chunk.
    const frames = run(30).map((f, i) => (i === 15 ? { ...f, width: 0, height: 0 } : f))
    const plan = planChunks(frames, NOW)
    expect(plan.length).toBe(2)
    expect(plan[0].frames).toHaveLength(15)
    expect(plan[1].frames).toHaveLength(14)
  })
})

describe('reporting', () => {
  it('sums the JPEG bytes a plan would reclaim', () => {
    const plan = planChunks(run(20), NOW)
    expect(plannedJpegBytes(plan, () => 64_000)).toBe(20 * 64_000)
  })

  it('reports nothing for an empty plan', () => {
    expect(plannedJpegBytes([], () => 1)).toBe(0)
  })
})

describe('local day keys', () => {
  it('uses local midnight, not UTC', () => {
    // A UTC-derived key would file evening frames under tomorrow for anyone
    // west of Greenwich, splitting a day's chunks across two directories.
    const evening = new Date(2026, 7, 17, 23, 30, 0).getTime()
    expect(localDayKey(evening)).toBe('2026-08-17')
  })

  it('zero-pads month and day', () => {
    expect(localDayKey(new Date(2026, 0, 5, 12, 0, 0).getTime())).toBe('2026-01-05')
  })
})
