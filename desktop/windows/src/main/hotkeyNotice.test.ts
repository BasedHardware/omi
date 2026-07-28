import { describe, it, expect } from 'vitest'
import { buildHotkeyConflictNotice } from './hotkeyNotice'

describe('buildHotkeyConflictNotice', () => {
  it('returns null when every enabled chord registered', () => {
    expect(
      buildHotkeyConflictNotice([
        { name: 'Summon', accelerator: 'Shift+Space', registered: true },
        { name: 'Record', accelerator: 'Ctrl+Space', registered: true, enabled: true }
      ])
    ).toBeNull()
  })

  it('returns null on an empty list', () => {
    expect(buildHotkeyConflictNotice([])).toBeNull()
  })

  it('names the single failed chord and points at Settings', () => {
    const notice = buildHotkeyConflictNotice([
      { name: 'Summon', accelerator: 'Shift+Space', registered: false },
      { name: 'Record', accelerator: 'Ctrl+Space', registered: true, enabled: true }
    ])
    expect(notice).not.toBeNull()
    expect(notice?.title).toBe('Shortcut unavailable')
    expect(notice?.body).toContain('Summon (Shift+Space)')
    expect(notice?.body).not.toContain('Record')
    expect(notice?.body).toContain('Settings → Shortcuts')
  })

  it('combines multiple failures into one notice', () => {
    const notice = buildHotkeyConflictNotice([
      { name: 'Summon', accelerator: 'Shift+Space', registered: false },
      { name: 'Record', accelerator: 'Ctrl+Space', registered: false, enabled: true }
    ])
    expect(notice?.title).toBe('Shortcuts unavailable')
    expect(notice?.body).toContain('Summon (Shift+Space) and Record (Ctrl+Space)')
    expect(notice?.body).toContain('them')
  })

  it('ignores a disabled chord even when it is unregistered', () => {
    // The user turned the record chord off: unregistered is expected, not a conflict.
    expect(
      buildHotkeyConflictNotice([
        { name: 'Summon', accelerator: 'Shift+Space', registered: true },
        { name: 'Record', accelerator: 'Ctrl+Space', registered: false, enabled: false }
      ])
    ).toBeNull()
  })

  it('treats a missing enabled flag as enabled', () => {
    const notice = buildHotkeyConflictNotice([
      { name: 'Summon', accelerator: 'Shift+Space', registered: false }
    ])
    expect(notice).not.toBeNull()
    expect(notice?.body).toContain('Summon (Shift+Space)')
  })
})
