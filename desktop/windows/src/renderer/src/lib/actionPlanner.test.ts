import { describe, it, expect, vi } from 'vitest'
import { looksLikeAction, looksLikeRawPlan, planActions } from './actionPlanner'
import type { UiSnapshot } from '../../../shared/types'

const snapshot: UiSnapshot = {
  ok: true,
  window: { handle: '123', title: 'Notepad', processName: 'notepad', rect: { x: 0, y: 0, w: 10, h: 10 } },
  elements: [
    {
      ref: 'a:edit',
      controlType: 'Edit',
      name: 'Text editor',
      automationId: 'edit',
      rect: { x: 0, y: 0, w: 10, h: 10 },
      patterns: ['value'],
      enabled: true
    },
    {
      ref: 'a:btn',
      controlType: 'Button',
      name: 'Save',
      automationId: 'btn',
      rect: { x: 0, y: 0, w: 10, h: 10 },
      patterns: ['invoke'],
      enabled: true
    }
  ]
}

describe('looksLikeAction', () => {
  it('is false with no action keyword', () => {
    expect(looksLikeAction('what is the capital of France?')).toBe(false)
  })
  it('is true when an action keyword is present', () => {
    expect(looksLikeAction('send a message to the team in Slack')).toBe(true)
    expect(looksLikeAction('type something here')).toBe(true)
    expect(looksLikeAction('click the submit button')).toBe(true)
    expect(looksLikeAction('open settings')).toBe(true)
  })
  it('is false for guidance questions even when they contain an action word', () => {
    expect(looksLikeAction('where should I click?')).toBe(false)
    expect(looksLikeAction('where do I have to click?')).toBe(false)
    expect(looksLikeAction('what should I type here?')).toBe(false)
    expect(looksLikeAction('how do I send this?')).toBe(false)
    expect(looksLikeAction('which button do I click to submit?')).toBe(false)
    expect(looksLikeAction('should I click save?')).toBe(false)
  })
})

describe('looksLikeRawPlan', () => {
  it('flags raw plan-shaped JSON leaking from the chat backend', () => {
    const leaked =
      '{"id":"x","summary":"Type report","targetWindow":"Inicio - Explorador de archivos","steps":[{"type":"focuswindow","windowRef":"x"},{"type":"setvalue","elementRef":"a:TextBox","value":"report"}]}'
    expect(looksLikeRawPlan(leaked)).toBe(true)
    expect(looksLikeRawPlan('  \n' + leaked)).toBe(true)
  })
  it('does not flag ordinary chat replies', () => {
    expect(looksLikeRawPlan('Here are your tasks: 1. Sign the docs…')).toBe(false)
    expect(looksLikeRawPlan('{"foo":"bar"}')).toBe(false)
    expect(looksLikeRawPlan('I think the steps to bake bread are…')).toBe(false)
  })
})

describe('planActions', () => {
  it('fetches a snapshot and returns the parsed plan in one LLM call', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi.fn().mockResolvedValue(
      '{"id":"p1","summary":"Type hi","targetWindow":"Notepad",' +
        '"steps":[{"type":"set_value","elementRef":"a:edit","value":"hi"}]}'
    )
    const result = await planActions('type hi in notepad', { getSnapshot, callLLM: llm })
    expect(result.ok).toBe(true)
    // A focus step targeting the snapshotted window (by handle) is prepended, then
    // the model's step follows.
    expect(result.ok && result.plan.steps).toEqual([
      { type: 'focus_window', windowRef: '123' },
      { type: 'set_value', elementRef: 'a:edit', value: 'hi' }
    ])
    // The snapshot must be in the prompt so the model can reference refs, and it
    // must be a SINGLE call (intent + plan folded together).
    expect(llm).toHaveBeenCalledOnce()
    expect(llm.mock.calls[0][0]).toContain('a:edit')
  })

  it('prepends a focus step even when the model omits one (so refs resolve)', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"p","summary":"click","targetWindow":"Notepad","steps":[{"type":"invoke_element","elementRef":"a:btn"}]}')
    const result = await planActions('click save', { getSnapshot, callLLM: llm })
    expect(result.ok).toBe(true)
    expect(result.ok && result.plan.steps[0]).toEqual({ type: 'focus_window', windowRef: '123' })
    expect(result.ok && result.plan.steps[1]).toEqual({ type: 'invoke_element', elementRef: 'a:btn' })
  })

  it('replaces a model-supplied focus step with the exact snapshot handle', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"p","summary":"s","targetWindow":"Notepad","steps":[{"type":"focus_window","windowRef":"Notepad"},{"type":"invoke_element","elementRef":"a:btn"}]}')
    const result = await planActions('click save', { getSnapshot, callLLM: llm })
    expect(result.ok).toBe(true)
    expect(result.ok && result.plan.steps).toEqual([
      { type: 'focus_window', windowRef: '123' },
      { type: 'invoke_element', elementRef: 'a:btn' }
    ])
  })

  it('rewrites invoke_element → click when the target lacks the invoke pattern', async () => {
    // Regression (test 4 / Settings search box): model "clicked" a value-only
    // text box via invoke_element → "Invoke not supported" at execute time.
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"p","summary":"s","targetWindow":"Notepad","steps":[{"type":"invoke_element","elementRef":"a:edit"},{"type":"set_value","elementRef":"a:edit","value":"hi"}]}')
    const result = await planActions('type hi', { getSnapshot, callLLM: llm })
    expect(result.ok).toBe(true)
    expect(result.ok && result.plan.steps).toEqual([
      { type: 'focus_window', windowRef: '123' },
      { type: 'click', elementRef: 'a:edit' },
      { type: 'set_value', elementRef: 'a:edit', value: 'hi' }
    ])
  })

  it('returns kind:error when set_value targets an element without the value pattern', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"p","summary":"s","targetWindow":"Notepad","steps":[{"type":"set_value","elementRef":"a:btn","value":"x"}]}')
    const result = await planActions('type x', { getSnapshot, callLLM: llm })
    expect(result.ok === false && result.kind).toBe('error')
    expect(result.ok === false && result.reason).toContain('value')
  })

  it('returns kind:chat when the model declines with CHAT', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi.fn().mockResolvedValue('CHAT')
    const result = await planActions('what time is it', { getSnapshot, callLLM: llm })
    expect(result).toEqual({ ok: false, kind: 'chat', reason: expect.any(String) })
  })

  it('returns kind:chat for a prose decline (no plan shape)', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi.fn().mockResolvedValue('I cannot help with that.')
    const result = await planActions('do it', { getSnapshot, callLLM: llm })
    expect(result.ok).toBe(false)
    expect(result.ok === false && result.kind).toBe('chat')
  })

  it('returns kind:error (not chat) when plan-shaped JSON fails to validate', async () => {
    // Regression: the model emitted plan-shaped JSON with a bogus step type.
    // It must NOT fall through to chat (which leaked raw JSON into the thread).
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"x","summary":"s","targetWindow":"Notepad","steps":[{"type":"frobnicate"}]}')
    const result = await planActions('do it', { getSnapshot, callLLM: llm })
    expect(result.ok === false && result.kind).toBe('error')
  })

  it('normalizes underscore-dropped step types into a valid plan', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"p","summary":"s","targetWindow":"Notepad","steps":[{"type":"setvalue","elementRef":"a:edit","value":"hi"}]}')
    const result = await planActions('type hi', { getSnapshot, callLLM: llm })
    expect(result.ok).toBe(true)
    // steps[0] is the prepended focus; the normalized model step follows.
    expect(result.ok && result.plan.steps[1].type).toBe('set_value')
  })

  it('returns kind:error when a step references an element not in the snapshot', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi
      .fn()
      .mockResolvedValue('{"id":"p","summary":"s","targetWindow":"Notepad","steps":[{"type":"set_value","elementRef":"address-bar","value":"hi"}]}')
    const result = await planActions('type hi', { getSnapshot, callLLM: llm })
    expect(result.ok === false && result.kind).toBe('error')
    expect(result.ok === false && result.reason).toContain('address-bar')
  })

  it('returns kind:error when the snapshot fails (cannot read the screen)', async () => {
    const getSnapshot = vi.fn().mockResolvedValue({ ok: false, code: 'NO_WINDOW', message: 'none' })
    const llm = vi.fn()
    const result = await planActions('do it', { getSnapshot, callLLM: llm })
    expect(result.ok === false && result.kind).toBe('error')
    expect(llm).not.toHaveBeenCalled()
  })

  it('returns kind:error when the planner LLM call throws (e.g. a 429)', async () => {
    const getSnapshot = vi.fn().mockResolvedValue(snapshot)
    const llm = vi.fn().mockRejectedValue(new Error('HTTP 429'))
    const result = await planActions('send it', { getSnapshot, callLLM: llm })
    expect(result.ok === false && result.kind).toBe('error')
  })
})
