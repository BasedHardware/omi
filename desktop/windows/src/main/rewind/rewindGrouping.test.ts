import { describe, it, expect } from 'vitest'
import { groupFrames, GROUP_WINDOW_MS } from './rewindGrouping'
import type { RewindFrame } from '../../shared/types'

function frame(over: Partial<RewindFrame>): RewindFrame {
  return {
    id: 1,
    ts: 0,
    app: 'Code.exe',
    windowTitle: 'a.ts',
    processName: 'Code',
    ocrText: 'hello world',
    imagePath: '/x.jpg',
    width: 0,
    height: 0,
    indexed: 1,
    ...over
  }
}

describe('groupFrames', () => {
  it('clusters frames within the time window AND same app+window into one group', () => {
    const frames = [
      frame({ id: 1, ts: 1000 }),
      frame({ id: 2, ts: 1000 + GROUP_WINDOW_MS - 1 }),
      frame({ id: 3, ts: 1000 + GROUP_WINDOW_MS + 5000 }) // new group (gap > window)
    ]
    const groups = groupFrames(frames, 'hello')
    expect(groups).toHaveLength(2)
    // Frames 1+2 cluster (same app/window, inside the window); 3 is its own group.
    // Group order follows the INPUT (relevance) order, so 1+2's group leads here.
    expect(groups[0].frames.map((f) => f.id)).toEqual([1, 2])
    expect(groups[1].frames.map((f) => f.id)).toEqual([3])
  })
  it('splits when app/window changes even within the window', () => {
    const groups = groupFrames(
      [frame({ id: 1, ts: 0, app: 'A' }), frame({ id: 2, ts: 10, app: 'B' })],
      'hello'
    )
    expect(groups).toHaveLength(2)
  })
  it('sets startTs/endTs/representative/snippet', () => {
    const groups = groupFrames([frame({ id: 2, ts: 9_000_000 }), frame({ id: 1, ts: 0 })], 'world')
    expect(groups[0].startTs).toBe(9_000_000)
    expect(groups[0].representative.id).toBe(2)
    expect(groups[0].matchSnippet.toLowerCase()).toContain('world')
  })

  // M-2 regression. The caller hands us a RELEVANCE-ordered list (FTS by bm25,
  // then vector hits appended). Re-sorting the groups by timestamp — which this
  // function used to do unconditionally — silently threw that away and let a
  // barely-over-threshold semantic hit from today outrank an exact keyword match
  // from last week.
  it('orders groups by their best-ranked member, NOT by recency', () => {
    const old_exact = frame({ id: 1, ts: 1_000, app: 'Mail', ocrText: 'the invoice is attached' })
    const recent_fuzzy = frame({ id: 2, ts: 9_000_000, app: 'Web', ocrText: 'billing overview' })

    // Input order = relevance: the exact keyword hit leads, the semantic hit trails.
    const groups = groupFrames([old_exact, recent_fuzzy], 'invoice')

    expect(groups.map((g) => g.representative.id)).toEqual([1, 2])
    // ...even though frame 2 is far newer. Recency must not promote it.
    expect(groups[0].startTs).toBeLessThan(groups[1].startTs)
  })

  it('keeps frames inside a group in chronological order', () => {
    const groups = groupFrames([frame({ id: 2, ts: 20 }), frame({ id: 1, ts: 10 })], 'hello')
    expect(groups).toHaveLength(1)
    expect(groups[0].frames.map((f) => f.id)).toEqual([1, 2])
  })
})
