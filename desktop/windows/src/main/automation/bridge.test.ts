import { EventEmitter } from 'node:events'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AutomationPlan, AutomationStep, StepResult } from '../../shared/types'

const spawnMock = vi.hoisted(() => vi.fn())

vi.mock('child_process', () => ({
  spawn: spawnMock
}))
vi.mock('./resolveHelperPath', () => ({
  resolveHelperPath: () => 'C:\\fake\\win-automation-helper.exe'
}))

import { automationBridge } from './bridge'

function makeFakeChild(): EventEmitter & {
  stdout: EventEmitter
  stderr: EventEmitter
  stdin: { write: ReturnType<typeof vi.fn> }
  kill: ReturnType<typeof vi.fn>
} {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter
    stderr: EventEmitter
    stdin: { write: ReturnType<typeof vi.fn> }
    kill: ReturnType<typeof vi.fn>
  }
  child.stdout = new EventEmitter()
  child.stderr = new EventEmitter()
  child.stdin = { write: vi.fn() }
  child.kill = vi.fn()
  return child
}

afterEach(() => {
  automationBridge.dispose()
  spawnMock.mockClear()
})

describe('AutomationBridge.run', () => {
  it('rejects malformed send_keys plans before starting the helper', async () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 's',
      targetWindow: 'Notepad',
      steps: [{ type: 'send_keys' } as unknown as AutomationStep]
    }
    const steps: StepResult[] = []

    const result = await automationBridge.run(plan, (step) => steps.push(step))

    expect(result).toEqual({ planId: 'p', ok: false, message: 'rejected: step 0: keys is empty' })
    expect(steps).toEqual([])
    expect(spawnMock).not.toHaveBeenCalled()
  })

  it('spawns the helper with windowsHide so no stray console window appears', () => {
    spawnMock.mockReturnValue(makeFakeChild())
    // snapshot() lazily spawns the helper via ensureStarted(); we never resolve
    // the request, we only inspect how the child was spawned.
    void automationBridge.snapshot().catch(() => {})
    expect(spawnMock).toHaveBeenCalledTimes(1)
    // The helper is a console-subsystem exe; without windowsHide it flashes a
    // stray console window in the taskbar when launched from GUI Electron main.
    expect(spawnMock.mock.calls[0][2]).toMatchObject({ windowsHide: true })
  })
})
