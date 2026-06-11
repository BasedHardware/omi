import { describe, it, expect } from 'vitest'
import {
  OP_SNAPSHOT,
  OP_STEP,
  PROTOCOL_VERSION,
  encodeRef,
  decodeRef,
  parseAutomationPlan,
  MAX_SNAPSHOT_NODES,
  MAX_SNAPSHOT_DEPTH
} from './protocol'

describe('refs', () => {
  it('prefers automationId', () => {
    expect(encodeRef({ automationId: 'sendBtn', controlType: 'Button', name: 'Send' })).toBe(
      'a:sendBtn'
    )
  })
  it('falls back to controlType:name', () => {
    expect(encodeRef({ automationId: '', controlType: 'Button', name: 'Send' })).toBe(
      'n:Button:Send'
    )
  })
  it('decodes both forms', () => {
    expect(decodeRef('a:sendBtn')).toEqual({ kind: 'automationId', value: 'sendBtn' })
    expect(decodeRef('n:Button:Send')).toEqual({
      kind: 'nameType',
      controlType: 'Button',
      name: 'Send'
    })
  })
  it('decodes names that contain colons', () => {
    expect(decodeRef('n:Edit:To: field')).toEqual({
      kind: 'nameType',
      controlType: 'Edit',
      name: 'To: field'
    })
  })
  it('returns null for malformed refs', () => {
    expect(decodeRef('garbage')).toBeNull()
  })
})

describe('parseAutomationPlan', () => {
  it('parses a valid plan embedded in prose/fences', () => {
    const text =
      'Sure!\n```json\n{"id":"p1","summary":"Type hi","targetWindow":"Notepad",' +
      '"steps":[{"type":"set_value","elementRef":"a:edit","value":"hi"}]}\n```'
    const plan = parseAutomationPlan(text)
    expect(plan).not.toBeNull()
    expect(plan!.steps).toHaveLength(1)
    expect(plan!.steps[0]).toEqual({ type: 'set_value', elementRef: 'a:edit', value: 'hi' })
  })
  it('rejects a plan with an unknown step type', () => {
    const text = '{"id":"p","summary":"x","targetWindow":"w","steps":[{"type":"format_disk"}]}'
    expect(parseAutomationPlan(text)).toBeNull()
  })
  it('rejects a plan with no steps', () => {
    expect(parseAutomationPlan('{"id":"p","summary":"x","targetWindow":"w","steps":[]}')).toBeNull()
  })
  it('returns null when there is no JSON object', () => {
    expect(parseAutomationPlan('I cannot do that.')).toBeNull()
  })
  it('normalizes underscore-dropped / camelCase step types to canonical form', () => {
    // Models routinely emit "focuswindow"/"setValue" instead of snake_case.
    const text =
      '{"id":"p","summary":"x","targetWindow":"Chrome","steps":[' +
      '{"type":"focuswindow","windowRef":"Chrome"},' +
      '{"type":"setValue","elementRef":"a:edit","value":"hi"},' +
      '{"type":"send_keys","keys":"{ENTER}"}]}'
    const plan = parseAutomationPlan(text)
    expect(plan).not.toBeNull()
    expect(plan!.steps.map((s) => s.type)).toEqual(['focus_window', 'set_value', 'send_keys'])
  })
})

describe('constants', () => {
  it('exposes opcodes and caps', () => {
    expect(OP_SNAPSHOT).toBe(1)
    expect(OP_STEP).toBe(2)
    expect(PROTOCOL_VERSION).toBe(1)
    expect(MAX_SNAPSHOT_NODES).toBeGreaterThan(0)
    expect(MAX_SNAPSHOT_DEPTH).toBeGreaterThan(0)
  })
})
