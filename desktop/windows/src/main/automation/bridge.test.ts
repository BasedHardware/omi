import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AutomationPlan, AutomationStep, StepResult } from '../../shared/types'

const spawnMock = vi.hoisted(() => vi.fn())

vi.mock('child_process', () => ({
  spawn: spawnMock
}))

import { automationBridge } from './bridge'

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
})
