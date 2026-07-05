import { describe, it, expect } from 'vitest'
import { validateStep, validatePlan } from './capabilities'
import type { AutomationPlan, AutomationStep } from '../../shared/types'

const ok = (s: AutomationStep): void => expect(validateStep(s).ok).toBe(true)
const bad = (s: AutomationStep): void => expect(validateStep(s).ok).toBe(false)

describe('validateStep', () => {
  it('accepts allowed step types', () => {
    ok({ type: 'focus_window', windowRef: 'Notepad' })
    ok({ type: 'invoke_element', elementRef: 'a:send' })
    ok({ type: 'set_value', elementRef: 'a:edit', value: 'hello' })
    ok({ type: 'wait_for', elementRef: 'a:x', timeoutMs: 1000 })
  })

  it('rejects unknown step types', () => {
    bad({ type: 'nuke' } as unknown as AutomationStep)
  })

  it('accepts plain text and whitelisted named keys in send_keys', () => {
    ok({ type: 'send_keys', keys: 'hello world' })
    ok({ type: 'send_keys', keys: 'line one{ENTER}line two' })
    ok({ type: 'send_keys', keys: 'done{TAB}{ENTER}' })
  })

  it('rejects modifier chords and OS-level keys in send_keys', () => {
    bad({ type: 'send_keys', keys: '^r' }) // Ctrl+R
    bad({ type: 'send_keys', keys: '%{F4}' }) // Alt+F4
    bad({ type: 'send_keys', keys: '#r' }) // Win+R
    bad({ type: 'send_keys', keys: '+{TAB}' }) // Shift modifier syntax
    bad({ type: 'send_keys', keys: '{WIN}' }) // unknown named key
  })

  it('rejects raw-coordinate click by default', () => {
    bad({ type: 'click', point: { x: 10, y: 10 } })
    ok({ type: 'click', elementRef: 'a:btn' })
  })

  it('rejects empty/whitespace value-bearing fields', () => {
    bad({ type: 'invoke_element', elementRef: '' })
    bad({ type: 'focus_window', windowRef: '   ' })
  })

  it('rejects set_value with an empty value', () => {
    bad({ type: 'set_value', elementRef: 'a:edit', value: '' })
    bad({ type: 'set_value', elementRef: 'a:edit', value: '   ' })
  })

  it('rejects fullwidth/unicode modifier lookalikes in send_keys', () => {
    bad({ type: 'send_keys', keys: '＋{TAB}' }) // U+FF0B fullwidth plus normalizes to '+'
  })

  it('enforces wait_for timeout bounds (capped below the bridge timeout)', () => {
    bad({ type: 'wait_for', elementRef: 'a:x', timeoutMs: 0 })
    bad({ type: 'wait_for', elementRef: 'a:x', timeoutMs: 7001 })
    ok({ type: 'wait_for', elementRef: 'a:x', timeoutMs: 7000 })
  })
})

describe('validatePlan', () => {
  it('blocks plans targeting a blocklisted window', () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 's',
      targetWindow: 'Windows Security',
      steps: [{ type: 'invoke_element', elementRef: 'a:ok' }]
    }
    expect(validatePlan(plan).ok).toBe(false)
  })

  it('passes a clean plan', () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 's',
      targetWindow: 'Notepad',
      steps: [{ type: 'set_value', elementRef: 'a:edit', value: 'hi' }]
    }
    expect(validatePlan(plan).ok).toBe(true)
  })

  it('rejects an empty targetWindow', () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 's',
      targetWindow: '',
      steps: [{ type: 'invoke_element', elementRef: 'a:ok' }]
    }
    expect(validatePlan(plan).ok).toBe(false)
  })

  it('fails the plan if any step is invalid', () => {
    const plan: AutomationPlan = {
      id: 'p',
      summary: 's',
      targetWindow: 'Notepad',
      steps: [
        { type: 'set_value', elementRef: 'a:edit', value: 'hi' },
        { type: 'send_keys', keys: '#r' }
      ]
    }
    const r = validatePlan(plan)
    expect(r.ok).toBe(false)
    expect(r.ok ? '' : r.reason).toMatch(/step 1/)
  })
})
