// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import type { ChatMessage, MainChatEvent, MainChatSendArgs } from '../../../shared/types'
import type { PickedChatFile } from '../../../shared/types'
import type { FileChat } from '../lib/omiApi.generated'

// send() dispatch-order regression, guarding the pi_mono-default reorder: with
// pi_mono the DEFAULT chat engine, the desktop-automation planner (tryPlan) must
// run BEFORE the pi_mono early-return. Otherwise a keyword-action message ("just
// do X in the app") for an opted-in user would be silently routed to the kernel
// instead of executed as an automation. The three cases pin the branch selection:
//   - action message      → tryPlan handles it; the pi_mono kernel is NOT reached.
//   - plain message        → falls through tryPlan (kind:'chat') → kernel (pi_mono).
//   - attachment message   → pi_mono is gated on sendFileIds===0 → legacy /v2/messages.

// looksLikeAction + planActions are per-test controllable so one file can drive
// the action branch and the plain branch.
const planMocks = vi.hoisted(() => ({
  looksLikeAction: vi.fn<(t: string) => boolean>(() => false),
  planActions: vi.fn()
}))
// automationConsentedAt gates tryPlan; consented by default here (opted-in user).
const prefMocks = vi.hoisted(() => ({
  automationConsentedAt: '2026-07-15T00:00:00Z' as string | null
}))

vi.mock('../lib/firebase', () => ({
  auth: { currentUser: { getIdToken: async () => 'test-token' } }
}))
vi.mock('../lib/pageCache', () => ({ invalidateConversationsCache: vi.fn() }))
vi.mock('../lib/localAgent', () => ({ gatherLocalContext: async () => '' }))
vi.mock('../lib/screenContext', () => ({ readCurrentScreen: async () => '' }))
vi.mock('../lib/actionPlanner', () => ({
  looksLikeAction: (t: string) => planMocks.looksLikeAction(t),
  looksLikeRawPlan: () => false,
  planActions: planMocks.planActions
}))
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn() }))
vi.mock('../lib/agentTask', () => ({
  detectAgentTask: () => null, // never an agent task → falls to the planner/engine
  resolveTaskCwd: vi.fn(async () => '/tmp/cwd')
}))
vi.mock('../lib/preferences', () => ({
  getPreferences: () => ({
    chatHistoryMode: 'per-launch',
    automationConsentedAt: prefMocks.automationConsentedAt,
    agentCommands: {}
  })
}))
vi.mock('../lib/voice/voiceController', () => ({ speakText: vi.fn(() => Promise.resolve()) }))
vi.mock('../lib/desktopChatMessages', () => ({
  saveDesktopMessage: vi.fn(async () => ({ id: 'srv', createdAt: 'now', created: true }))
}))

import { useChat } from './useChat'
import { addAttachments, awaitUploadsSettled, clearAttachments } from '../lib/chatAttachments'

// pi_mono kernel harness.
let sendArgs: MainChatSendArgs | null = null
let eventCb: ((e: MainChatEvent) => void) | null = null
let sendResolve: ((r: unknown) => void) | null = null
const mainChatSend = vi.fn((args: MainChatSendArgs) => {
  sendArgs = args
  return new Promise((res) => (sendResolve = res as (r: unknown) => void))
})
// automation confirm/run — the sink for a planned action.
const automationConfirmRun = vi.fn(async (_plan: unknown) => ({ ok: true, canceled: false }))
// legacy /v2/messages harness (attachment fallthrough).
let fetchUrls: string[] = []

beforeEach(() => {
  vi.clearAllMocks()
  sendArgs = null
  eventCb = null
  sendResolve = null
  fetchUrls = []
  planMocks.looksLikeAction.mockReturnValue(false)
  planMocks.planActions.mockReset()
  prefMocks.automationConsentedAt = '2026-07-15T00:00:00Z'
  clearAttachments()
  global.fetch = vi.fn(async (url: unknown) => {
    fetchUrls.push(String(url))
    // A stream that ends immediately with an empty done frame — the hook's blank-
    // reply guard fires, which is fine; the test only asserts the branch was taken.
    const enc = new TextEncoder()
    let done = false
    return {
      ok: true,
      body: {
        getReader: () => ({
          read: async () => {
            if (done) return { done: true }
            done = true
            return {
              done: false,
              value: enc.encode(`done: ${btoa('{"id":"srv","text":"ok"}')}\n\n`)
            }
          }
        })
      }
    } as unknown as Response
  }) as unknown as typeof fetch
  ;(window as unknown as { omi: unknown }).omi = {
    automationEnabled: true,
    chatGetEngine: async () => 'pi_mono',
    getLocalConversation: async () => null,
    insertLocalConversation: async (_c: { messages?: ChatMessage[] }) => {},
    notifyConversationsChanged: vi.fn(),
    automationTargetWindow: async () => ({ id: 1 }),
    automationSnapshot: async () => ({}),
    automationConfirmRun,
    onMainChatEvent: (cb: (e: MainChatEvent) => void) => {
      eventCb = cb
      return () => {
        if (eventCb === cb) eventCb = null
      }
    },
    mainChatSend,
    mainChatCancel: vi.fn(async () => true)
  }
})
afterEach(() => cleanup())

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

describe('useChat — send() dispatch order (pi_mono default)', () => {
  it('an action message hits tryPlan and does NOT reach the pi_mono kernel', async () => {
    planMocks.looksLikeAction.mockReturnValue(true)
    planMocks.planActions.mockResolvedValue({ ok: true, plan: { steps: [] } })

    const { result } = renderHook(() => useChat())
    await act(async () => {
      await flush() // engineRef → 'pi_mono'
      await result.current.send('open settings and turn on dark mode')
      // give the planner + confirm round-trip a few ticks
      for (let k = 0; k < 20; k++) await flush()
    })

    // tryPlan owned the message: the native confirm dialog ran…
    expect(automationConfirmRun).toHaveBeenCalledTimes(1)
    // …and the pi_mono kernel was never invoked (the reorder's whole point).
    expect(mainChatSend).not.toHaveBeenCalled()
    expect(fetchUrls).toEqual([]) // nor the legacy path
  })

  it('a plain message falls through tryPlan to the pi_mono kernel', async () => {
    planMocks.looksLikeAction.mockReturnValue(false)

    const { result } = renderHook(() => useChat())
    await act(async () => {
      await flush()
      void result.current.send('what is the capital of France')
      for (let k = 0; k < 20 && !sendArgs; k++) await flush()
    })

    // The kernel handled it; the automation dialog never fired.
    expect(mainChatSend).toHaveBeenCalledTimes(1)
    expect(sendArgs).toMatchObject({ cleanUserText: 'what is the capital of France' })
    expect(automationConfirmRun).not.toHaveBeenCalled()
    expect(fetchUrls).toEqual([])

    // Resolve the pending kernel send so no promise dangles past the test.
    await act(async () => {
      sendResolve?.({
        runId: 'r',
        requestId: sendArgs!.requestId,
        ok: true,
        text: 'Paris',
        terminalStatus: 'succeeded'
      })
      await flush()
    })
  })

  it('an attachment message skips the pi_mono kernel and uses legacy /v2/messages', async () => {
    planMocks.looksLikeAction.mockReturnValue(false)
    const pick: PickedChatFile = {
      name: 'a.txt',
      mimeType: 'text/plain',
      size: 3,
      bytes: new Uint8Array([1, 2, 3])
    }
    const uploaded: FileChat = {
      id: 'srv-a.txt',
      name: 'a.txt',
      mime_type: 'text/plain',
      openai_file_id: 'oai-a.txt',
      created_at: '2026-07-15T00:00:00Z'
    }
    addAttachments([pick], { upload: async () => uploaded })
    await awaitUploadsSettled()

    const { result } = renderHook(() => useChat())
    await act(async () => {
      await flush()
      await result.current.send('describe this')
      for (let k = 0; k < 20 && fetchUrls.length === 0; k++) await flush()
    })

    // pi_mono is gated on sendFileIds.length === 0, so the attachment send fell
    // through to legacy /v2/messages — the kernel was skipped.
    expect(mainChatSend).not.toHaveBeenCalled()
    expect(fetchUrls.length).toBe(1)
    expect(fetchUrls[0]).toContain('/v2/messages')
  })
})
