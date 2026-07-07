import { describe, it, expect } from 'vitest'
import {
  DEFAULT_OVERLAY_ACCELERATOR,
  acceleratorToTokens,
  eventToAccelerator,
  validateCustomAccelerator
} from './overlayShortcut'

const ev = (p: Partial<Parameters<typeof eventToAccelerator>[0]> & { key: string }) => ({
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
  metaKey: false,
  ...p
})

describe('acceleratorToTokens', () => {
  it('renders the default as Shift + Space', () => {
    expect(acceleratorToTokens(DEFAULT_OVERLAY_ACCELERATOR)).toEqual(['Shift', 'Space'])
  })

  it('maps modifiers and upper-cases single keys', () => {
    expect(acceleratorToTokens('CommandOrControl+Shift+J')).toEqual(['Ctrl', 'Shift', 'J'])
  })

  it('maps Super to Win and Return to Enter', () => {
    expect(acceleratorToTokens('Super+Return')).toEqual(['Win', 'Enter'])
  })

  it('returns [] for an empty accelerator', () => {
    expect(acceleratorToTokens('')).toEqual([])
  })
})

describe('eventToAccelerator', () => {
  it('builds Ctrl+Space from a space press with ctrl held', () => {
    expect(eventToAccelerator(ev({ key: ' ', ctrlKey: true }))).toBe('CommandOrControl+Space')
  })

  it('builds a multi-modifier accelerator in CommandOrControl+Alt+Shift order', () => {
    expect(eventToAccelerator(ev({ key: 'j', ctrlKey: true, shiftKey: true, altKey: true }))).toBe(
      'CommandOrControl+Alt+Shift+J'
    )
  })

  it('maps the Windows key to Super', () => {
    expect(eventToAccelerator(ev({ key: 'k', metaKey: true }))).toBe('Super+K')
  })

  it('rejects a key with no modifier', () => {
    expect(eventToAccelerator(ev({ key: 'j' }))).toBeNull()
  })

  it('returns null while only a modifier is held (chord still building)', () => {
    expect(eventToAccelerator(ev({ key: 'Control', ctrlKey: true }))).toBeNull()
  })

  it('returns null for Escape (used to cancel capture)', () => {
    expect(eventToAccelerator(ev({ key: 'Escape', ctrlKey: true }))).toBeNull()
  })
})

describe('validateCustomAccelerator', () => {
  it('accepts the default, Ctrl+J, and Ctrl+Shift+Space', () => {
    expect(validateCustomAccelerator(DEFAULT_OVERLAY_ACCELERATOR).ok).toBe(true)
    expect(validateCustomAccelerator('CommandOrControl+J').ok).toBe(true)
    expect(validateCustomAccelerator('CommandOrControl+Shift+Space').ok).toBe(true)
  })

  it('allows Shift with a non-typing key (Shift+Space / Shift+Return)', () => {
    expect(validateCustomAccelerator('Shift+Space').ok).toBe(true)
    expect(validateCustomAccelerator('Shift+Return').ok).toBe(true)
  })

  it('rejects Shift + a typing key (would just type a capital)', () => {
    const r = validateCustomAccelerator('Shift+J')
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.reason).toMatch(/Shift/)
  })

  it('rejects any Alt combo (dangerous on Windows)', () => {
    expect(validateCustomAccelerator('Alt+K').ok).toBe(false)
    expect(validateCustomAccelerator('Alt+Shift+K').ok).toBe(false)
    const r = validateCustomAccelerator('CommandOrControl+Alt+J')
    expect(r.ok).toBe(false)
    expect(r.ok === false && r.reason).toMatch(/Alt/)
  })

  it('rejects Ctrl+Enter and other common editor combos', () => {
    expect(validateCustomAccelerator('CommandOrControl+Return').ok).toBe(false)
    expect(validateCustomAccelerator('CommandOrControl+C').ok).toBe(false)
    expect(validateCustomAccelerator('CommandOrControl+S').ok).toBe(false)
  })

  it('rejects a bare key with no modifier', () => {
    expect(validateCustomAccelerator('J').ok).toBe(false)
  })

  it('rejects a combo with no main key', () => {
    expect(validateCustomAccelerator('CommandOrControl+Shift').ok).toBe(false)
  })
})
