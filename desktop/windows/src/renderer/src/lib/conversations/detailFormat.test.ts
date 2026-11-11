import { describe, it, expect } from 'vitest'
import type { Conversation } from '../omiApi.generated'
import { conversationDuration, displayCategory, formatDuration } from './detailFormat'

function conv(over: Partial<Conversation> = {}): Conversation {
  return {
    id: 'c1',
    created_at: '2026-07-01T14:30:00Z',
    started_at: '2026-07-01T14:30:00Z',
    finished_at: '2026-07-01T14:35:30Z',
    structured: {},
    ...over
  } as Conversation
}

describe('formatDuration', () => {
  it('formats as Mac does', () => {
    expect(formatDuration(330)).toBe('5m 30s')
    expect(formatDuration(60)).toBe('1m 0s')
    expect(formatDuration(42)).toBe('42s') // under a minute drops the minutes
    expect(formatDuration(0)).toBe('0s')
    expect(formatDuration(-5)).toBe('0s') // never negative
  })
})

describe('conversationDuration', () => {
  it('uses the recorded window when finished_at is stamped', () => {
    expect(conversationDuration(conv())).toBe(330)
  })

  // Anything still in progress has no finished_at — Mac falls back to how far the
  // transcript actually got rather than showing nothing.
  it('falls back to the last segment end when there is no finished_at', () => {
    const c = conv({
      finished_at: null,
      transcript_segments: [
        { text: 'a', start: 0, end: 4, is_user: false },
        { text: 'b', start: 5, end: 23, is_user: false }
      ]
    })
    expect(conversationDuration(c)).toBe(23)
  })

  it('is null when neither is known', () => {
    expect(conversationDuration(conv({ finished_at: null }))).toBeNull()
  })
})

describe('displayCategory', () => {
  it('hides the catch-all "other" bucket', () => {
    expect(displayCategory(conv({ structured: { category: 'other' } }))).toBeNull()
    expect(displayCategory(conv({ structured: { category: 'work' } }))).toBe('work')
    expect(displayCategory(conv({ structured: {} }))).toBeNull()
  })
})
