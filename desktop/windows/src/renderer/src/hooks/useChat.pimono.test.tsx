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

import { useChat, CHAT_NOT_READY_INTERIM, CHAT_NOT_READY_FINAL } from './useChat'
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

// #123 first-chat not-ready (pi_mono). Right after sign-in the owner/adapter relay
// may not have reached main yet, so the FIRST send resolves `{ ok:false, error:<a
// not-ready marker> }`. useChat must show the interim copy, retry ONCE, and — if it
// still fails not-ready — show a friendly final line, NEVER a raw `Error:` bubble.
// A generic model error must be unaffected (no retry). Fake timers drive the delay.
describe('useChat — first-chat not ready (retry once)', () => {
  const setSend = (
    fn: (args: MainChatSendArgs) => Promise<MainChatResult>
  ): ReturnType<typeof vi.fn> => {
    const mock = vi.fn(fn)
    ;(window as unknown as { omi: { mainChatSend: unknown } }).omi.mainChatSend = mock
    return mock
  }

  // Mount and flush the mount effect (engineRef → 'pi_mono') under fake timers.
  async function mountFake(): Promise<
    ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
  > {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    return result
  }

  // Advance 1ms at a time (never crossing the 600ms retry delay) until the interim
  // copy appears — i.e. attempt 1 has resolved not-ready and written the bubble.
  async function pumpToInterim(
    result: ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
  ): Promise<void> {
    for (
      let k = 0;
      k < 50 && lastAssistant(result.current.history)?.content !== CHAT_NOT_READY_INTERIM;
      k++
    ) {
      await vi.advanceTimersByTimeAsync(1)
    }
  }

  // All three not-ready markers this branch can produce must trigger the retry:
  // adapter never registered, session cleared before the pool built the adapter,
  // and the cold-start owner gate (mainChat.ts — dominant right after sign-in).
  it.each([
    'Adapter not registered: pi-mono',
    'pi-mono session was cleared before the adapter started.',
    'Sign-in has not completed yet — try again in a moment.'
  ])(
    'retries once and renders the reply when the first send fails not-ready (%s)',
    async (marker) => {
      vi.useFakeTimers()
      try {
        let call = 0
        const sendMock = setSend(async (args) => {
          sendArgs = args
          call++
          return call === 1
            ? {
                runId: '',
                requestId: args.requestId,
                ok: false,
                text: '',
                terminalStatus: 'failed',
                error: marker
              }
            : {
                runId: 'run-ok',
                requestId: args.requestId,
                ok: true,
                text: 'Hi there',
                terminalStatus: 'succeeded'
              }
        })
        const result = await mountFake()

        let p!: Promise<void>
        await act(async () => {
          p = result.current.send('hello')
          await pumpToInterim(result)
        })
        // Attempt 1 failed not-ready → exactly one send so far, interim copy shown.
        expect(sendMock).toHaveBeenCalledTimes(1)
        expect(lastAssistant(result.current.history)?.content).toBe(CHAT_NOT_READY_INTERIM)

        await act(async () => {
          await vi.advanceTimersByTimeAsync(2000) // fire the retry delay → attempt 2
          await p
        })
        // Retried exactly once (two sends total), with a FRESH requestId, and the
        // real reply won — never an `Error:` line.
        expect(sendMock).toHaveBeenCalledTimes(2)
        expect(sendMock.mock.calls[0][0].requestId).not.toBe(sendMock.mock.calls[1][0].requestId)
        expect(lastAssistant(result.current.history)?.content).toBe('Hi there')
        // INV-CHAT-1: human saved once@start, ai once@completion — the retry did NOT
        // double-save the human turn (the whole point of keeping the user-save out of
        // the per-attempt helper).
        expect(saveSpy).toHaveBeenCalledTimes(2)
        expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human', text: 'hello' })
        expect(saveSpy.mock.calls[1][0]).toMatchObject({ sender: 'ai', text: 'Hi there' })
      } finally {
        vi.useRealTimers()
      }
    }
  )

  // The FINAL friendly copy must show for EVERY not-ready marker when the retry
  // also fails not-ready — never a raw `Error:` line, for any of the three.
  it.each([
    'Adapter not registered: pi-mono',
    'pi-mono session was cleared before the adapter started.',
    'Sign-in has not completed yet — try again in a moment.'
  ])(
    'shows the friendly final copy (not a raw error) when BOTH attempts fail not-ready (%s)',
    async (marker) => {
      vi.useFakeTimers()
      try {
        const sendMock = setSend(async (args) => {
          sendArgs = args
          return {
            runId: '',
            requestId: args.requestId,
            ok: false,
            text: '',
            terminalStatus: 'failed',
            error: marker
          }
        })
        const result = await mountFake()

        let p!: Promise<void>
        await act(async () => {
          p = result.current.send('hello')
          await pumpToInterim(result)
        })
        expect(sendMock).toHaveBeenCalledTimes(1)

        await act(async () => {
          await vi.advanceTimersByTimeAsync(2000) // retry → attempt 2, still not ready
          await p
        })
        expect(sendMock).toHaveBeenCalledTimes(2)
        // Friendly final line, never `Error: <marker>`.
        expect(lastAssistant(result.current.history)?.content).toBe(CHAT_NOT_READY_FINAL)
        expect(lastAssistant(result.current.history)?.content).not.toMatch(/^Error:/)
        // Only the human turn is saved to the shared thread — the friendly line is not.
        expect(saveSpy).toHaveBeenCalledTimes(1)
        expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
        expect(speakSpy).not.toHaveBeenCalled()
      } finally {
        vi.useRealTimers()
      }
    }
  )

  it('does NOT retry a generic (non-not-ready) failure — unchanged behavior', async () => {
    vi.useFakeTimers()
    try {
      const sendMock = setSend(async (args) => {
        sendArgs = args
        return {
          runId: 'r',
          requestId: args.requestId,
          ok: false,
          text: '',
          terminalStatus: 'failed',
          error: 'the model exploded'
        }
      })
      const result = await mountFake()

      await act(async () => {
        const p = result.current.send('boom')
        await vi.advanceTimersByTimeAsync(2000) // ample time for any (wrong) retry to fire
        await p
      })
      // Exactly one send, raw error surfaced verbatim, no retry.
      expect(sendMock).toHaveBeenCalledTimes(1)
      expect(lastAssistant(result.current.history)?.content).toBe('Error: the model exploded')
      expect(saveSpy).toHaveBeenCalledTimes(1)
      expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
    } finally {
      vi.useRealTimers()
    }
  })

  // The single most delicate new window: reset() DURING the 600ms retry delay. The
  // setTimeout is NOT cancelled, so the post-await isCurrent() check is the ONLY
  // thing preventing attempt 2 — lock it in.
  it('reset() DURING the retry delay skips attempt 2 (no second send, no zombie)', async () => {
    vi.useFakeTimers()
    try {
      const sendMock = setSend(async (args) => {
        sendArgs = args
        return {
          runId: '',
          requestId: args.requestId,
          ok: false,
          text: '',
          terminalStatus: 'failed',
          error: 'Adapter not registered: pi-mono'
        }
      })
      const result = await mountFake()

      let p!: Promise<void>
      await act(async () => {
        p = result.current.send('hello')
        await pumpToInterim(result)
      })
      // Attempt 1 failed not-ready; interim shown; the 600ms retry delay is pending.
      expect(sendMock).toHaveBeenCalledTimes(1)
      expect(lastAssistant(result.current.history)?.content).toBe(CHAT_NOT_READY_INTERIM)

      // Dismiss WHILE the delay is pending — do NOT advance past 600ms first.
      act(() => result.current.reset())
      expect(result.current.history).toEqual([])
      // Attempt 1 failed pre-stream, so no run was ever accepted → nothing to cancel.
      expect(cancelSpy).not.toHaveBeenCalled()

      // Now let the lingering delay fire: the post-await isCurrent() check must bail
      // BEFORE attempt 2, so mainChatSend is never called a second time.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
        await p
      })
      expect(sendMock).toHaveBeenCalledTimes(1) // still ONE send — attempt 2 was skipped
      expect(result.current.history).toEqual([]) // reset's empty thread stands
      // Only the human@start save fired; no ai-completion save from the dismissed turn.
      expect(saveSpy).toHaveBeenCalledTimes(1)
      expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
      // The interim copy was never persisted as a zombie.
      const anyZombie = persisted.some((thread) =>
        thread.some((m) => m.content === CHAT_NOT_READY_INTERIM)
      )
      expect(anyZombie).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
