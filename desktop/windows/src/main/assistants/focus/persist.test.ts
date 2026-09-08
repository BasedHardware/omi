// The persistence layer: the session-epoch write guard (a verdict formed under a
// departed session is never written), and the memory dual-write shape.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  epoch: 5,
  getSessionEpoch: vi.fn(() => h.epoch),
  getBackendSession: vi.fn(() => ({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })),
  getAbortSignal: vi.fn(() => undefined),
  insertFocusSession: vi.fn(() => 42),
  markFocusSessionSynced: vi.fn(),
  fetch: vi.fn()
}))

vi.mock('../core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession,
  getAbortSignal: h.getAbortSignal
}))
vi.mock('../../ipc/db', () => ({
  insertFocusSession: h.insertFocusSession,
  markFocusSessionSynced: h.markFocusSessionSynced
}))
vi.mock('electron', () => ({ net: { fetch: h.fetch } }))

import { persistFocusSession } from './persist'
import type { ScreenAnalysis } from './models'

const analysis: ScreenAnalysis = {
  status: 'distracted',
  appOrSite: 'YouTube',
  description: 'a video',
  message: 'refocus'
}
const frame = { screenshotId: '7', windowTitle: 'private title', createdAt: 1000 }

beforeEach(() => {
  h.epoch = 5
  vi.clearAllMocks()
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.insertFocusSession.mockReturnValue(42)
  h.getBackendSession.mockReturnValue({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })
  h.fetch.mockResolvedValue({ ok: true, json: async () => ({ id: 'mem-1' }) })
})

afterEach(() => vi.restoreAllMocks())

describe('persistFocusSession — epoch guard', () => {
  it('writes the row when the epoch still matches the one pinned before analysis', () => {
    const id = persistFocusSession(analysis, frame, 5)
    expect(id).toBe(42)
    expect(h.insertFocusSession).toHaveBeenCalledTimes(1)
  })

  it('drops the verdict (no row, returns null) when the session changed mid-analysis', () => {
    // The verdict was formed under epoch 5, but the session has since advanced.
    h.epoch = 6
    const id = persistFocusSession(analysis, frame, 5)
    expect(id).toBeNull()
    expect(h.insertFocusSession).not.toHaveBeenCalled()
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('stores the row with the raw window title but syncs only appOrSite (never the title)', () => {
    persistFocusSession(analysis, frame, 5)
    // Local row keeps the title (never leaves the device).
    expect(h.insertFocusSession).toHaveBeenCalledWith(
      expect.objectContaining({ windowTitle: 'private title', screenshotId: '7' })
    )
    // The synced memory body must NOT contain the window title.
    const body = JSON.parse(h.fetch.mock.calls[0][1].body)
    expect(body.content).toBe('Distracted on YouTube: a video')
    expect(JSON.stringify(body)).not.toContain('private title')
    expect(body.category).toBe('system')
    expect(body.source).toBe('desktop')
    expect(body.tags).toEqual(['focus', 'distracted', 'app:YouTube', 'has-message'])
  })
})

describe('persistFocusSession — backend sync', () => {
  it('marks the row synced with the returned memory id', async () => {
    persistFocusSession(analysis, frame, 5)
    await vi.waitFor(() => expect(h.markFocusSessionSynced).toHaveBeenCalledWith(42, 'mem-1'))
  })

  it('does NOT mark synced if the session changed while the POST was in flight', async () => {
    let resolveFetch!: (v: unknown) => void
    h.fetch.mockReturnValue(new Promise((res) => (resolveFetch = res)))
    persistFocusSession(analysis, frame, 5)
    // Session advances mid-POST.
    h.epoch = 6
    resolveFetch({ ok: true, json: async () => ({ id: 'mem-1' }) })
    // Give the microtasks a chance to run.
    await new Promise((r) => setTimeout(r, 0))
    expect(h.markFocusSessionSynced).not.toHaveBeenCalled()
  })

  it('keeps the local row on a sync HTTP failure (fail-open, never loses it)', async () => {
    h.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    const id = persistFocusSession(analysis, frame, 5)
    expect(id).toBe(42) // row still written
    await new Promise((r) => setTimeout(r, 0))
    expect(h.markFocusSessionSynced).not.toHaveBeenCalled()
  })
})
