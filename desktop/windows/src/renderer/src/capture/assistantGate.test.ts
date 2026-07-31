import { describe, it, expect, afterEach } from 'vitest'
import { assistantGate, wrapFeed, GATE_TTL_MS, GATE_REASSERT_MS } from './assistantGate'

afterEach(() => assistantGate.setSpeaking(false))

describe('assistantGate.wrapFeed', () => {
  it('passes frames through while Omi is silent', () => {
    const got: number[] = []
    const feed = wrapFeed((n: number) => got.push(n))
    feed(1)
    feed(2)
    expect(got).toEqual([1, 2])
  })

  it('drops every frame while assistant-speaking is active, resumes after', () => {
    const got: number[] = []
    const feed = wrapFeed((n: number) => got.push(n))
    feed(1)
    assistantGate.setSpeaking(true)
    feed(2) // Omi's own voice — must never reach the transcription feed
    feed(3)
    assistantGate.setSpeaking(false)
    feed(4)
    expect(got).toEqual([1, 4])
  })

  it('gate state applies to feeds wrapped before OR after the toggle (module-global)', () => {
    assistantGate.setSpeaking(true)
    const got: number[] = []
    const feed = wrapFeed((n: number) => got.push(n))
    feed(1)
    expect(got).toEqual([])
    expect(assistantGate.isPaused()).toBe(true)
  })
})

describe('assistantGate TTL (sender-death resilience)', () => {
  it('an ON assertion expires after GATE_TTL_MS without a re-assert', () => {
    assistantGate.setSpeaking(true, 1000)
    expect(assistantGate.isPaused(1000)).toBe(true)
    expect(assistantGate.isPaused(1000 + GATE_TTL_MS - 1)).toBe(true)
    // The sender died mid-speech — transcription must NOT stay deaf forever.
    expect(assistantGate.isPaused(1000 + GATE_TTL_MS)).toBe(false)
  })

  it('periodic re-asserts keep the gate held past a single TTL', () => {
    assistantGate.setSpeaking(true, 0)
    assistantGate.setSpeaking(true, GATE_REASSERT_MS) // controller refresh
    expect(assistantGate.isPaused(GATE_REASSERT_MS + GATE_TTL_MS - 1)).toBe(true)
  })

  it('the re-assert interval is comfortably inside the TTL', () => {
    expect(GATE_REASSERT_MS * 2).toBeLessThanOrEqual(GATE_TTL_MS)
  })

  it('OFF is immediate regardless of TTL', () => {
    assistantGate.setSpeaking(true, 0)
    assistantGate.setSpeaking(false, 10)
    expect(assistantGate.isPaused(10)).toBe(false)
  })
})
