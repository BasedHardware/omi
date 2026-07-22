// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock only the network boundary; the real extractNoteMemories synthesis + dedup
// runs against the mocked desktop client, and the real tagged-write loop runs
// against the mocked omi client.
const { desktopPost, omiPost } = vi.hoisted(() => ({ desktopPost: vi.fn(), omiPost: vi.fn() }))
vi.mock('./apiClient', () => ({
  desktopApi: { post: desktopPost },
  omiApi: { post: omiPost }
}))

import {
  readAndExtractStickyNotes,
  importStickyMemories,
  STICKY_NOTE_TAG,
  STICKY_PROFILE_TAG
} from './stickyNotesImport'

function synthReply(obj: unknown): { data: unknown } {
  return { data: { choices: [{ message: { content: JSON.stringify(obj) } }] } }
}

function stubStickyRead(result: unknown): void {
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    readStickyNotes: vi.fn().mockResolvedValue(result)
  }
}

beforeEach(() => {
  desktopPost.mockReset()
  omiPost.mockReset()
})

describe('readAndExtractStickyNotes — resting states', () => {
  it('reports unavailable when Sticky Notes is absent', async () => {
    stubStickyRead({ available: false, notes: [] })
    expect(await readAndExtractStickyNotes([])).toEqual({ status: 'unavailable' })
  })

  it('reports the read error verbatim', async () => {
    stubStickyRead({ available: true, notes: [], error: 'db locked' })
    expect(await readAndExtractStickyNotes([])).toEqual({ status: 'error', error: 'db locked' })
  })

  it('distinguishes no-notes from no-new-memories', async () => {
    stubStickyRead({ available: true, notes: [] })
    expect(await readAndExtractStickyNotes([])).toEqual({ status: 'empty', reason: 'no-notes' })

    stubStickyRead({ available: true, notes: [{ id: '1', text: 'hi', updatedAt: 0 }] })
    desktopPost.mockResolvedValue(synthReply({ memories: [], profile: '' }))
    expect(await readAndExtractStickyNotes([])).toEqual({
      status: 'empty',
      reason: 'no-new-memories'
    })
  })

  it('returns the synthesized memories + profile on success', async () => {
    stubStickyRead({ available: true, notes: [{ id: '1', text: 'Loves hiking', updatedAt: 0 }] })
    desktopPost.mockResolvedValue(synthReply({ memories: ['Loves hiking'], profile: 'Outdoorsy.' }))
    expect(await readAndExtractStickyNotes([])).toEqual({
      status: 'ok',
      memories: ['Loves hiking'],
      profile: 'Outdoorsy.'
    })
  })
})

describe('importStickyMemories', () => {
  it('writes each memory with the note tag and the profile with the profile tag', async () => {
    omiPost.mockResolvedValue({})
    const r = await importStickyMemories(['Loves hiking', 'Has a cat'], 'A profile.')
    expect(r).toEqual({ ok: 2, failed: 0, firstError: undefined })
    expect(omiPost).toHaveBeenCalledWith('/v3/memories', {
      content: 'Loves hiking',
      tags: [STICKY_NOTE_TAG]
    })
    expect(omiPost).toHaveBeenCalledWith('/v3/memories', {
      content: 'A profile.',
      tags: [STICKY_PROFILE_TAG]
    })
  })

  it('counts failures and surfaces the first error, without letting a bad profile write fail the import', async () => {
    omiPost
      .mockRejectedValueOnce({ response: { data: { detail: 'nope' } } }) // memory 1
      .mockResolvedValueOnce({}) // memory 2
      .mockRejectedValueOnce(new Error('profile boom')) // profile (best-effort)
    const r = await importStickyMemories(['a', 'b'], 'prof')
    expect(r.ok).toBe(1)
    expect(r.failed).toBe(1)
    expect(r.firstError).toBe('nope')
  })
})
