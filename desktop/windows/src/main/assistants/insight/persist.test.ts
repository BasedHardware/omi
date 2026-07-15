// The persistence layer: the session-epoch write guard (an insight formed under a
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
  insertInsight: vi.fn(() => 42),
  fetch: vi.fn()
}))

vi.mock('../core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession,
  getAbortSignal: h.getAbortSignal
}))
vi.mock('../../ipc/db', () => ({ insertInsight: h.insertInsight }))
vi.mock('electron', () => ({ net: { fetch: h.fetch } }))

import { persistInsight, toPayload } from './persist'
import type { ExtractedInsight } from './models'

const insight: ExtractedInsight = {
  advice: 'Mask the token before sharing',
  headline: 'Token visible',
  reasoning: 'A live token is on screen',
  category: 'productivity',
  sourceApp: 'Terminal',
  confidence: 0.92,
  contextSummary: 'ctx',
  currentActivity: 'act'
}

beforeEach(() => {
  h.epoch = 5
  vi.clearAllMocks()
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.insertInsight.mockReturnValue(42)
  h.getBackendSession.mockReturnValue({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })
  h.fetch.mockResolvedValue({ ok: true, json: async () => ({ id: 'mem-1' }) })
})

afterEach(() => vi.restoreAllMocks())

describe('toPayload', () => {
  it('prefers the headline for the toast, falls back to advice', () => {
    expect(toPayload(insight).headline).toBe('Token visible')
    expect(toPayload({ ...insight, headline: null }).headline).toBe('Mask the token before sharing')
    expect(toPayload({ ...insight, reasoning: null }).reasoning).toBe('')
  })
})

describe('persistInsight — epoch guard', () => {
  it('writes the row when the epoch still matches the one pinned before the pipeline', () => {
    expect(persistInsight(insight, 5)).toBe(42)
    expect(h.insertInsight).toHaveBeenCalledTimes(1)
  })

  it('drops the insight (no row, returns null, no POST) when the session changed mid-pipeline', () => {
    h.epoch = 6 // formed under 5, session advanced to 6
    expect(persistInsight(insight, 5)).toBeNull()
    expect(h.insertInsight).not.toHaveBeenCalled()
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('dual-writes to /v3/memories with Mac tags/category', () => {
    persistInsight(insight, 5)
    const [url, opts] = h.fetch.mock.calls[0]
    expect(url).toBe('https://api/v3/memories')
    const body = JSON.parse(opts.body)
    expect(body.content).toBe('Mask the token before sharing')
    expect(body.category).toBe('interesting')
    expect(body.tags).toEqual(['tips', 'productivity'])
  })

  it('does NOT POST if the session changed after the local write but before the sync', () => {
    // local insert runs at epoch 5; the sync re-checks and must bail when it moved.
    h.getSessionEpoch.mockReturnValueOnce(5) // persist guard
    h.getSessionEpoch.mockReturnValue(6) // sync guard sees the new session
    persistInsight(insight, 5)
    expect(h.insertInsight).toHaveBeenCalledTimes(1)
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('keeps the local row on a sync HTTP failure (fail-open)', async () => {
    h.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    expect(persistInsight(insight, 5)).toBe(42)
    await new Promise((r) => setTimeout(r, 0))
  })
})
