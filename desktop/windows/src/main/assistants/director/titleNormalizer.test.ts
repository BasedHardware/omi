import { describe, it, expect } from 'vitest'
import { normalizeTitleForIdentity, identityKey } from './titleNormalizer'

describe('normalizeTitleForIdentity', () => {
  it('returns null for null, empty, and whitespace-only titles', () => {
    expect(normalizeTitleForIdentity(null, 'Notepad')).toBeNull()
    expect(normalizeTitleForIdentity('', 'Notepad')).toBeNull()
    expect(normalizeTitleForIdentity('   ', 'Notepad')).toBeNull()
  })

  it('strips braille spinner characters (U+2800-U+28FF)', () => {
    expect(normalizeTitleForIdentity('⣾ Building project', 'Code')).toBe('Building project')
  })

  it('strips progress glyphs', () => {
    expect(normalizeTitleForIdentity('◐ Loading dashboard ✳', 'Code')).toBe('Loading dashboard')
  })

  it('removes clock times and dimensions anywhere in the title', () => {
    expect(normalizeTitleForIdentity('Meeting 10:30 notes', 'Notepad')).toBe('Meeting notes')
    expect(normalizeTitleForIdentity('Timer 1:02:03 running', 'Notepad')).toBe('Timer running')
    expect(normalizeTitleForIdentity('Screen 1920x1080 capture', 'Notepad')).toBe('Screen capture')
    expect(normalizeTitleForIdentity('Frame 640×480 view', 'Notepad')).toBe('Frame view')
  })

  it('strips leading unread badges only for messaging and browser apps', () => {
    expect(normalizeTitleForIdentity('(3) Inbox', 'Google Chrome')).toBe('Inbox')
    expect(normalizeTitleForIdentity('[12] general', 'Slack')).toBe('general')
    // Non-messaging, non-browser apps keep the badge as identity.
    expect(normalizeTitleForIdentity('(3) Inbox', 'Notepad')).toBe('(3) Inbox')
  })

  it('strips trailing counts and new-item suffixes only for messaging apps', () => {
    expect(normalizeTitleForIdentity('general (4)', 'Slack')).toBe('general')
    expect(normalizeTitleForIdentity('team [2]', 'Discord')).toBe('team')
    expect(normalizeTitleForIdentity('inbox - 3 new messages', 'Telegram Desktop')).toBe('inbox')
    expect(normalizeTitleForIdentity('inbox — 5 items', 'Telegram Desktop')).toBe('inbox')
    // Browsers keep trailing counts: identity, not unread churn.
    expect(normalizeTitleForIdentity('Results (4)', 'Google Chrome')).toBe('Results (4)')
    expect(normalizeTitleForIdentity('Report (2)', 'Notepad')).toBe('Report (2)')
  })

  it('strips shell suffixes for terminal apps only', () => {
    expect(normalizeTitleForIdentity('~/project — zsh', 'Windows Terminal')).toBe('~/project')
    expect(normalizeTitleForIdentity('~/project — zsh', 'Notepad')).toBe('~/project — zsh')
  })

  it('collapses whitespace runs and trims', () => {
    expect(normalizeTitleForIdentity('  a   b  ', 'Notepad')).toBe('a b')
  })

  it('returns null when stripping consumes everything', () => {
    expect(normalizeTitleForIdentity('10:30', 'Notepad')).toBeNull()
    expect(normalizeTitleForIdentity('⠀⠁', 'Notepad')).toBeNull()
  })
})

describe('identityKey', () => {
  it('is app::title, both lowercased', () => {
    expect(identityKey('Google Chrome', 'GitHub Inbox')).toBe('google chrome::github inbox')
  })

  it('is null when the title normalizes to nothing', () => {
    expect(identityKey('Notepad', '   ')).toBeNull()
    expect(identityKey('Notepad', null)).toBeNull()
  })
})
