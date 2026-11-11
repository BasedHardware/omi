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

  // Bug fix: grouping/snippet used to test the RAW query as one literal substring.
  // A frame that FTS surfaced only via camelCase/digit/prefix expansion — where the
  // raw query never appears verbatim in the OCR text — then got the wrong
  // representative (fell through to `last`) and an un-highlighted `slice(0,80)`
  // head. groupFrames now uses the same expanded terms buildRewindFtsMatch searches.
  it('picks the representative + highlights via FTS-expanded terms, not the raw query', () => {
    // Raw query "ActivityPerformance" — its camelCase split yields "Activity" /
    // "Performance", either of which FTS prefix-matches. Neither frame contains the
    // literal "activityperformance" substring, so the OLD raw-substring code found
    // no match and fell back to `last` (id 2) + a snippet head.
    const other = frame({ id: 1, ts: 1000, ocrText: 'Quarterly Performance review notes' })
    const noise = frame({ id: 2, ts: 1005, ocrText: 'unrelated trailing content xxxxxxxxxx' })
    const groups = groupFrames([other, noise], 'ActivityPerformance')
    expect(groups).toHaveLength(1)
    // The frame whose text actually contains an expanded term wins — not `last`.
    expect(groups[0].representative.id).toBe(1)
    // ...and the snippet is centered on the real match, so it highlights.
    expect(groups[0].matchSnippet.toLowerCase()).toContain('performance')
  })

  // Semantic affordance: with the keyword id set supplied (phase-2 merged results),
  // a group whose frames were NONE of the keyword hits is flagged as vector-only.
  it('flags a purely-semantic group (no keyword member) when keywordIds is given', () => {
    const kw = frame({ id: 1, ts: 1_000, app: 'Mail', ocrText: 'the invoice is attached' })
    const semantic = frame({ id: 2, ts: 9_000_000, app: 'Web', ocrText: 'billing overview' })
    const groups = groupFrames([kw, semantic], 'invoice', { keywordIds: new Set([1]) })
    const byRep = new Map(groups.map((g) => [g.representative.id, g]))
    expect(byRep.get(1)?.matchedSemantically).toBe(false) // keyword hit
    expect(byRep.get(2)?.matchedSemantically).toBe(true) // vector-only
  })

  it('never flags semantic without a keyword id set (phase-1 keyword-only results)', () => {
    const groups = groupFrames([frame({ id: 1, ocrText: 'hello' })], 'hello')
    expect(groups[0].matchedSemantically).toBe(false)
  })

  it('keeps frames inside a group in chronological order', () => {
    const groups = groupFrames([frame({ id: 2, ts: 20 }), frame({ id: 1, ts: 10 })], 'hello')
    expect(groups).toHaveLength(1)
    expect(groups[0].frames.map((f) => f.id)).toEqual([1, 2])
  })
})
