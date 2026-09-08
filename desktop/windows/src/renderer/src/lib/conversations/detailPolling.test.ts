import { describe, it, expect } from 'vitest'
import {
  POLL_INTERVAL_MS,
  POLL_MAX_ATTEMPTS,
  isEnriching,
  isProcessing,
  shouldStopPolling
} from './detailPolling'

describe('detail polling', () => {
  it('polls 15 times, 2s apart (30s ceiling)', () => {
    expect(POLL_MAX_ATTEMPTS).toBe(15)
    expect(POLL_INTERVAL_MS).toBe(2000)
    expect(POLL_MAX_ATTEMPTS * POLL_INTERVAL_MS).toBe(30_000)
  })

  it('keeps polling while the conversation is processing', () => {
    expect(shouldStopPolling('processing', 1)).toBe(false)
    expect(shouldStopPolling('processing', 14)).toBe(false)
  })

  it('stops early as soon as the status leaves processing', () => {
    expect(shouldStopPolling('completed', 1)).toBe(true)
    expect(shouldStopPolling('failed', 3)).toBe(true)
    expect(shouldStopPolling('merging', 2)).toBe(true)
    expect(shouldStopPolling('in_progress', 2)).toBe(true)
  })

  // Without an attempt ceiling a conversation the backend leaves wedged in
  // `processing` would spin the summary spinner forever.
  it('gives up after 15 attempts even if it never leaves processing', () => {
    expect(shouldStopPolling('processing', 15)).toBe(true)
    expect(shouldStopPolling('processing', 16)).toBe(true)
  })

  it('treats a deferred conversation as still enriching', () => {
    expect(isEnriching({ status: 'completed', deferred: true })).toBe(true)
    expect(isEnriching({ status: 'processing' })).toBe(true)
    expect(isEnriching({ status: 'completed' })).toBe(false)
    expect(isProcessing('completed')).toBe(false)
  })
})
