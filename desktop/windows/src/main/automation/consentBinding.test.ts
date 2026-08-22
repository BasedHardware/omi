import { describe, expect, it } from 'vitest'
import { bindPlanToWindow, sameWindowIdentity } from './consentBinding'
import type { AutomationPlan, UiSnapshotWindow } from '../../shared/types'

const windowInfo = (patch: Partial<UiSnapshotWindow> = {}): UiSnapshotWindow => ({
  handle: '42',
  title: 'Notepad',
  processName: 'notepad.exe',
  rect: { x: 0, y: 0, w: 800, h: 600 },
  ...patch
})

describe('automation consent binding', () => {
  it('replaces renderer window labels and refs with the native identity', () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 'type text',
      targetWindow: 'Password Manager',
      steps: [
        { type: 'focus_window', windowRef: 'attacker-ref' },
        { type: 'send_keys', keys: 'hello' }
      ]
    }
    expect(bindPlanToWindow(plan, windowInfo())).toMatchObject({
      targetWindow: 'Notepad',
      steps: [
        { type: 'focus_window', windowRef: '42' },
        { type: 'send_keys', keys: 'hello' }
      ]
    })
  })

  it('prepends a native focus step when the model omitted one', () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 'type text',
      targetWindow: 'anything',
      steps: [{ type: 'send_keys', keys: 'hello' }]
    }
    expect(bindPlanToWindow(plan, windowInfo()).steps[0]).toEqual({
      type: 'focus_window',
      windowRef: '42'
    })
  })

  it('rejects handle reuse by a different process', () => {
    expect(sameWindowIdentity(windowInfo(), windowInfo({ title: 'Untitled - Notepad' }))).toBe(true)
    expect(sameWindowIdentity(windowInfo(), windowInfo({ processName: 'vault.exe' }))).toBe(false)
    expect(sameWindowIdentity(windowInfo(), windowInfo({ handle: '99' }))).toBe(false)
  })
})
