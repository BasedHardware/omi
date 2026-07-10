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
  createShortcutSlot,
  registerRecordShortcut,
  setRecordAccelerator,
  getRecordShortcut,
  __resetRecordShortcutForTests,
  DEFAULT_RECORD_HOTKEY
} from './shortcuts'

describe('createShortcutSlot', () => {
  beforeEach(() => {
    registered.clear()
    taken.clear()
  })

  it('claims the default accelerator on register', () => {
    const slot = createShortcutSlot('Shift+Space')
    expect(slot.register(() => {})).toBe(true)
    expect(slot.getAccelerator()).toBe('Shift+Space')
    expect(slot.isRegistered()).toBe(true)
  })

  it('register(onFire, accelerator) claims the requested accelerator, not the default', () => {
    const slot = createShortcutSlot('Shift+Space')
    expect(slot.register(() => {}, 'Ctrl+K')).toBe(true)
    expect(slot.getAccelerator()).toBe('Ctrl+K')
    expect(registered.has('Ctrl+K')).toBe(true)
    expect(registered.has('Shift+Space')).toBe(false)
  })

  it('register(onFire, accelerator) rolls back to the default when the requested chord is taken', () => {
    taken.add('Ctrl+O')
    const slot = createShortcutSlot('Shift+Space')
    expect(slot.register(() => {}, 'Ctrl+O')).toBe(false)
    expect(slot.getAccelerator()).toBe('Shift+Space') // fell back to the default
    expect(registered.has('Shift+Space')).toBe(true)
    expect(registered.has('Ctrl+O')).toBe(false)
  })

  it('does not register before a handler is attached', () => {
    const slot = createShortcutSlot('Ctrl+J')
    // No register() call yet → resume can't claim it (no handler).
    expect(slot.resume()).toBe(false)
    expect(registered.has('Ctrl+J')).toBe(false)
  })

  it('rebinds and rolls back when the target is taken', () => {
    const slot = createShortcutSlot('Ctrl+J')
    slot.register(() => {})
    expect(slot.setAccelerator('Ctrl+K')).toBe(true)
    expect(slot.getAccelerator()).toBe('Ctrl+K')
    taken.add('Ctrl+O')
    expect(slot.setAccelerator('Ctrl+O')).toBe(false)
    expect(slot.getAccelerator()).toBe('Ctrl+K') // rolled back
    expect(registered.has('Ctrl+K')).toBe(true)
    expect(registered.has('Ctrl+O')).toBe(false)
  })

  it('suspend releases the accelerator; resume re-claims it', () => {
    const slot = createShortcutSlot('Shift+Space')
    slot.register(() => {})
    slot.suspend()
    expect(registered.has('Shift+Space')).toBe(false)
    expect(slot.resume()).toBe(true)
    expect(registered.has('Shift+Space')).toBe(true)
  })
})

describe('record shortcut', () => {
  beforeEach(() => {
    registered.clear()
    taken.clear()
    __resetRecordShortcutForTests()
  })

  it('reports registered=false and the default before any registration', () => {
    expect(getRecordShortcut()).toEqual({ accelerator: DEFAULT_RECORD_HOTKEY, registered: false })
  })

  it('claims the persisted accelerator on registration', () => {
    const fired: number[] = []
    const state = registerRecordShortcut('Ctrl+Space', () => fired.push(1))
    expect(state).toEqual({ accelerator: 'Ctrl+Space', registered: true })
    expect(getRecordShortcut()).toEqual({ accelerator: 'Ctrl+Space', registered: true })
  })

  it('surfaces registered=false when the chord is owned by another app', () => {
    taken.add('Ctrl+Space')
    const state = registerRecordShortcut('Ctrl+Space', () => {})
    expect(state.registered).toBe(false)
    expect(getRecordShortcut().registered).toBe(false)
  })

  it('rebinds the record chord and never throws on a conflict', () => {
    registerRecordShortcut('Ctrl+Space', () => {})
    expect(setRecordAccelerator('Ctrl+Shift+O')).toEqual({
      accelerator: 'Ctrl+Shift+O',
      registered: true
    })
    taken.add('Ctrl+Alt+P')
    const rolledBack = setRecordAccelerator('Ctrl+Alt+P')
    expect(rolledBack.registered).toBe(false)
    expect(rolledBack.accelerator).toBe('Ctrl+Shift+O') // previous binding kept
  })
})
