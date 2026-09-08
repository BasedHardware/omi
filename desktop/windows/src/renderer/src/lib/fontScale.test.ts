// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest'

// fontScale.ts runs no side effects on import — `main.tsx` calls initFontScale()
// once at startup (main window only). These tests call it explicitly (exactly what
// main.tsx does) and re-import the module graph fresh per case (vi.resetModules) so
// each runs against the localStorage / hash set up first.

describe('fontScale startup application (initFontScale)', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    document.documentElement.style.fontSize = ''
    window.location.hash = ''
  })

  it('applies the persisted scale to the root element on init', async () => {
    localStorage.setItem('omi-windows-prefs-v1', JSON.stringify({ fontScale: 1.5 }))
    const { initFontScale } = await import('./fontScale')
    initFontScale()
    expect(document.documentElement.style.fontSize).toBe('24px') // 16 * 1.5
  })

  it('defaults to 16px when no scale is persisted', async () => {
    const { initFontScale } = await import('./fontScale')
    initFontScale()
    expect(document.documentElement.style.fontSize).toBe('16px')
  })

  it('clamps an out-of-range persisted scale to the max', async () => {
    localStorage.setItem('omi-windows-prefs-v1', JSON.stringify({ fontScale: 5 }))
    const { initFontScale } = await import('./fontScale')
    initFontScale()
    expect(document.documentElement.style.fontSize).toBe('32px') // clamped 2.0
  })

  it('ignores a non-finite persisted scale (falls back to default)', async () => {
    localStorage.setItem('omi-windows-prefs-v1', JSON.stringify({ fontScale: 'huge' }))
    const { initFontScale } = await import('./fontScale')
    initFontScale()
    expect(document.documentElement.style.fontSize).toBe('16px')
  })

  it('does NOT scale a secondary (floating-bar) window', async () => {
    window.location.hash = '#/bar'
    localStorage.setItem('omi-windows-prefs-v1', JSON.stringify({ fontScale: 1.5 }))
    const { initFontScale } = await import('./fontScale')
    initFontScale()
    expect(document.documentElement.style.fontSize).toBe('')
  })
})

describe('fontScale live re-apply via preferences (after init)', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    document.documentElement.style.fontSize = ''
    window.location.hash = ''
  })

  it('updates the root element when fontScale is written through setPreferences', async () => {
    const { initFontScale } = await import('./fontScale')
    const { setPreferences } = await import('./preferences')
    initFontScale()
    setPreferences({ fontScale: 1.25 })
    expect(document.documentElement.style.fontSize).toBe('20px') // 16 * 1.25
    setPreferences({ fontScale: 1 })
    expect(document.documentElement.style.fontSize).toBe('16px')
  })

  it('clamps out-of-range writes on the write path', async () => {
    const { initFontScale } = await import('./fontScale')
    const { setPreferences, getPreferences } = await import('./preferences')
    initFontScale()
    setPreferences({ fontScale: 10 })
    expect(getPreferences().fontScale).toBe(2)
    expect(document.documentElement.style.fontSize).toBe('32px')
  })
})

describe('fontScale keyboard shortcuts', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    document.documentElement.style.fontSize = ''
    window.location.hash = ''
  })

  it('increases the scale on Ctrl+= after init', async () => {
    const { initFontScale } = await import('./fontScale')
    const { getPreferences } = await import('./preferences')
    initFontScale()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true }))
    expect(getPreferences().fontScale).toBeCloseTo(1.1) // 1.0 + 0.1 step
    expect(document.documentElement.style.fontSize).toBe('17.6px')
  })

  it('decreases the scale on Ctrl+- after init', async () => {
    const { initFontScale } = await import('./fontScale')
    const { getPreferences } = await import('./preferences')
    initFontScale()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '-', ctrlKey: true }))
    expect(getPreferences().fontScale).toBeCloseTo(0.9) // 1.0 - 0.1 step
    expect(document.documentElement.style.fontSize).toBe('14.4px')
  })

  it('resets to exactly 1.0 on Ctrl+0 after nudging up', async () => {
    const { initFontScale } = await import('./fontScale')
    const { getPreferences } = await import('./preferences')
    initFontScale()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '0', ctrlKey: true }))
    expect(getPreferences().fontScale).toBe(1.0)
    expect(document.documentElement.style.fontSize).toBe('16px')
  })

  it('ignores the shortcut when Alt or Meta is held (guard branch)', async () => {
    const { initFontScale } = await import('./fontScale')
    const { getPreferences } = await import('./preferences')
    initFontScale()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true, altKey: true }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true, metaKey: true }))
    // No write happened — scale stays unset (default) and the root px is untouched.
    expect(getPreferences().fontScale).toBeUndefined()
    expect(document.documentElement.style.fontSize).toBe('16px')
  })

  it('round-trips drift-free — Ctrl+= then Ctrl+- returns to exactly 1.0 (FIX A)', async () => {
    const { initFontScale } = await import('./fontScale')
    const { getPreferences } = await import('./preferences')
    initFontScale()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '-', ctrlKey: true }))
    // Strict equality: the 0.05-grid snap kills the 1.0000000000000002 float drift
    // that plain `current + 0.1 - 0.1` would leave behind.
    expect(getPreferences().fontScale).toBe(1.0)
    expect(document.documentElement.style.fontSize).toBe('16px')
  })

  it('is idempotent — calling initFontScale twice does not double-register the listener', async () => {
    const { initFontScale } = await import('./fontScale')
    const { getPreferences } = await import('./preferences')
    initFontScale()
    initFontScale()
    // A double-registered handler would nudge twice (1.0 → 1.2); a single one → 1.1.
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '=', ctrlKey: true }))
    expect(getPreferences().fontScale).toBeCloseTo(1.1)
  })
})
