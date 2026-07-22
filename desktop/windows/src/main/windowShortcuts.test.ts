import { describe, it, expect } from 'vitest'
import { isHideWindowShortcut, type KeyboardInput } from './windowShortcuts'

// A fully-modifier-free keyDown of a given key; spread over per-test overrides.
const input = (over: Partial<KeyboardInput> = {}): KeyboardInput => ({
  type: 'keyDown',
  key: 'w',
  control: false,
  alt: false,
  meta: false,
  ...over
})

describe('isHideWindowShortcut', () => {
  it('matches Ctrl+W on keyDown', () => {
    expect(isHideWindowShortcut(input({ control: true }))).toBe(true)
  })

  it('is case-insensitive on the key (some layouts report uppercase)', () => {
    expect(isHideWindowShortcut(input({ control: true, key: 'W' }))).toBe(true)
  })

  // The whole point of gating on keyDown: keyUp must not fire a second hide.
  it('ignores the keyUp half of the keystroke', () => {
    expect(isHideWindowShortcut(input({ control: true, type: 'keyUp' }))).toBe(false)
  })

  // Ctrl+Alt is AltGr on some layouts — a character key, not a shortcut.
  it('does not match Ctrl+Alt+W (AltGr)', () => {
    expect(isHideWindowShortcut(input({ control: true, alt: true }))).toBe(false)
  })

  it('does not match Cmd/Meta+W', () => {
    expect(isHideWindowShortcut(input({ meta: true }))).toBe(false)
    expect(isHideWindowShortcut(input({ control: true, meta: true }))).toBe(false)
  })

  it('does not match W without Ctrl, nor other Ctrl keys', () => {
    expect(isHideWindowShortcut(input({ control: false }))).toBe(false)
    expect(isHideWindowShortcut(input({ control: true, key: 'q' }))).toBe(false)
  })
})
