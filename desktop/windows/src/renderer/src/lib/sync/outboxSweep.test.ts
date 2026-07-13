// @vitest-environment jsdom
// The outbox sweep must retry unsynced conversations on a 60s timer from launch —
// WITHOUT the Conversations page ever mounting (the wedged-PTT-user bug). Uses
// fake timers; conversationSync is mocked so no real backend/DB is touched.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ retryUnsyncedConversations: vi.fn(async () => false) }))
vi.mock('./conversationSync', () => ({ retryUnsyncedConversations: h.retryUnsyncedConversations }))

import { startOutboxSweep, stopOutboxSweep } from './outboxSweep'

const listLocalConversations = vi.fn(async () => [])

beforeEach(() => {
  vi.useFakeTimers()
  h.retryUnsyncedConversations.mockClear()
  listLocalConversations.mockClear()
  ;(globalThis as { window: { omi: unknown } }).window.omi = { listLocalConversations }
})
afterEach(() => {
  stopOutboxSweep()
  vi.useRealTimers()
})

describe('outbox background sweep', () => {
  it('runs one pass immediately, then every 60s, with no page mount', async () => {
    startOutboxSweep()
    await vi.advanceTimersByTimeAsync(0) // let the immediate pass settle
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(3)
  })

  it('stops firing after stopOutboxSweep (sign-out)', async () => {
    startOutboxSweep()
    await vi.advanceTimersByTimeAsync(0)
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(1)

    stopOutboxSweep()
    await vi.advanceTimersByTimeAsync(180_000)
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(1) // no further passes
  })

  it('is idempotent — a second start does not add a second timer', async () => {
    startOutboxSweep()
    startOutboxSweep()
    await vi.advanceTimersByTimeAsync(0)
    // Two immediate passes would mean two timers; there must be exactly one.
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(h.retryUnsyncedConversations).toHaveBeenCalledTimes(2)
  })
})
