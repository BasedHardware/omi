// The persistence layer: the session-epoch write guard (a memory formed under a
// departed session is never written), and the /v3/memories dual-write body shape.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MemoryToPersist } from './persist'

const h = vi.hoisted(() => ({
  epoch: 5,
  getSessionEpoch: vi.fn(() => h.epoch),
  getBackendSession: vi.fn(() => ({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })),
  getAbortSignal: vi.fn(() => undefined),
  insertMemory: vi.fn(() => 42),
  markMemorySynced: vi.fn(),
  fetch: vi.fn()
}))

vi.mock('../core/session', () => ({
  getSessionEpoch: h.getSessionEpoch,
  getBackendSession: h.getBackendSession,
  getAbortSignal: h.getAbortSignal
}))
vi.mock('../../ipc/db', () => ({
  insertMemory: h.insertMemory,
  markMemorySynced: h.markMemorySynced
}))
vi.mock('electron', () => ({ net: { fetch: h.fetch } }))

import { persistMemory } from './persist'

const mem: MemoryToPersist = {
  content: 'User works at Acme Corp',
  category: 'system',
  sourceApp: 'Slack',
  contextSummary: 'Viewing a Slack workspace',
  windowTitle: 'Acme — general',
  confidence: 0.9,
  screenshotId: 7,
  createdAt: 1000
}

beforeEach(() => {
  h.epoch = 5
  vi.clearAllMocks()
  h.getSessionEpoch.mockImplementation(() => h.epoch)
  h.insertMemory.mockReturnValue(42)
  h.getBackendSession.mockReturnValue({
    apiBase: 'https://api',
    desktopApiBase: 'https://d',
    token: 't'
  })
  h.fetch.mockResolvedValue({ ok: true, json: async () => ({ id: 'mem-1' }) })
})

afterEach(() => vi.restoreAllMocks())

describe('persistMemory — epoch guard', () => {
  it('writes the row when the epoch still matches the one pinned before extraction', () => {
    const id = persistMemory(mem, 5)
    expect(id).toBe(42)
    expect(h.insertMemory).toHaveBeenCalledTimes(1)
  })

  it('drops the memory (no row, returns null) when the session changed mid-analysis', () => {
    h.epoch = 6 // the memory was formed under epoch 5; the session has advanced.
    const id = persistMemory(mem, 5)
    expect(id).toBeNull()
    expect(h.insertMemory).not.toHaveBeenCalled()
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('inserts the local row with the frame provenance and unsynced flag', () => {
    persistMemory(mem, 5)
    expect(h.insertMemory).toHaveBeenCalledWith(
      expect.objectContaining({
        content: 'User works at Acme Corp',
        category: 'system',
        sourceApp: 'Slack',
        windowTitle: 'Acme — general',
        contextSummary: 'Viewing a Slack workspace',
        confidence: 0.9,
        screenshotId: 7,
        backendSynced: false,
        createdAt: 1000
      })
    )
  })
})

describe('persistMemory — backend dual-write', () => {
  it('POSTs /v3/memories with the exact body shape (source:desktop, NO window_title)', () => {
    persistMemory(mem, 5)
    const [url, opts] = h.fetch.mock.calls[0]
    expect(url).toBe('https://api/v3/memories')
    const body = JSON.parse(opts.body)
    expect(body).toEqual({
      content: 'User works at Acme Corp',
      visibility: 'private',
      category: 'system',
      confidence: 0.9,
      source_app: 'Slack',
      context_summary: 'Viewing a Slack workspace',
      source: 'desktop'
    })
  })

  it('marks the row synced with the returned memory id', async () => {
    persistMemory(mem, 5)
    await vi.waitFor(() => expect(h.markMemorySynced).toHaveBeenCalledWith(42, 'mem-1'))
  })

  it('does NOT mark synced if the session changed while the POST was in flight', async () => {
    let resolveFetch!: (v: unknown) => void
    h.fetch.mockReturnValue(new Promise((res) => (resolveFetch = res)))
    persistMemory(mem, 5)
    h.epoch = 6 // session advances mid-POST
    resolveFetch({ ok: true, json: async () => ({ id: 'mem-1' }) })
    await new Promise((r) => setTimeout(r, 0))
    expect(h.markMemorySynced).not.toHaveBeenCalled()
  })

  it('keeps the local row on a sync HTTP failure (fail-open, never loses it)', async () => {
    h.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    const id = persistMemory(mem, 5)
    expect(id).toBe(42) // row still written
    await new Promise((r) => setTimeout(r, 0))
    expect(h.markMemorySynced).not.toHaveBeenCalled()
  })

  it('never sends window_title to the backend (privacy — raw titles are PII)', () => {
    persistMemory(mem, 5)
    const body = JSON.parse(h.fetch.mock.calls[0][1].body)
    expect('window_title' in body).toBe(false)
    // …but the title IS still mirrored into the local memories table.
    expect(h.insertMemory).toHaveBeenCalledWith(
      expect.objectContaining({ windowTitle: 'Acme — general' })
    )
  })
})
