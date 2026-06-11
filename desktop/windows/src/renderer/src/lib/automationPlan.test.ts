import { describe, it, expect } from 'vitest'
import { describePlanSteps, describeStep } from './automationPlan'
import type { AutomationStep } from '../../../shared/types'

describe('describeStep', () => {
  const cases: [AutomationStep, string][] = [
    [{ type: 'focus_window', windowRef: 'Slack' }, 'Focus window “Slack”'],
    [{ type: 'invoke_element', elementRef: 'a:send' }, 'Click “send”'],
    [{ type: 'set_value', elementRef: 'n:Edit:Message', value: 'hi team' }, 'Type “hi team” into “Message”'],
    [{ type: 'send_keys', keys: 'hello{ENTER}' }, 'Type keys: hello{ENTER}'],
    [{ type: 'wait_for', elementRef: 'a:dialog', timeoutMs: 2000 }, 'Wait for “dialog” (up to 2000ms)']
  ]
  it.each(cases)('describes %o', (step, expected) => {
    expect(describeStep(step)).toBe(expected)
  })
})

describe('describePlanSteps', () => {
  it('numbers each step', () => {
    const lines = describePlanSteps([
      { type: 'focus_window', windowRef: 'Notepad' },
      { type: 'set_value', elementRef: 'a:edit', value: 'hi' }
    ])
    expect(lines).toEqual(['1. Focus window “Notepad”', '2. Type “hi” into “edit”'])
  })
})
