import { describe, expect, it } from 'vitest'
import { LiveNotesAccumulator, type AccumulatorSegment } from './liveNotesAccumulator'

// Build a single-segment update whose text has `n` words, under a stable id.
function seg(id: string, wordCount: number): AccumulatorSegment {
  return { id, text: Array.from({ length: wordCount }, (_, i) => `w${i}`).join(' ') }
}

describe('LiveNotesAccumulator', () => {
  it('fires only once the word threshold of NEW words is reached', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 5 })
    expect(acc.handleSegmentsUpdate([seg('a', 3)], false)).toBeNull() // 3 < 5
    // Same segment refined to 5 words → 2 new words, total 5 → fires.
    const req = acc.handleSegmentsUpdate([seg('a', 5)], false)
    expect(req).not.toBeNull()
    expect(req?.segmentEndOrder).toBe(1)
    expect(req?.recentText.split(' ')).toHaveLength(5)
  })

  it('does not re-count words already contributed by a refined segment', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 10 })
    expect(acc.handleSegmentsUpdate([seg('a', 8)], false)).toBeNull()
    // Re-emitting the SAME 8-word segment adds zero new words → no request.
    expect(acc.handleSegmentsUpdate([seg('a', 8)], false)).toBeNull()
    // A second segment adds 2 → total new = 10 → fires.
    expect(acc.handleSegmentsUpdate([seg('a', 8), seg('b', 2)], false)).not.toBeNull()
  })

  it('is single-flight: no request while a generation is in flight', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 5 })
    expect(acc.handleSegmentsUpdate([seg('a', 10)], true)).toBeNull() // isGenerating
    // Once free, the already-buffered words fire immediately (1 new word suffices).
    expect(acc.handleSegmentsUpdate([seg('a', 11)], false)).not.toBeNull()
  })

  it('keeps the remainder past the threshold toward the next note', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 5 })
    const req = acc.handleSegmentsUpdate([seg('a', 12)], false) // 12 new, >= 5
    expect(req).not.toBeNull()
    acc.markGenerationSucceeded('note one') // 12 - 5 = 7 remain, still >= 5
    // One more new word → 8 >= 5 → fires again without needing another full 5.
    expect(acc.handleSegmentsUpdate([seg('a', 13)], false)).not.toBeNull()
  })

  it('caps the rolling word buffer and passes only the last threshold words', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 5, maxWordBufferSize: 10 })
    const big: AccumulatorSegment = {
      id: 'a',
      text: Array.from({ length: 30 }, (_, i) => `x${i}`).join(' ')
    }
    const req = acc.handleSegmentsUpdate([big], false)
    // recentText is the LAST `wordThreshold` words of the (capped) buffer.
    expect(req?.recentText.split(' ')).toHaveLength(5)
    expect(req?.recentText).toBe('x25 x26 x27 x28 x29')
  })

  it('formats existing-notes context and avoids repeats', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 3 })
    const first = acc.handleSegmentsUpdate([seg('a', 3)], false)
    expect(first?.existingNotesText).toBe('No existing notes yet.')
    acc.markGenerationSucceeded('discussed the roadmap')
    const second = acc.handleSegmentsUpdate([seg('a', 6)], false)
    expect(second?.existingNotesText).toBe('Existing notes:\n- discussed the roadmap')
  })

  it('trims existing-notes context to the cap (last N notes)', () => {
    const acc = new LiveNotesAccumulator({ maxExistingNotesContext: 2 })
    acc.seedExistingNotes(['one', 'two', 'three', 'four'])
    const req = acc.handleSegmentsUpdate([seg('a', 60)], false)
    expect(req?.existingNotesText).toBe('Existing notes:\n- three\n- four')
  })

  it('forgets word counts for segments that disappear (new conversation)', () => {
    const acc = new LiveNotesAccumulator({ wordThreshold: 5 })
    acc.handleSegmentsUpdate([seg('a', 8)], false) // fires, buffer has words
    acc.markGenerationSucceeded('n')
    // A fresh conversation reuses id 'a' with new content — since the old 'a' is
    // gone from the set on the transition, its processed count is dropped and the
    // new words count fresh.
    acc.reset()
    expect(acc.handleSegmentsUpdate([seg('a', 5)], false)).not.toBeNull()
  })
})
