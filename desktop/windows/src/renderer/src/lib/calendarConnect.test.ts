import { describe, it, expect, vi } from 'vitest'
import { pollUntilConnected } from './calendarConnect'

// Fake sleep so the poll runs synchronously (no real timers). Reused by the
// Calendar connect flow and the X connector's phase-1 poll.
const noSleep = (): Promise<void> => Promise.resolve()

describe('pollUntilConnected', () => {
  it('resolves true once the status reports connected', async () => {
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce({ connected: false })
      .mockResolvedValueOnce({ connected: true })
    const ok = await pollUntilConnected(getStatus, {
      intervalMs: 1,
      maxAttempts: 10,
      sleep: noSleep
    })
    expect(ok).toBe(true)
    expect(getStatus).toHaveBeenCalledTimes(2)
  })

  it('resolves false after exhausting maxAttempts (timeout)', async () => {
    const getStatus = vi.fn().mockResolvedValue({ connected: false })
    const ok = await pollUntilConnected(getStatus, {
      intervalMs: 1,
      maxAttempts: 3,
      sleep: noSleep
    })
    expect(ok).toBe(false)
    expect(getStatus).toHaveBeenCalledTimes(3)
  })

  it('keeps polling through a transient status error', async () => {
    const getStatus = vi
      .fn()
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValueOnce({ connected: true })
    const ok = await pollUntilConnected(getStatus, {
      intervalMs: 1,
      maxAttempts: 5,
      sleep: noSleep
    })
    expect(ok).toBe(true)
    expect(getStatus).toHaveBeenCalledTimes(2)
  })

  it('stops immediately when canceled, without polling', async () => {
    const getStatus = vi.fn().mockResolvedValue({ connected: true })
    const ok = await pollUntilConnected(getStatus, {
      intervalMs: 1,
      maxAttempts: 5,
      sleep: noSleep,
      canceled: () => true
    })
    expect(ok).toBe(false)
    expect(getStatus).not.toHaveBeenCalled()
  })
})
