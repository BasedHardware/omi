import { describe, expect, it } from 'vitest'
import {
  containedImageRect,
  highlightTerms,
  lineTextMatches,
  normalizedBoxToRect
} from './rewindOverlay'

describe('containedImageRect (aspect-fit letterboxing)', () => {
  it('letterboxes vertically when the image is wider than the container ratio', () => {
    // 200x100 image inside 200x200 container → scale 1, centered with 50px top/bottom bars.
    expect(containedImageRect(200, 200, 200, 100)).toEqual({
      left: 0,
      top: 50,
      width: 200,
      height: 100
    })
  })

  it('pillarboxes horizontally when the image is taller than the container ratio', () => {
    // 100x200 image inside 200x200 container → scale 1, centered with 50px left/right bars.
    expect(containedImageRect(200, 200, 100, 200)).toEqual({
      left: 50,
      top: 0,
      width: 100,
      height: 200
    })
  })

  it('scales down to fit while preserving aspect ratio', () => {
    // 400x200 image inside 200x200 container → scale 0.5 → 200x100, centered.
    expect(containedImageRect(200, 200, 400, 200)).toEqual({
      left: 0,
      top: 50,
      width: 200,
      height: 100
    })
  })

  it('returns a zero rect for degenerate inputs', () => {
    expect(containedImageRect(0, 200, 100, 100)).toEqual({ left: 0, top: 0, width: 0, height: 0 })
    expect(containedImageRect(200, 200, 0, 100)).toEqual({ left: 0, top: 0, width: 0, height: 0 })
  })
})

describe('normalizedBoxToRect', () => {
  it('maps a normalized box onto the contained image rect (respecting the offset)', () => {
    const contained = { left: 0, top: 50, width: 200, height: 100 }
    // A box at the top-left quarter of the image.
    expect(normalizedBoxToRect({ x: 0, y: 0, w: 0.5, h: 0.5 }, contained)).toEqual({
      left: 0,
      top: 50,
      width: 100,
      height: 50
    })
    // A box centered in the lower-right.
    expect(normalizedBoxToRect({ x: 0.5, y: 0.5, w: 0.25, h: 0.25 }, contained)).toEqual({
      left: 100,
      top: 100,
      width: 50,
      height: 25
    })
  })
})

describe('highlightTerms + lineTextMatches', () => {
  it('lowercases and drops sub-2-char terms', () => {
    expect(highlightTerms('  Budget A Report ')).toEqual(['budget', 'report'])
    expect(highlightTerms('   ')).toEqual([])
  })

  it('matches a line when it contains any term (case-insensitive)', () => {
    const terms = highlightTerms('Budget Report')
    expect(lineTextMatches('Q3 BUDGET summary', terms)).toBe(true)
    expect(lineTextMatches('unrelated line', terms)).toBe(false)
  })

  it('never matches when there are no terms', () => {
    expect(lineTextMatches('anything', [])).toBe(false)
  })
})
