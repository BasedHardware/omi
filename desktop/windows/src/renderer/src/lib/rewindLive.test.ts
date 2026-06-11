import { describe, it, expect } from 'vitest'
import { mergeFrames, isFollowingLive } from './rewindLive'
import type { RewindFrame } from '../../../shared/types'

const f = (id: number, ts: number): RewindFrame => ({ id, ts }) as RewindFrame

describe('mergeFrames', () => {
  it('appends newer frames in timestamp order', () => {
    const merged = mergeFrames([f(1, 100), f(2, 200)], [f(3, 300)])
    expect(merged.map((x) => x.id)).toEqual([1, 2, 3])
  })

  it('dedupes frames that already exist by timestamp', () => {
    const merged = mergeFrames([f(1, 100), f(2, 200)], [f(2, 200), f(3, 300)])
    expect(merged.map((x) => x.id)).toEqual([1, 2, 3])
  })

  it('returns frames sorted even if incoming is out of order', () => {
    const merged = mergeFrames([f(1, 100)], [f(3, 300), f(2, 200)])
    expect(merged.map((x) => x.ts)).toEqual([100, 200, 300])
  })

  it('leaves the list unchanged when nothing new arrives', () => {
    const prev = [f(1, 100), f(2, 200)]
    expect(mergeFrames(prev, []).map((x) => x.id)).toEqual([1, 2])
  })
})

describe('isFollowingLive', () => {
  it('follows when the cursor sits on the newest frame', () => {
    expect(isFollowingLive(200, [f(1, 100), f(2, 200)])).toBe(true)
  })

  it('follows when the cursor is at or past the newest frame', () => {
    expect(isFollowingLive(250, [f(1, 100), f(2, 200)])).toBe(true)
  })

  it('does not follow when the user has scrubbed back', () => {
    expect(isFollowingLive(100, [f(1, 100), f(2, 200)])).toBe(false)
  })

  it('follows when there are no frames yet', () => {
    expect(isFollowingLive(0, [])).toBe(true)
  })
})
