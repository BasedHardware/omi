import { describe, it, expect, vi } from 'vitest'
import {
  buildTrayMenuTemplate,
  describeTray,
  isTrayState,
  TRAY_STATES,
  type TrayMenuActions
} from './trayState'

describe('trayState', () => {
  it('lists exactly the three states', () => {
    expect(TRAY_STATES).toEqual(['idle', 'listening', 'paused'])
  })

  it('isTrayState only accepts the three known states', () => {
    expect(isTrayState('idle')).toBe(true)
    expect(isTrayState('listening')).toBe(true)
    expect(isTrayState('paused')).toBe(true)
    expect(isTrayState('recording')).toBe(false)
    expect(isTrayState(undefined)).toBe(false)
    expect(isTrayState(2)).toBe(false)
  })

  it('listening offers Pause', () => {
    const p = describeTray('listening')
    expect(p.tooltip).toBe('Omi — listening')
    expect(p.toggleLabel).toBe('Pause listening')
  })

  it('paused offers Resume', () => {
    const p = describeTray('paused')
    expect(p.tooltip).toBe('Omi — paused')
    expect(p.toggleLabel).toBe('Resume listening')
  })

  it('idle offers Resume (nothing to pause yet)', () => {
    const p = describeTray('idle')
    expect(p.tooltip).toBe('Omi')
    expect(p.toggleLabel).toBe('Resume listening')
  })

  it('appends an update-ready suffix to the tooltip when staged', () => {
    expect(describeTray('listening', { updateReady: true }).tooltip).toBe(
      'Omi — listening · update ready'
    )
    expect(describeTray('idle', { updateReady: true }).tooltip).toBe('Omi · update ready')
    // Non-tooltip fields are unchanged by the update flag.
    expect(describeTray('paused', { updateReady: true }).toggleLabel).toBe('Resume listening')
  })

  it('every tooltip stays under the Windows 127-char limit', () => {
    for (const s of TRAY_STATES) {
      expect(describeTray(s, { updateReady: true }).tooltip.length).toBeLessThan(127)
    }
  })
})

describe('buildTrayMenuTemplate', () => {
  const noopActions = (): TrayMenuActions => ({
    showMainWindow: vi.fn(),
    toggleListening: vi.fn(),
    openSettings: vi.fn(),
    checkForUpdates: vi.fn(),
    toggleScreenCapture: vi.fn(),
    quit: vi.fn()
  })

  // A menu item's label with the runtime-narrowed shape the template produces.
  type Item = { label?: string; type?: string; checked?: boolean; click?: () => void }
  const labels = (items: Item[]): (string | undefined)[] =>
    items.filter((i) => i.type !== 'separator').map((i) => i.label)
  const byLabel = (items: Item[], label: string): Item =>
    items.find((i) => i.label === label) as Item

  it('lists all items in Mac order (capture toggle first, updates before quit)', () => {
    const items = buildTrayMenuTemplate(
      { toggleLabel: 'Pause listening', screenCaptureEnabled: true },
      noopActions()
    ) as Item[]
    expect(labels(items)).toEqual([
      'Screen Analysis',
      'Open Omi',
      'Pause listening',
      'Settings',
      'Check for Updates',
      'Quit Omi'
    ])
  })

  it('uses the passed pause/resume label', () => {
    const items = buildTrayMenuTemplate(
      { toggleLabel: 'Resume listening', screenCaptureEnabled: false },
      noopActions()
    ) as Item[]
    expect(labels(items)).toContain('Resume listening')
    expect(labels(items)).not.toContain('Pause listening')
  })

  it('renders Screen Analysis as a checkbox reflecting the enabled state', () => {
    const on = byLabel(
      buildTrayMenuTemplate(
        { toggleLabel: 'Pause listening', screenCaptureEnabled: true },
        noopActions()
      ) as Item[],
      'Screen Analysis'
    )
    expect(on.type).toBe('checkbox')
    expect(on.checked).toBe(true)

    const off = byLabel(
      buildTrayMenuTemplate(
        { toggleLabel: 'Pause listening', screenCaptureEnabled: false },
        noopActions()
      ) as Item[],
      'Screen Analysis'
    )
    expect(off.type).toBe('checkbox')
    expect(off.checked).toBe(false)
  })

  it('routes each click to its injected action', () => {
    const actions = noopActions()
    const items = buildTrayMenuTemplate(
      { toggleLabel: 'Pause listening', screenCaptureEnabled: true },
      actions
    ) as Item[]
    byLabel(items, 'Screen Analysis').click?.()
    byLabel(items, 'Open Omi').click?.()
    byLabel(items, 'Pause listening').click?.()
    byLabel(items, 'Settings').click?.()
    byLabel(items, 'Check for Updates').click?.()
    byLabel(items, 'Quit Omi').click?.()
    expect(actions.toggleScreenCapture).toHaveBeenCalledOnce()
    expect(actions.showMainWindow).toHaveBeenCalledOnce()
    expect(actions.toggleListening).toHaveBeenCalledOnce()
    expect(actions.openSettings).toHaveBeenCalledOnce()
    expect(actions.checkForUpdates).toHaveBeenCalledOnce()
    expect(actions.quit).toHaveBeenCalledOnce()
  })
})
