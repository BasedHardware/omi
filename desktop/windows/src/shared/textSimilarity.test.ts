import { describe, it, expect } from 'vitest'
import {
  isNearDuplicateText,
  normalizeForTextSimilarity,
  textSimilarityRatio
} from './textSimilarity'

describe('textSimilarity', () => {
  it('normalizes case and whitespace', () => {
    expect(normalizeForTextSimilarity('  Hello\nWORLD  ')).toBe('hello world')
  })

  it('treats long nearly-identical OCR text as a near duplicate', () => {
    const a = 'Project Alpha roadmap Q2 launch risk checklist owner Junius status green'
    const b = 'Project Alpha roadmap Q2 launch risk checklist owner Junius status green.'
    expect(isNearDuplicateText(a, b)).toBe(true)
    expect(textSimilarityRatio(a, b)).toBeGreaterThanOrEqual(0.92)
  })

  it('does not collapse short changed UI labels', () => {
    expect(isNearDuplicateText('Open', 'Open file')).toBe(false)
  })

  it('does not collapse unrelated OCR text', () => {
    const a = 'Project Alpha roadmap Q2 launch risk checklist owner Junius status green'
    const b = 'Chrome search results for SQLite OCR clustering and markdown context'
    expect(isNearDuplicateText(a, b)).toBe(false)
  })
})
