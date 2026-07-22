import { describe, it, expect, vi } from 'vitest'
import { createSignal } from './signal'

describe('createSignal', () => {
  it('replays the current value to a new subscriber immediately', () => {
    const s = createSignal<number | null>(null)
    const seen: (number | null)[] = []
    s.subscribe((v) => seen.push(v))
    expect(seen).toEqual([null])
  })

  it('broadcasts set() to every subscriber, and get() reflects the latest value', () => {
    const s = createSignal(0)
    const a: number[] = []
    const b: number[] = []
    s.subscribe((v) => a.push(v))
    s.subscribe((v) => b.push(v))
    s.set(1)
    s.set(2)
    expect(a).toEqual([0, 1, 2])
    expect(b).toEqual([0, 1, 2])
    expect(s.get()).toBe(2)
  })

  it('delivers a set-before-subscribe value to a later subscriber (race-proof buffering)', () => {
    const s = createSignal<string | null>(null)
    s.set('buffered')
    const cb = vi.fn()
    s.subscribe(cb)
    expect(cb).toHaveBeenCalledWith('buffered')
  })

  it('unsubscribe stops further delivery without affecting other subscribers', () => {
    const s = createSignal(0)
    const a: number[] = []
    const b: number[] = []
    const offA = s.subscribe((v) => a.push(v))
    s.subscribe((v) => b.push(v))
    offA()
    s.set(1)
    expect(a).toEqual([0]) // unsubscribed before the broadcast
    expect(b).toEqual([0, 1])
  })
})
