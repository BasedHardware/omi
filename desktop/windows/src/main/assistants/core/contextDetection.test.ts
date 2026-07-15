// The normalization is the whole value of this module: without it, a title that
// re-renders itself (spinner, timer, unread badge) reads as a context switch, and
// every switch resets the assistants' analysis cycle. Each case below is a title
// that changes character-by-character while the user has not moved at all.
import { describe, expect, it } from 'vitest'
import { didContextChange, normalizeWindowTitle } from './contextDetection'

describe('normalizeWindowTitle', () => {
  it('strips braille spinner glyphs', () => {
    expect(normalizeWindowTitle('⠋ Building — vite')).toBe('Building — vite')
    expect(normalizeWindowTitle('⣾ Building — vite')).toBe('Building — vite')
  })

  it('strips non-braille spinner glyphs', () => {
    expect(normalizeWindowTitle('◐ Installing')).toBe('Installing')
    expect(normalizeWindowTitle('✳ Thinking')).toBe('Thinking')
  })

  it('strips timers', () => {
    expect(normalizeWindowTitle('Meet — 12:34')).toBe('Meet —')
    expect(normalizeWindowTitle('Meet — 1:23:45')).toBe('Meet —')
  })

  it('strips terminal dimensions', () => {
    expect(normalizeWindowTitle('zsh — 80×24')).toBe('zsh —')
    expect(normalizeWindowTitle('zsh — 120x40')).toBe('zsh —')
  })

  it('strips bracketed unread counts', () => {
    expect(normalizeWindowTitle('Inbox (3) - Gmail')).toBe('Inbox - Gmail')
    expect(normalizeWindowTitle('Slack [12]')).toBe('Slack')
  })

  it('collapses whitespace and returns null for an empty result', () => {
    expect(normalizeWindowTitle('a    b')).toBe('a b')
    expect(normalizeWindowTitle('⠋')).toBeNull()
    expect(normalizeWindowTitle('   ')).toBeNull()
    expect(normalizeWindowTitle('')).toBeNull()
    expect(normalizeWindowTitle(null)).toBeNull()
  })

  it('keeps path separators — they are structure, not spinner noise', () => {
    expect(normalizeWindowTitle('src/main/index.ts — omi')).toBe('src/main/index.ts — omi')
  })
})

describe('didContextChange', () => {
  it('is true when the app differs', () => {
    expect(didContextChange('Chrome', 'Docs', 'Slack', 'Docs')).toBe(true)
  })

  it('is true when the normalized title differs', () => {
    expect(didContextChange('Chrome', 'Docs', 'Chrome', 'Jira')).toBe(true)
  })

  it('is FALSE for a ticking spinner (same window, still working)', () => {
    expect(didContextChange('Terminal', '⠋ Building', 'Terminal', '⣾ Building')).toBe(false)
  })

  it('is FALSE for a ticking timer (same call, one second later)', () => {
    expect(didContextChange('Meet', 'Standup — 12:34', 'Meet', 'Standup — 12:35')).toBe(false)
  })

  it('is FALSE for a changing unread badge (same inbox)', () => {
    expect(didContextChange('Chrome', 'Inbox (3) - Gmail', 'Chrome', 'Inbox (4) - Gmail')).toBe(
      false
    )
  })

  it('is FALSE for a resized terminal (same shell)', () => {
    expect(didContextChange('Terminal', 'zsh — 80×24', 'Terminal', 'zsh — 100×30')).toBe(false)
  })

  it('is FALSE for the identical context', () => {
    expect(didContextChange('Chrome', 'Docs', 'Chrome', 'Docs')).toBe(false)
  })

  it('treats an empty title and a spinner-only title as the same (both carry no context)', () => {
    expect(didContextChange('Terminal', '', 'Terminal', '⠋')).toBe(false)
  })
})
