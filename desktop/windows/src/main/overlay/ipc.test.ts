import { describe, it, expect, vi, beforeEach } from 'vitest'

// Regression: onboarding's ShortcutSetupStep rebinds the summon chord through
// the legacy `overlay:setAccelerator` IPC channel — the same channel Settings
// uses — but until this fix it only updated the in-memory shortcut slot, never
// appSettings.summonHotkey. A chord set during onboarding then reverted to the
// stale default on the next launch (main re-registers from appSettings at
// boot), silently reintroducing the "shortcut owned by another app" conflict
// for anyone who never opens Settings → Shortcuts. This test proves the legacy
// channel now persists main-side too.

const h = vi.hoisted(() => {
  const ipcHandlers = new Map<string, (...args: unknown[]) => unknown>()
  const ipcOnHandlers = new Map<string, (...args: unknown[]) => unknown>()
  return { ipcHandlers, ipcOnHandlers, settingsPatches: [] as Array<Record<string, unknown>> }
})

vi.mock('electron', () => ({
  ipcMain: {
    handle: (ch: string, fn: (...args: unknown[]) => unknown) => h.ipcHandlers.set(ch, fn),
    on: (ch: string, fn: (...args: unknown[]) => unknown) => h.ipcOnHandlers.set(ch, fn)
  },
  BrowserWindow: { getAllWindows: () => [] }
}))

vi.mock('../bar/window', () => ({
  hideBar: vi.fn(),
  setBarEnabled: vi.fn(),
  setSummonGestureAccelerator: vi.fn()
}))

vi.mock('../appSettings', () => ({
  setAppSettings: (patch: Record<string, unknown>) => {
    h.settingsPatches.push(patch)
    return patch
  }
}))

vi.mock('./shortcut', () => ({
  setOverlayAccelerator: (accel: string) => accel !== 'taken',
  suspendOverlayShortcut: vi.fn(),
  resumeOverlayShortcut: vi.fn(),
  getOverlayAccelerator: () => 'CommandOrControl+J'
}))

import { registerOverlayHandlers } from './ipc'

describe('overlay:setAccelerator IPC (legacy onboarding rebind path)', () => {
  beforeEach(() => {
    h.ipcHandlers.clear()
    h.ipcOnHandlers.clear()
    h.settingsPatches.length = 0
    registerOverlayHandlers(() => {})
  })

  it('persists the new accelerator to appSettings.summonHotkey on success', async () => {
    const handler = h.ipcHandlers.get('overlay:setAccelerator')!
    const ok = await handler({}, 'CommandOrControl+J')
    expect(ok).toBe(true)
    expect(h.settingsPatches).toContainEqual({ summonHotkey: 'CommandOrControl+J' })
  })

  it('does not touch appSettings when the accelerator is already taken', async () => {
    const handler = h.ipcHandlers.get('overlay:setAccelerator')!
    const ok = await handler({}, 'taken')
    expect(ok).toBe(false)
    expect(h.settingsPatches).toEqual([])
  })
})
