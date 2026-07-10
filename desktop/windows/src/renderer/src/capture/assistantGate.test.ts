import { describe, it, expect, afterEach } from 'vitest'
import { assistantGate, wrapFeed } from './assistantGate'

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
