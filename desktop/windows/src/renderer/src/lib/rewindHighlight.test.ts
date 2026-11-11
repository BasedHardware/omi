import { describe, it, expect } from 'vitest'
import { highlightSegments } from './rewindHighlight'

describe('highlightSegments', () => {
  it('flags the matched run and leaves the rest plain', () => {
    const segs = highlightSegments('the invoice is attached', ['invoice'])
    expect(segs).toEqual([
      { text: 'the ', match: false },
      { text: 'invoice', match: true },
      { text: ' is attached', match: false }
    ])
  })

  it('is case-insensitive but preserves the original casing in the output', () => {
    const segs = highlightSegments('Quarterly Performance review', ['performance'])
    expect(segs.find((s) => s.match)?.text).toBe('Performance')
  })

  it('highlights multiple terms and the longest match wins at a position', () => {
    const segs = highlightSegments('performance perf', ['perf', 'performance'])
    const matched = segs.filter((s) => s.match).map((s) => s.text)
    expect(matched).toEqual(['performance', 'perf'])
  })

  it('returns a single plain segment when nothing matches', () => {
    expect(highlightSegments('nothing here', ['xyz'])).toEqual([
      { text: 'nothing here', match: false }
    ])
  })

  it('handles empty inputs', () => {
    expect(highlightSegments('', ['x'])).toEqual([])
    expect(highlightSegments('abc', [])).toEqual([{ text: 'abc', match: false }])
  })
})
