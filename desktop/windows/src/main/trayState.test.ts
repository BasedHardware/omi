import { describe, it, expect } from 'vitest'
import { describeTray, isTrayState, TRAY_STATES } from './trayState'

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
