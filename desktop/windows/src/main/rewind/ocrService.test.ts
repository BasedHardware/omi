// The backlog sweep's idle-burn gate: it must NOT hit the DB every 4s when there
// is nothing to OCR, and it must reliably wake when capture leaves a frame
// un-OCR'd. Every impure edge (DB, OCR helper, persistence, filesystem) is mocked,
// so this runs with no native binding.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const unindexedRewindFrames = vi.fn<(limit: number) => unknown[]>(() => [])
vi.mock('../ipc/db', () => ({ unindexedRewindFrames: (n: number) => unindexedRewindFrames(n) }))
vi.mock('../ocr/helperProcess', () => ({
  helperProcess: { ocr: vi.fn(async () => ({ ok: true, fullText: 'x', lines: [] })) }
}))
vi.mock('./ocrPersist', () => ({ persistFrameOcr: vi.fn() }))
vi.mock('fs', () => ({ readFileSync: vi.fn(() => Buffer.from('jpeg')) }))

import { signalRewindOcrPending, __rewindOcrTestHooks } from './ocrService'

const { backfill, setPending, getPending } = __rewindOcrTestHooks

function frames(n: number): { id: number; imagePath: string; app: string; windowTitle: string }[] {
  return Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    imagePath: `/f/${i}.jpg`,
    app: 'App',
    windowTitle: 'w'
  }))
}

beforeEach(() => {
  unindexedRewindFrames.mockReset().mockReturnValue([])
  setPending(false)
})

describe('OCR backlog sweep — idle gate', () => {
  it('skips the DB read entirely when nothing is pending', async () => {
    await backfill()
    expect(unindexedRewindFrames).not.toHaveBeenCalled()
  })

  it('reads once when pending, then re-gates after draining a short page', async () => {
    signalRewindOcrPending()
    expect(getPending()).toBe(true)

    unindexedRewindFrames.mockReturnValue(frames(2)) // short page (< BATCH of 5) → drained
    await backfill()
    expect(unindexedRewindFrames).toHaveBeenCalledTimes(1)
    expect(getPending()).toBe(false) // nothing left → gated again

    await backfill()
    expect(unindexedRewindFrames).toHaveBeenCalledTimes(1) // still gated, no second read
  })

  it('keeps sweeping while a full page suggests more remain', async () => {
    signalRewindOcrPending()
    unindexedRewindFrames.mockReturnValue(frames(5)) // full BATCH → more may remain
    await backfill()
    expect(getPending()).toBe(true) // stays armed for the next tick

    await backfill()
    expect(unindexedRewindFrames).toHaveBeenCalledTimes(2)
  })

  it('a signal arriving during a sweep re-arms the gate (work is never lost)', async () => {
    signalRewindOcrPending()
    // The DB read fires a fresh capture signal mid-sweep (as the hot path would).
    unindexedRewindFrames.mockImplementation(() => {
      signalRewindOcrPending()
      return frames(1) // short page — would normally clear the gate
    })
    await backfill()
    expect(getPending()).toBe(true) // the mid-sweep signal kept it armed
  })
})
