import { describe, it, expect, beforeEach, vi } from 'vitest'

// In-memory globalShortcut stand-in. `taken` simulates accelerators another app
// already owns (register returns false for those).
const registered = new Set<string>()
const taken = new Set<string>()

vi.mock('electron', () => ({
  globalShortcut: {
    register: (accel: string): boolean => {
      if (taken.has(accel)) return false
      registered.add(accel)
      return true
    },
    unregister: (accel: string): void => {
      registered.delete(accel)
    },
    isRegistered: (accel: string): boolean => registered.has(accel)
  }
}))

import {
  registerOverlayShortcut,
  setOverlayAccelerator,
  suspendOverlayShortcut,
  resumeOverlayShortcut,
  getOverlayAccelerator,
  OVERLAY_ACCELERATOR
} from './shortcut'

describe('overlay shortcut manager', () => {
  beforeEach(() => {
    registered.clear()
    taken.clear()
  })

  it('claims the default accelerator on register', () => {
    expect(registerOverlayShortcut(OVERLAY_ACCELERATOR, () => {})).toBe(true)
    expect(registered.has('Shift+Space')).toBe(true)
    expect(getOverlayAccelerator()).toBe('Shift+Space')
  })

  it('rebinds: releases the old accelerator and claims the new one', () => {
    registerOverlayShortcut('Shift+Space', () => {})
    expect(setOverlayAccelerator('CommandOrControl+J')).toBe(true)
    expect(registered.has('Shift+Space')).toBe(false)
    expect(registered.has('CommandOrControl+J')).toBe(true)
    expect(getOverlayAccelerator()).toBe('CommandOrControl+J')
  })

  it('rolls back to the previous binding when the new accelerator is taken', () => {
    registerOverlayShortcut('CommandOrControl+J', () => {})
    taken.add('CommandOrControl+O') // owned by another app
    expect(setOverlayAccelerator('CommandOrControl+O')).toBe(false)
    // Previous binding restored and still registered.
    expect(getOverlayAccelerator()).toBe('CommandOrControl+J')
    expect(registered.has('CommandOrControl+J')).toBe(true)
    expect(registered.has('CommandOrControl+O')).toBe(false)
  })

  it('suspend releases the current accelerator; resume re-claims it', () => {
    registerOverlayShortcut('Shift+Space', () => {})
    suspendOverlayShortcut()
    expect(registered.has('Shift+Space')).toBe(false)
    expect(resumeOverlayShortcut()).toBe(true)
    expect(registered.has('Shift+Space')).toBe(true)
  })
})
