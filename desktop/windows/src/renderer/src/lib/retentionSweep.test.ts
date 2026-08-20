// @vitest-environment jsdom
// The retention sweep's REQUEST-VOLUME contract. `retentionMode` is optional and
// falls back to 'dry-run', and a dry-run pass ends at a console.log — so before the
// trigger split, every default install ran a full `/v3/memories` page-through plus a
// 200-conversation fetch every 30 minutes, forever, and threw all of it away. These
// cases pin who is allowed to spend a request: the background timer only in 'live',
// the user's Preview button in 'dry-run'.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  get: vi.fn(),
  del: vi.fn(),
  fetchAllMemories: vi.fn(),
  deleteMemoriesPaced: vi.fn(),
  getPreferences: vi.fn(),
  invalidateConversationsCache: vi.fn()
}))

vi.mock('./apiClient', () => ({ omiApi: { get: h.get, delete: h.del } }))
vi.mock('./memoriesBulk', () => ({
  fetchAllMemories: h.fetchAllMemories,
  deleteMemoriesPaced: h.deleteMemoriesPaced
}))
vi.mock('./preferences', () => ({ getPreferences: h.getPreferences }))
vi.mock('./pageCache', () => ({ invalidateConversationsCache: h.invalidateConversationsCache }))

import { maybeStartRetentionSweep, runRetentionSweep } from './retentionSweep'

const listLocalConversations = vi.fn()

/** Every backend call the sweep can make, from either of its two fetch paths. */
const backendCalls = (): number => h.get.mock.calls.length + h.fetchAllMemories.mock.calls.length

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  listLocalConversations.mockResolvedValue([])
  ;(globalThis as unknown as { window: Record<string, unknown> }).window.omi = {
    listLocalConversations,
    deleteLocalConversation: vi.fn(async () => {})
  }
  h.get.mockResolvedValue({ data: [] })
  h.fetchAllMemories.mockResolvedValue([])
  h.deleteMemoriesPaced.mockResolvedValue({ deleted: 0, failed: 0 })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('scheduled passes', () => {
  it('spends nothing on a default install, where retentionMode is unset', async () => {
    // The exact production default: the key is absent from preferences entirely.
    h.getPreferences.mockReturnValue({})
    await runRetentionSweep('scheduled')
    expect(backendCalls()).toBe(0)
  })

  it('spends nothing when the user has explicitly chosen Preview', async () => {
    h.getPreferences.mockReturnValue({ retentionMode: 'dry-run' })
    await runRetentionSweep('scheduled')
    expect(backendCalls()).toBe(0)
  })

  it('spends nothing when retention is off', async () => {
    h.getPreferences.mockReturnValue({ retentionMode: 'off' })
    await runRetentionSweep('scheduled')
    expect(backendCalls()).toBe(0)
  })

  it('still runs in live mode, which is the mode that deletes something', async () => {
    h.getPreferences.mockReturnValue({ retentionMode: 'live' })
    await runRetentionSweep('scheduled')
    expect(h.fetchAllMemories).toHaveBeenCalledTimes(1)
    expect(h.get).toHaveBeenCalledWith('/v1/conversations', expect.anything())
  })
})

describe('manual passes', () => {
  it('runs the Preview the user just asked for', async () => {
    // Pressing Preview in Settings is the trigger that makes the mode's advertised
    // "logs what it would delete" true, so this path must still do the work.
    h.getPreferences.mockReturnValue({ retentionMode: 'dry-run' })
    await runRetentionSweep('manual')
    expect(h.fetchAllMemories).toHaveBeenCalledTimes(1)
    expect(h.get).toHaveBeenCalledWith('/v1/conversations', expect.anything())
  })

  it('still respects off — the one mode that means do nothing', async () => {
    h.getPreferences.mockReturnValue({ retentionMode: 'off' })
    await runRetentionSweep('manual')
    expect(backendCalls()).toBe(0)
  })
})

// Kept last on purpose: `started` is a module-level latch with no reset seam, so
// maybeStartRetentionSweep can only be exercised once per module instance.
describe('the scheduler wiring', () => {
  it('costs a default install nothing for the first two hours of uptime', async () => {
    // The guard above only helps if the scheduler keeps passing 'scheduled'. This is
    // the end-to-end version of that: launch the real timers on a default install and
    // let four sweep windows go by.
    vi.useFakeTimers()
    try {
      h.getPreferences.mockReturnValue({})
      maybeStartRetentionSweep()
      await vi.advanceTimersByTimeAsync(8_000) // the deferred startup pass
      expect(backendCalls()).toBe(0)
      await vi.advanceTimersByTimeAsync(2 * 60 * 60 * 1000) // 4 x 30-minute windows
      expect(backendCalls()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })
})
