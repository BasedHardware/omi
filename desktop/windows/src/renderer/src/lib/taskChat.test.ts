// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ActionItemRecord } from '../../../shared/types'
import {
  TASK_CHAT_MAX_MESSAGES,
  buildTaskChatPreamble,
  buildTaskChatPrompt,
  clearTaskChat,
  loadTaskChat,
  saveTaskChat,
  sendTaskChatMessage,
  type TaskChatMessage
} from './taskChat'

const task = (over: Partial<ActionItemRecord> = {}): ActionItemRecord =>
  ({
    id: 1,
    backendId: 'b-1',
    backendSynced: true,
    description: 'Reply to Sarah about the Q3 report',
    completed: false,
    deleted: false,
    deletedBy: null,
    source: 'conversation',
    conversationId: 'conv-9',
    priority: 'high',
    category: 'work',
    tags: [],
    dueAt: null,
    screenshotId: null,
    confidence: null,
    sourceApp: 'Slack',
    windowTitle: '#reports',
    contextSummary: 'Sarah asked for the Q3 numbers by Friday',
    currentActivity: null,
    metadataJson: null,
    createdAt: 1,
    updatedAt: 1,
    ...over
  }) as ActionItemRecord

const msg = (role: 'user' | 'assistant', content: string): TaskChatMessage => ({
  role,
  content,
  at: 1
})

beforeEach(() => {
  window.localStorage.clear()
})

describe('transcript persistence', () => {
  it('round-trips a transcript keyed by backendId', () => {
    saveTaskChat('b-1', [msg('user', 'hello'), msg('assistant', 'hi')])
    expect(loadTaskChat('b-1')).toEqual([msg('user', 'hello'), msg('assistant', 'hi')])
    expect(loadTaskChat('b-2')).toEqual([])
  })

  it('is a no-op without a backendId (unsynced task)', () => {
    saveTaskChat(null, [msg('user', 'hello')])
    expect(loadTaskChat(null)).toEqual([])
  })

  it('drops malformed stored entries instead of crashing', () => {
    window.localStorage.setItem(
      'omi.taskChat.v1.b-1',
      JSON.stringify([msg('user', 'ok'), { role: 'user' }, 'junk', null])
    )
    expect(loadTaskChat('b-1')).toEqual([msg('user', 'ok')])
    window.localStorage.setItem('omi.taskChat.v1.b-1', '{not json')
    expect(loadTaskChat('b-1')).toEqual([])
  })

  it('caps the stored transcript at TASK_CHAT_MAX_MESSAGES, keeping the newest', () => {
    const long = Array.from({ length: TASK_CHAT_MAX_MESSAGES + 10 }, (_, i) => msg('user', `m${i}`))
    saveTaskChat('b-1', long)
    const stored = loadTaskChat('b-1')
    expect(stored).toHaveLength(TASK_CHAT_MAX_MESSAGES)
    expect(stored[stored.length - 1].content).toBe(`m${TASK_CHAT_MAX_MESSAGES + 9}`)
  })

  it('clearTaskChat removes the stored transcript', () => {
    saveTaskChat('b-1', [msg('user', 'hello')])
    clearTaskChat('b-1')
    expect(loadTaskChat('b-1')).toEqual([])
  })
})

describe('prompt building', () => {
  it('preamble carries the task, schedule, priority, and captured source context', () => {
    const p = buildTaskChatPreamble(task({ dueAt: Date.UTC(2026, 7, 20, 12) }))
    expect(p).toContain('Reply to Sarah about the Q3 report')
    expect(p).toContain('Priority: high')
    expect(p).toContain('Captured from: Slack — #reports')
    expect(p).toContain('Captured context: Sarah asked for the Q3 numbers by Friday')
    expect(p).toContain('Origin: conversation conv-9')
    expect(p).not.toContain('no due date')
  })

  it('omits absent metadata lines rather than printing empty fields', () => {
    const p = buildTaskChatPreamble(
      task({
        priority: null,
        category: null,
        sourceApp: null,
        windowTitle: null,
        contextSummary: null,
        conversationId: null
      })
    )
    expect(p).toContain('Due: no due date')
    expect(p).not.toContain('Priority:')
    expect(p).not.toContain('Captured from:')
    expect(p).not.toContain('Origin:')
  })

  it('replays history in order and ends with the open user turn', () => {
    const p = buildTaskChatPrompt(
      task(),
      [msg('user', 'first'), msg('assistant', 'reply')],
      'second',
      ''
    )
    const first = p.indexOf('User: first')
    const reply = p.indexOf('Omi: reply')
    const second = p.indexOf('User: second')
    expect(first).toBeGreaterThan(-1)
    expect(reply).toBeGreaterThan(first)
    expect(second).toBeGreaterThan(reply)
    expect(p.trimEnd().endsWith('Omi:')).toBe(true)
  })

  it('includes local context only when non-empty', () => {
    expect(buildTaskChatPrompt(task(), [], 'q', 'CTX-42')).toContain('Relevant local context:')
    expect(buildTaskChatPrompt(task(), [], 'q', '')).not.toContain('Relevant local context:')
  })
})

describe('sendTaskChatMessage', () => {
  it('appends the user turn and the model reply, persisting both', async () => {
    const callLLM = vi.fn().mockResolvedValue('  do the thing  ')
    const gatherContext = vi.fn().mockResolvedValue('ctx')
    const out = await sendTaskChatMessage(task(), [], 'help me', { callLLM, gatherContext })
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({ role: 'user', content: 'help me' })
    expect(out[1]).toMatchObject({ role: 'assistant', content: 'do the thing' })
    expect(callLLM).toHaveBeenCalledTimes(1)
    expect(String(callLLM.mock.calls[0][0])).toContain('Relevant local context:\nctx')
    expect(loadTaskChat('b-1')).toHaveLength(2)
  })

  it('ignores a blank send', async () => {
    const callLLM = vi.fn()
    const out = await sendTaskChatMessage(task(), [], '   ', { callLLM })
    expect(out).toEqual([])
    expect(callLLM).not.toHaveBeenCalled()
  })

  it('keeps the user turn persisted when the LLM call fails, and rethrows', async () => {
    const callLLM = vi.fn().mockRejectedValue(new Error('llm down'))
    const gatherContext = vi.fn().mockResolvedValue('')
    await expect(
      sendTaskChatMessage(task(), [], 'help me', { callLLM, gatherContext })
    ).rejects.toThrow('llm down')
    const stored = loadTaskChat('b-1')
    expect(stored).toHaveLength(1)
    expect(stored[0]).toMatchObject({ role: 'user', content: 'help me' })
  })

  it('treats an empty model reply as a failed send (retry stays available)', async () => {
    const callLLM = vi.fn().mockResolvedValue('   ')
    const gatherContext = vi.fn().mockResolvedValue('')
    await expect(
      sendTaskChatMessage(task(), [], 'help me', { callLLM, gatherContext })
    ).rejects.toThrow('empty model reply')
    // The user's turn stays persisted, exactly like a transport failure.
    expect(loadTaskChat('b-1')).toHaveLength(1)
  })

  it('returns the bounded transcript once the cap is reached', async () => {
    const callLLM = vi.fn().mockResolvedValue('ok')
    const gatherContext = vi.fn().mockResolvedValue('')
    const long = Array.from({ length: TASK_CHAT_MAX_MESSAGES }, (_, i) => msg('user', `m${i}`))
    const out = await sendTaskChatMessage(task(), long, 'newest', { callLLM, gatherContext })
    expect(out).toHaveLength(TASK_CHAT_MAX_MESSAGES)
    expect(out[out.length - 1]).toMatchObject({ role: 'assistant', content: 'ok' })
    expect(out[out.length - 2]).toMatchObject({ role: 'user', content: 'newest' })
  })

  it('survives a context-gather failure (degrades to no context)', async () => {
    const callLLM = vi.fn().mockResolvedValue('ok')
    const gatherContext = vi.fn().mockRejectedValue(new Error('kg down'))
    const out = await sendTaskChatMessage(task(), [], 'q', { callLLM, gatherContext })
    expect(out).toHaveLength(2)
    expect(String(callLLM.mock.calls[0][0])).not.toContain('Relevant local context:')
  })
})
