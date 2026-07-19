import { describe, it, expect } from 'vitest'
import { publishPlaybackLevel, subscribePlaybackLevel } from './playbackLevelBus'

describe('playbackLevelBus', () => {
  it('delivers published levels to every subscriber, and unsubscribe stops delivery', () => {
    const a: number[] = []
    const b: number[] = []
    const unA = subscribePlaybackLevel((v) => a.push(v))
    const unB = subscribePlaybackLevel((v) => b.push(v))
    publishPlaybackLevel(0.4)
    unA()
    publishPlaybackLevel(0.7)
    unB()
    publishPlaybackLevel(0.9) // no listeners — must not throw
    expect(a).toEqual([0.4])
    expect(b).toEqual([0.4, 0.7])
  })

  it('a subscriber unsubscribing during dispatch does not skip the others', () => {
    const seen: string[] = []
    const unA = subscribePlaybackLevel(() => {
      seen.push('a')
      unA() // self-removal mid-dispatch (snapshot iteration)
    })
    subscribePlaybackLevel(() => seen.push('b'))
    publishPlaybackLevel(0.5)
    publishPlaybackLevel(0.6)
    expect(seen).toEqual(['a', 'b', 'b'])
  })
})
