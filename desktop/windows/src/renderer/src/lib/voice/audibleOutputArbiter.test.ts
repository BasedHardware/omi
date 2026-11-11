import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  beginRealtimeAudible,
  endRealtimeAudible,
  isRealtimeAudible,
  registerTtsStop,
  __resetAudibleArbiterForTests
} from './audibleOutputArbiter'

beforeEach(() => __resetAudibleArbiterForTests())

describe('audibleOutputArbiter — single audible owner', () => {
  it('reports no realtime lane audible at rest', () => {
    expect(isRealtimeAudible()).toBe(false)
  })

  it('marks realtime audible between begin and end', () => {
    const token = beginRealtimeAudible()
    expect(isRealtimeAudible()).toBe(true)
    endRealtimeAudible(token)
    expect(isRealtimeAudible()).toBe(false)
  })

  it('preempts the in-flight TTS cascade the instant a realtime lane speaks', () => {
    const stopTts = vi.fn()
    registerTtsStop(stopTts)
    const token = beginRealtimeAudible()
    expect(stopTts).toHaveBeenCalledTimes(1)
    endRealtimeAudible(token)
  })

  it('does not throw or leave state dirty when the TTS stop hook throws', () => {
    registerTtsStop(() => {
      throw new Error('boom')
    })
    const token = beginRealtimeAudible()
    // The throw is contained — the realtime lane is still the audible owner.
    expect(isRealtimeAudible()).toBe(true)
    endRealtimeAudible(token)
    expect(isRealtimeAudible()).toBe(false)
  })

  it('stays audible until EVERY realtime speaker ends (two overlapping lanes)', () => {
    const a = beginRealtimeAudible()
    const b = beginRealtimeAudible()
    expect(isRealtimeAudible()).toBe(true)
    endRealtimeAudible(a)
    // One lane ended but the other is still speaking — must remain audible.
    expect(isRealtimeAudible()).toBe(true)
    endRealtimeAudible(b)
    expect(isRealtimeAudible()).toBe(false)
  })

  it('is idempotent for a double-end and a null token (no leak, no underflow)', () => {
    const token = beginRealtimeAudible()
    endRealtimeAudible(token)
    endRealtimeAudible(token) // double end — safe no-op
    endRealtimeAudible(null) // null — safe no-op
    expect(isRealtimeAudible()).toBe(false)
  })

  it('a stale token from a previous turn cannot clear a newer realtime speaker', () => {
    const stale = beginRealtimeAudible()
    endRealtimeAudible(stale)
    const fresh = beginRealtimeAudible()
    endRealtimeAudible(stale) // the old token must not clear the fresh owner
    expect(isRealtimeAudible()).toBe(true)
    endRealtimeAudible(fresh)
    expect(isRealtimeAudible()).toBe(false)
  })
})
