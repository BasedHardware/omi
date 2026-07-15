// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import type {
  ChatMessage,
  MainChatEvent,
  MainChatResult,
  MainChatSendArgs
} from '../../../shared/types'

// The pi_mono (kernel-routed) branch of useChat.send(). The flag-OFF (legacy_sse)
// path is proven byte-identical by the UNMODIFIED existing useChat.test.tsx; this
// file drives the ON path: engine flag 'pi_mono' → tryKernelChat consumes the
// mainChat event stream, makes the INV-CHAT-1 saveMessage calls, and honours the
// C5 generation guards (dismiss mid-stream must not persist/save/unlatch).

vi.mock('../lib/firebase', () => ({
  auth: { currentUser: { getIdToken: async () => 'test-token' } }
}))
vi.mock('../lib/pageCache', () => ({ invalidateConversationsCache: vi.fn() }))
vi.mock('../lib/localAgent', () => ({ gatherLocalContext: async () => '' }))
// Non-empty screen context so `prompt` (context-prepended) differs from the raw
// user text — proving the model gets the contexted prompt while the transcript /
// shared-thread saves store only the clean user message.
vi.mock('../lib/screenContext', () => ({ readCurrentScreen: async () => 'SCREEN_CTX' }))
vi.mock('../lib/actionPlanner', () => ({
  looksLikeAction: () => false,
  looksLikeRawPlan: () => false,
  planActions: vi.fn()
}))
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn() }))
vi.mock('../lib/agentTask', () => ({
  detectAgentTask: () => null, // never an agent task → falls through to the engine
  resolveTaskCwd: vi.fn(async () => '/tmp/cwd')
}))
vi.mock('../lib/preferences', () => ({
  getPreferences: () => ({
    chatHistoryMode: 'per-launch',
    automationConsentedAt: null,
    agentCommands: {}
  })
}))
const speakSpy = vi.fn((_t: string) => Promise.resolve())
vi.mock('../lib/voice/voiceController', () => ({ speakText: (t: string) => speakSpy(t) }))
// The INV-CHAT-1 shared-thread persistence — spied so we can assert the two turns.
const saveSpy = vi.fn(async (_req: Record<string, unknown>) => ({
  id: 'srv',
  createdAt: 'now',
  created: true
}))
vi.mock('../lib/desktopChatMessages', () => ({
  saveDesktopMessage: (req: Record<string, unknown>) => saveSpy(req)
}))

import { useChat } from './useChat'
import { clearAttachments } from '../lib/chatAttachments'

let persisted: ChatMessage[][] = []
let eventCb: ((e: MainChatEvent) => void) | null = null
let sendArgs: MainChatSendArgs | null = null
let sendResolve: ((r: MainChatResult) => void) | null = null
const cancelSpy = vi.fn(async () => true)

beforeEach(() => {
  vi.clearAllMocks()
  persisted = []
  eventCb = null
  sendArgs = null
  sendResolve = null
  clearAttachments()
  ;(window as unknown as { omi: unknown }).omi = {
    automationEnabled: false,
    chatGetEngine: async () => 'pi_mono',
    getLocalConversation: async () => null,
    insertLocalConversation: async (c: { messages?: ChatMessage[] }) => {
      persisted.push(JSON.parse(JSON.stringify(c.messages ?? [])))
    },
    notifyConversationsChanged: vi.fn(),
    onMainChatEvent: (cb: (e: MainChatEvent) => void) => {
      eventCb = cb
      return () => {
        if (eventCb === cb) eventCb = null
      }
    },
    mainChatSend: (args: MainChatSendArgs) => {
      sendArgs = args
      return new Promise<MainChatResult>((res) => (sendResolve = res))
    },
    mainChatCancel: cancelSpy
  }
})
afterEach(() => cleanup())

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

// Mount and let the mount effect's chatGetEngine() resolve so engineRef flips to
// 'pi_mono' before the first send.
async function mountPiMono(): Promise<
  ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
> {
  const { result } = renderHook(() => useChat())
  await act(async () => {
    await flush()
  })
  return result
}

async function waitForSend(): Promise<void> {
  for (let k = 0; k < 100 && !sendArgs; k++) await flush()
  if (!sendArgs) throw new Error('mainChatSend was never called')
}

const emit = (e: MainChatEvent): void => eventCb?.(e)
const lastAssistant = (
  msgs: { role: string; content: string }[]
): { content: string } | undefined => [...msgs].reverse().find((m) => m.role === 'assistant')

describe('useChat — pi_mono engine', () => {
  it('streams deltas, resolves with the final text, and persists BOTH turns to the shared thread', async () => {
    const result = await mountPiMono()
    let p: Promise<void>
    await act(async () => {
      p = result.current.send('hello')
      await waitForSend()
      const rid = sendArgs!.requestId
      emit({ type: 'accepted', requestId: rid, runId: 'run-1' })
      emit({ type: 'text_delta', requestId: rid, runId: 'run-1', text: 'Hi ' })
      emit({ type: 'text_delta', requestId: rid, runId: 'run-1', text: 'there' })
      await flush()
    })
    // Mid-stream: the deltas render into the bubble before the send resolves.
    expect(lastAssistant(result.current.history)?.content).toBe('Hi there')

    await act(async () => {
      sendResolve!({
        runId: 'run-1',
        requestId: sendArgs!.requestId,
        ok: true,
        text: 'Hi there',
        terminalStatus: 'succeeded'
      })
      await p
    })

    expect(lastAssistant(result.current.history)?.content).toBe('Hi there')
    // The model gets the context-prepended prompt; the transcript gets the clean
    // user text — the raw-vs-contexted split at the heart of INV-CHAT-1.
    expect(sendArgs).toMatchObject({ prompt: 'SCREEN_CTX\n\nhello', cleanUserText: 'hello' })

    // INV-CHAT-1: exactly two shared-thread writes — human@start, ai@completion —
    // both OMITTING session_id (default shared thread), and the human write stores
    // the RAW user text, never the context-prepended prompt.
    expect(saveSpy).toHaveBeenCalledTimes(2)
    const userReq = saveSpy.mock.calls[0][0] as Record<string, unknown>
    const aiReq = saveSpy.mock.calls[1][0] as Record<string, unknown>
    expect(userReq).toMatchObject({ text: 'hello', sender: 'human' })
    expect('sessionId' in userReq).toBe(false)
    expect(aiReq).toMatchObject({ text: 'Hi there', sender: 'ai' })
    expect('sessionId' in aiReq).toBe(false)
  })

  it('surfaces the error on a failed turn and does NOT write an error line to the shared thread', async () => {
    const result = await mountPiMono()
    await act(async () => {
      const p = result.current.send('boom')
      await waitForSend()
      const rid = sendArgs!.requestId
      emit({ type: 'accepted', requestId: rid, runId: 'run-2' })
      emit({
        type: 'run_finished',
        requestId: rid,
        runId: 'run-2',
        status: 'failed',
        error: 'the model exploded'
      })
      sendResolve!({
        runId: 'run-2',
        requestId: rid,
        ok: false,
        text: '',
        terminalStatus: 'failed',
        error: 'the model exploded'
      })
      await p
    })
    expect(lastAssistant(result.current.history)?.content).toBe('Error: the model exploded')
    // Only the human turn is persisted to the shared thread — never the error line.
    expect(saveSpy).toHaveBeenCalledTimes(1)
    expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
    expect(speakSpy).not.toHaveBeenCalled()
  })

  it('dismiss mid-stream cancels the run, fires no completion save, and persists no zombie', async () => {
    const result = await mountPiMono()
    let p: Promise<void>
    await act(async () => {
      p = result.current.send('question')
      await waitForSend()
      const rid = sendArgs!.requestId
      emit({ type: 'accepted', requestId: rid, runId: 'run-x' })
      emit({ type: 'text_delta', requestId: rid, runId: 'run-x', text: 'partial' })
      await flush()
    })
    expect(lastAssistant(result.current.history)?.content).toBe('partial')

    // Dismiss mid-stream: cancels the managed-cloud run with the captured runId.
    act(() => result.current.reset())
    expect(cancelSpy).toHaveBeenCalledWith('run-x')
    expect(result.current.history).toEqual([])

    // The cancelled send resolves AFTER the dismiss — its completion path must be
    // fully guarded: no assistant save, no zombie persist, no busy unlatch clobber.
    await act(async () => {
      sendResolve!({
        runId: 'run-x',
        requestId: sendArgs!.requestId,
        ok: false,
        text: 'ZOMBIE FINAL',
        terminalStatus: 'cancelled'
      })
      await p
    })
    expect(result.current.history).toEqual([])
    // Only the human@start save fired (before dismiss); the ai@completion did NOT.
    expect(saveSpy).toHaveBeenCalledTimes(1)
    expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
    // Nothing from the dismissed turn's completion was persisted.
    const anyZombie = persisted.some((thread) => thread.some((m) => /ZOMBIE FINAL/.test(m.content)))
    expect(anyZombie).toBe(false)
  })
})
