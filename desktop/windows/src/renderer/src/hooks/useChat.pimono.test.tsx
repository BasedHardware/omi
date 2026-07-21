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
// Mutable prefs holder so a single test can flip chatHistoryMode to 'infinite' (the
// real default) to exercise persistChat's async-read + post-read stillValid branch.
// Defaults to 'per-launch' → transparent to every other test. vi.hoisted lets the
// vi.mock factory (hoisted above imports) read it.
const prefsState = vi.hoisted(() => ({
  chatHistoryMode: 'per-launch' as 'per-launch' | 'infinite'
}))
vi.mock('../lib/preferences', () => ({
  getPreferences: () => ({
    chatHistoryMode: prefsState.chatHistoryMode,
    automationConsentedAt: null,
    agentCommands: {}
  })
}))
const speakSpy = vi.fn((_t: string) => Promise.resolve())
vi.mock('../lib/voice/voiceController', () => ({ speakText: (t: string) => speakSpy(t) }))
// Fallback/degrade telemetry — spied so the 429-retry tests can assert the ops
// signal fires (recovered/exhausted) without a real PostHog fetch (hermetic).
const trackEventSpy = vi.fn((_e: string, _p?: Record<string, unknown>) => {})
vi.mock('../lib/analytics', () => ({
  trackEvent: (e: string, p?: Record<string, unknown>) => trackEventSpy(e, p)
}))
// The INV-CHAT-1 shared-thread persistence — spied so we can assert the two turns.
const saveSpy = vi.fn(async (_req: Record<string, unknown>) => ({
  id: 'srv',
  createdAt: 'now',
  created: true
}))
vi.mock('../lib/desktopChatMessages', () => ({
  saveDesktopMessage: (req: Record<string, unknown>) => saveSpy(req)
}))

import {
  useChat,
  CHAT_NOT_READY_INTERIM,
  CHAT_NOT_READY_FINAL,
  CHAT_STREAM_TIMEOUT_MS,
  CHAT_STREAM_TIMEOUT_COPY,
  CHAT_SLOW_CONNECT_MS,
  CHAT_SLOW_CONNECT_COPY
} from './useChat'
import { CHAT_BUSY_RETRY_INTERIM } from '../lib/chat/chatRetry'
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

  it('surfaces FRIENDLY copy on a failed turn (never the raw error) and does NOT write an error line to the shared thread', async () => {
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
    // PR-C: the raw kernel error ("the model exploded") is mapped to the friendly
    // generic copy — never `Error: <raw>` in the bubble.
    expect(lastAssistant(result.current.history)?.content).toBe(
      'Omi couldn’t answer right now. Try again.'
    )
    expect(lastAssistant(result.current.history)?.content).not.toContain('the model exploded')
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

// Tool-activity display (pi_mono). Now that the tool plane fires, the kernel event
// stream carries tool_activity events; the pi_mono door surfaces the running tool as
// a TRANSIENT italic line (`_${name}…_`, matching the coding-agent door) so a long
// tool run no longer reads as dead air. The line is DISPLAY-ONLY: it is never folded
// into the persisted/streamed text nor written to the shared thread (INV-CHAT-1).
describe('useChat — pi_mono tool-activity line', () => {
  it('shows a transient tool line on tool_activity{started}, replaces it with real text, and NEVER persists it', async () => {
    const result = await mountPiMono()
    let p: Promise<void>
    await act(async () => {
      p = result.current.send('do a thing')
      await waitForSend()
      const rid = sendArgs!.requestId
      emit({ type: 'accepted', requestId: rid, runId: 'run-t1' })
      // A tool starts before any reply text → the transient line fills the gap.
      emit({
        type: 'tool_activity',
        requestId: rid,
        runId: 'run-t1',
        name: 'search_memories',
        status: 'started'
      })
      await flush()
    })
    // The running tool renders as the exact italic copy the ACP door uses.
    expect(lastAssistant(result.current.history)?.content).toBe('_search_memories…_')

    // Real reply text supersedes the tool line (cleared on text_delta).
    await act(async () => {
      const rid = sendArgs!.requestId
      emit({ type: 'text_delta', requestId: rid, runId: 'run-t1', text: 'Found it.' })
      await flush()
    })
    expect(lastAssistant(result.current.history)?.content).toBe('Found it.')
    expect(lastAssistant(result.current.history)?.content).not.toContain('search_memories')

    await act(async () => {
      sendResolve!({
        runId: 'run-t1',
        requestId: sendArgs!.requestId,
        ok: true,
        text: 'Found it.',
        terminalStatus: 'succeeded'
      })
      await p
    })

    // Final bubble is the plain reply — no tool line.
    expect(lastAssistant(result.current.history)?.content).toBe('Found it.')
    // INV-CHAT-1 unchanged: exactly two shared-thread writes (human@start, ai@end),
    // and NEITHER carries the transient tool line.
    expect(saveSpy).toHaveBeenCalledTimes(2)
    expect(saveSpy.mock.calls[0][0]).toMatchObject({ text: 'do a thing', sender: 'human' })
    expect(saveSpy.mock.calls[1][0]).toMatchObject({ text: 'Found it.', sender: 'ai' })
    expect(saveSpy.mock.calls[1][0].text).not.toContain('search_memories')
    // No persisted thread snapshot ever contained the tool line.
    const anyToolLine = persisted.some((thread) =>
      thread.some((m) => /search_memories/.test(m.content))
    )
    expect(anyToolLine).toBe(false)
  })

  it('clears the tool line on tool_activity{completed} and keeps streamed text below a later tool', async () => {
    const result = await mountPiMono()
    let p: Promise<void>
    await act(async () => {
      p = result.current.send('multi')
      await waitForSend()
      const rid = sendArgs!.requestId
      emit({ type: 'accepted', requestId: rid, runId: 'run-t2' })
      emit({
        type: 'tool_activity',
        requestId: rid,
        runId: 'run-t2',
        name: 'read_file',
        status: 'started'
      })
      await flush()
    })
    expect(lastAssistant(result.current.history)?.content).toBe('_read_file…_')

    // Tool completes with no text yet → the line clears, leaving an empty bubble.
    await act(async () => {
      const rid = sendArgs!.requestId
      emit({
        type: 'tool_activity',
        requestId: rid,
        runId: 'run-t2',
        name: 'read_file',
        status: 'completed'
      })
      await flush()
    })
    expect(lastAssistant(result.current.history)?.content).toBe('')

    // Text streams, then a SECOND tool starts → the transient line rides BELOW the
    // accumulated reply text (coding-agent door parity), never inside the saved text.
    await act(async () => {
      const rid = sendArgs!.requestId
      emit({ type: 'text_delta', requestId: rid, runId: 'run-t2', text: 'Reading' })
      emit({
        type: 'tool_activity',
        requestId: rid,
        runId: 'run-t2',
        name: 'write_file',
        status: 'started'
      })
      await flush()
    })
    expect(lastAssistant(result.current.history)?.content).toBe('Reading\n\n_write_file…_')

    await act(async () => {
      sendResolve!({
        runId: 'run-t2',
        requestId: sendArgs!.requestId,
        ok: true,
        text: 'Reading done.',
        terminalStatus: 'succeeded'
      })
      await p
    })
    // Terminal reply is the authoritative text — no tool line survives.
    expect(lastAssistant(result.current.history)?.content).toBe('Reading done.')
    expect(saveSpy).toHaveBeenCalledTimes(2)
    expect(saveSpy.mock.calls[1][0]).toMatchObject({ text: 'Reading done.', sender: 'ai' })
    expect(saveSpy.mock.calls[1][0].text).not.toMatch(/write_file|read_file/)
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
        // Retried exactly once (two sends total), reusing the SAME requestId so
        // main's recordSurfaceTurn dedups the kernel human-turn record (a fresh id
        // per attempt would double-record it), and the real reply won — never an
        // `Error:` line.
        expect(sendMock).toHaveBeenCalledTimes(2)
        expect(sendMock.mock.calls[0][0].requestId).toBe(sendMock.mock.calls[1][0].requestId)
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
      // Exactly one send (generic ≠ not-ready → no retry); the raw error is mapped
      // to the friendly generic copy, never surfaced verbatim.
      expect(sendMock).toHaveBeenCalledTimes(1)
      expect(lastAssistant(result.current.history)?.content).toBe(
        'Omi couldn’t answer right now. Try again.'
      )
      expect(lastAssistant(result.current.history)?.content).not.toContain('the model exploded')
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

// Rate-limit (429) auto-retry (pi_mono). The reported bug: a user typed their FIRST
// message right after a voice session and got a scary "you're sending messages too
// quickly" throttle — a backend 429 (this account hits 429 storms) surfaced raw with
// no retry, so they had to manually re-send ~3 times. The fix: a bounded auto-retry
// with backoff (reusing the SAME requestId, so main's recordSurfaceTurn never
// double-records the human turn), and — only when exhausted — a non-blaming "busy"
// line, NEVER the "too quickly" copy. Fake timers drive the backoff.
describe('useChat — pi_mono rate-limit (429) auto-retry', () => {
  const setSend = (
    fn: (args: MainChatSendArgs) => Promise<MainChatResult>
  ): ReturnType<typeof vi.fn> => {
    const mock = vi.fn(fn)
    ;(window as unknown as { omi: { mainChatSend: unknown } }).omi.mainChatSend = mock
    return mock
  }

  async function mountFake(): Promise<
    ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
  > {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    return result
  }

  async function pumpToInterim(
    result: ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
  ): Promise<void> {
    for (
      let k = 0;
      k < 50 && lastAssistant(result.current.history)?.content !== CHAT_BUSY_RETRY_INTERIM;
      k++
    ) {
      await vi.advanceTimersByTimeAsync(1)
    }
  }

  // Both wire formats a 429 can arrive in: legacy-style `HTTP 429` and the
  // managed-cloud/axios `status code 429`. Either must trigger the retry.
  it.each(['HTTP 429', 'Request failed with status code 429'])(
    'auto-retries a first-send 429 and renders the reply — the throttle copy NEVER shows (%s)',
    async (rateLimitError) => {
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
                error: rateLimitError
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
          p = result.current.send('hi')
          await pumpToInterim(result)
        })
        // Attempt 1 got a 429 → one send so far, the non-blaming interim shown.
        expect(sendMock).toHaveBeenCalledTimes(1)
        expect(lastAssistant(result.current.history)?.content).toBe(CHAT_BUSY_RETRY_INTERIM)

        await act(async () => {
          await vi.advanceTimersByTimeAsync(5000) // fire the backoff → retry
          await p
        })
        // Retried, the retry succeeded, and the reply won.
        expect(sendMock).toHaveBeenCalledTimes(2)
        // SAME requestId across attempts → recordSurfaceTurn dedups the human turn.
        expect(sendMock.mock.calls[0][0].requestId).toBe(sendMock.mock.calls[1][0].requestId)
        expect(lastAssistant(result.current.history)?.content).toBe('Hi there')
        // The user NEVER saw the throttle copy (the bug) nor any raw error.
        const seen = result.current.history.map((m) => m.content).join(' | ')
        expect(seen).not.toMatch(/too quickly/i)
        expect(seen).not.toMatch(/^Error:/)
        // INV-CHAT-1: the human turn saved exactly once (not double-saved by the
        // retry), ai once on success.
        expect(saveSpy).toHaveBeenCalledTimes(2)
        expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human', text: 'hi' })
        expect(saveSpy.mock.calls[1][0]).toMatchObject({ sender: 'ai', text: 'Hi there' })
        // Silent-ops guard: the heal is NOT invisible — one fixed-field fallback
        // event fired with outcome 'recovered' (never per-retry spam).
        const fb = trackEventSpy.mock.calls.filter((c) => c[0] === 'fallback_triggered')
        expect(fb).toHaveLength(1)
        expect(fb[0][1]).toMatchObject({
          component: 'chat_send',
          reason: 'rate_limited',
          outcome: 'recovered',
          engine: 'pi_mono'
        })
      } finally {
        vi.useRealTimers()
      }
    }
  )

  it('when every attempt 429s, shows the non-blaming "busy" copy — never "too quickly"', async () => {
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
          error: 'Request failed with status code 429'
        }
      })
      const result = await mountFake()

      let p!: Promise<void>
      await act(async () => {
        p = result.current.send('hi')
        await pumpToInterim(result)
      })
      expect(sendMock).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000) // exhaust every bounded retry
        await p
      })
      // Retried the bounded number of times (initial + CHAT_RATE_LIMIT_RETRIES).
      expect(sendMock.mock.calls.length).toBeGreaterThanOrEqual(2)
      // All attempts reused the one requestId (no double human-record).
      const ids = new Set(sendMock.mock.calls.map((c) => c[0].requestId))
      expect(ids.size).toBe(1)
      // Terminal copy is the honest "servers busy" line — NOT the user-blaming one.
      expect(lastAssistant(result.current.history)?.content).toBe(
        'Omi’s servers are busy. Try again in a moment.'
      )
      expect(lastAssistant(result.current.history)?.content).not.toMatch(/too quickly/i)
      // The friendly line is not written to the shared thread nor spoken.
      expect(saveSpy).toHaveBeenCalledTimes(1)
      expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
      expect(speakSpy).not.toHaveBeenCalled()
      // Silent-ops guard: exhaustion surfaces ONE fallback event, outcome 'exhausted'.
      const fb = trackEventSpy.mock.calls.filter((c) => c[0] === 'fallback_triggered')
      expect(fb).toHaveLength(1)
      expect(fb[0][1]).toMatchObject({
        reason: 'rate_limited',
        outcome: 'exhausted',
        engine: 'pi_mono'
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('does NOT retry a non-429 failure (unchanged fast-fail)', async () => {
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
          error: 'HTTP 500'
        }
      })
      const result = await mountFake()

      await act(async () => {
        const p = result.current.send('hi')
        await vi.advanceTimersByTimeAsync(20_000) // ample time for any (wrong) retry
        await p
      })
      // A 5xx is a hard failure → exactly one send, mapped to the generic copy.
      expect(sendMock).toHaveBeenCalledTimes(1)
      expect(lastAssistant(result.current.history)?.content).toBe(
        'Omi couldn’t answer right now. Try again.'
      )
      // No 429 retry happened → no fallback event (a hard failure is an error metric,
      // not a fallback — AGENTS.md).
      expect(trackEventSpy.mock.calls.filter((c) => c[0] === 'fallback_triggered')).toHaveLength(0)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reset() DURING the backoff skips the retry (no second send, no zombie)', async () => {
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
          error: 'HTTP 429'
        }
      })
      const result = await mountFake()

      let p!: Promise<void>
      await act(async () => {
        p = result.current.send('hi')
        await pumpToInterim(result)
      })
      expect(sendMock).toHaveBeenCalledTimes(1)
      expect(lastAssistant(result.current.history)?.content).toBe(CHAT_BUSY_RETRY_INTERIM)

      // Dismiss while the backoff is pending — the post-await isCurrent() must bail.
      act(() => result.current.reset())
      expect(result.current.history).toEqual([])

      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000)
        await p
      })
      expect(sendMock).toHaveBeenCalledTimes(1) // retry was skipped
      expect(result.current.history).toEqual([])
      const anyZombie = persisted.some((t) =>
        t.some(
          (m) =>
            m.content === CHAT_BUSY_RETRY_INTERIM || /too quickly|servers are busy/i.test(m.content)
        )
      )
      expect(anyZombie).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})

// PR-E per-turn watchdog (pi_mono). The kernel IPC (mainChatSend) has no abort
// primitive and resolves only on the run's terminal event, so a hung run/bridge
// would strand the spinner forever. On the CHAT_STREAM_TIMEOUT_MS deadline the
// watchdog recovers the bubble, unlatches `sending`, best-effort cancels the run,
// and INVALIDATES the turn so a late resolve can't zombie over the recovered state.
// Fake timers drive the 180s deadline instantly.
describe('useChat — pi_mono per-turn watchdog', () => {
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

  // Advance 1ms at a time (never crossing the 180s deadline) until mainChatSend has
  // been issued — i.e. context-gathering resolved and the attempt is awaiting the IPC.
  async function pumpToSend(): Promise<void> {
    for (let k = 0; k < 50 && !sendArgs; k++) await vi.advanceTimersByTimeAsync(1)
    if (!sendArgs) throw new Error('mainChatSend was never called')
  }

  it('HANG → TIMEOUT: recovers the bubble, unlatches sending, and cancels the run', async () => {
    vi.useFakeTimers()
    try {
      // The default beforeEach mainChatSend returns a promise that never settles —
      // exactly a hung run. We never call sendResolve, so the await never returns.
      const result = await mountFake()
      await act(async () => {
        void result.current.send('hello')
        await pumpToSend()
        // Run WAS accepted (server ack'd) then the terminal event never comes.
        emit({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'run-hang' })
        await vi.advanceTimersByTimeAsync(1)
      })
      // Pre-deadline: spinner latched, no reply.
      expect(result.current.sending).toBe(true)

      // Cross the 180s deadline → the watchdog fires.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_STREAM_TIMEOUT_MS + 10)
      })
      expect(lastAssistant(result.current.history)?.content).toBe(CHAT_STREAM_TIMEOUT_COPY)
      expect(result.current.sending).toBe(false) // spinner unlatched (the whole point)
      expect(cancelSpy).toHaveBeenCalledWith('run-hang') // best-effort server cancel
      // The timeout line is a local recovery, NOT a real reply — only the human@start
      // save fired; it is never written to the shared thread (INV-CHAT-1).
      expect(saveSpy).toHaveBeenCalledTimes(1)
      expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
      expect(speakSpy).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('LATE-RESOLVE-AFTER-TIMEOUT: a resolve after the deadline cannot zombie the turn', async () => {
    vi.useFakeTimers()
    try {
      const result = await mountFake()
      let p!: Promise<void>
      await act(async () => {
        p = result.current.send('hello')
        await pumpToSend()
        emit({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'run-late' })
        await vi.advanceTimersByTimeAsync(1)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_STREAM_TIMEOUT_MS + 10)
      })
      expect(lastAssistant(result.current.history)?.content).toBe(CHAT_STREAM_TIMEOUT_COPY)
      expect(result.current.sending).toBe(false)
      const savesAtTimeout = saveSpy.mock.calls.length // 1 (human@start)

      // The abandoned send resolves LATE with a success + emits a late delta. The
      // turn was invalidated, so none of this may land.
      await act(async () => {
        emit({
          type: 'text_delta',
          requestId: sendArgs!.requestId,
          runId: 'run-late',
          text: 'late reply'
        })
        sendResolve!({
          runId: 'run-late',
          requestId: sendArgs!.requestId,
          ok: true,
          text: 'late reply',
          terminalStatus: 'succeeded'
        })
        await p
      })
      // Timeout copy stands — NOT 'late reply'.
      expect(lastAssistant(result.current.history)?.content).toBe(CHAT_STREAM_TIMEOUT_COPY)
      // No second setBusy latch flip, no ai-completion save, no zombie persist.
      expect(result.current.sending).toBe(false)
      expect(saveSpy).toHaveBeenCalledTimes(savesAtTimeout)
      expect(saveSpy.mock.calls[0][0]).toMatchObject({ sender: 'human' })
      const anyZombie = persisted.some((t) => t.some((m) => /late reply/.test(m.content)))
      expect(anyZombie).toBe(false)
      expect(speakSpy).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('NO-TIMEOUT REGRESSION: a fast success is unchanged and the watchdog is cleared', async () => {
    vi.useFakeTimers()
    try {
      const result = await mountFake()
      let p!: Promise<void>
      await act(async () => {
        p = result.current.send('hello')
        await pumpToSend()
        const rid = sendArgs!.requestId
        emit({ type: 'accepted', requestId: rid, runId: 'run-fast' })
        emit({ type: 'text_delta', requestId: rid, runId: 'run-fast', text: 'Hi there' })
        sendResolve!({
          runId: 'run-fast',
          requestId: rid,
          ok: true,
          text: 'Hi there',
          terminalStatus: 'succeeded'
        })
        await p
      })
      // Normal completion: reply rendered, both INV-CHAT-1 saves fired.
      expect(lastAssistant(result.current.history)?.content).toBe('Hi there')
      expect(result.current.sending).toBe(false)
      expect(saveSpy).toHaveBeenCalledTimes(2)
      const savesBefore = saveSpy.mock.calls.length

      // The watchdog was cleared on completion — crossing the deadline is a no-op:
      // the reply is not overwritten with the timeout copy and no extra saves fire.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_STREAM_TIMEOUT_MS + 10)
      })
      expect(lastAssistant(result.current.history)?.content).toBe('Hi there')
      expect(saveSpy).toHaveBeenCalledTimes(savesBefore)
      expect(result.current.sending).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  // INFINITE-mode is the real default (getPreferences() → 'infinite'). It is the ONLY
  // mode where the crux bites: persistChat does `await getLocalConversation(...)` before
  // its SECOND stillValid() re-check, so the watchdog's own `++genRef.current` would flip
  // an `isCurrent`-based validator false AFTER the await and silently drop the write —
  // shipping an empty persisted bubble that resurfaces on reload. Validating the persist
  // against the captured `invalidated` gen (not isCurrent) is what keeps it durable. This
  // test locks that in: it FAILS loudly if the validator regresses to `isCurrent`.
  it('INFINITE-MODE PERSIST: the timeout line is durably persisted (survives the own-turn gen bump)', async () => {
    vi.useFakeTimers()
    prefsState.chatHistoryMode = 'infinite'
    // A prior stored conversation forces the infinite-mode branch (async read +
    // mergeChatMessages + the post-read re-check that per-launch skips).
    ;(window as unknown as { omi: { getLocalConversation: unknown } }).omi.getLocalConversation =
      async () => ({ startedAt: 1000, messages: [] })
    try {
      const result = await mountFake()
      await act(async () => {
        void result.current.send('hello')
        await pumpToSend()
        emit({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'run-inf' })
        await vi.advanceTimersByTimeAsync(1)
      })
      // Cross the deadline → watchdog recovers the bubble, invalidates the turn, and
      // persists the timeout line locally. Drain the persist's async read + insert.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_STREAM_TIMEOUT_MS + 10)
        await vi.advanceTimersByTimeAsync(1)
      })
      const rendered = [...result.current.history].reverse().find((m) => m.role === 'assistant')
      expect(rendered?.content).toBe(CHAT_STREAM_TIMEOUT_COPY)
      const assistantId = rendered?.id
      expect(assistantId).toBeTruthy()
      // CRUX: the timeout line landed in storage under THIS turn's assistant id — it
      // survived the watchdog's own genRef bump. Regressing the validator to `isCurrent`
      // makes persistChat bail at its post-await re-check, so `persisted` would never
      // contain the timeout copy and this assertion would fail.
      const persistedTimeout = persisted.some((thread) =>
        thread.some((m) => m.id === assistantId && m.content === CHAT_STREAM_TIMEOUT_COPY)
      )
      expect(persistedTimeout).toBe(true)
    } finally {
      prefsState.chatHistoryMode = 'per-launch'
      vi.useRealTimers()
    }
  })
})

// First-reply slow-connect feedback. On a cold managed-cloud backend the first
// turn can wait tens of seconds before its first delta with the bubble EMPTY —
// which rendered as a bare spinner and read as a hang (the shipped first-run
// complaint: "sent hi, got dots"). At CHAT_SLOW_CONNECT_MS with nothing visible
// the bubble shows the connecting copy; real content replaces it, and a turn
// that already streamed is never overwritten.
describe('useChat — pi_mono slow-connect feedback', () => {
  async function mountFake(): Promise<
    ReturnType<typeof renderHook<ReturnType<typeof useChat>, unknown>>['result']
  > {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    return result
  }

  async function pumpToSend(): Promise<void> {
    for (let k = 0; k < 50 && !sendArgs; k++) await vi.advanceTimersByTimeAsync(1)
    if (!sendArgs) throw new Error('mainChatSend was never called')
  }

  it('COLD START: an empty bubble shows the connecting copy at the deadline; the first delta replaces it', async () => {
    vi.useFakeTimers()
    try {
      // The default mainChatSend never settles — the run was accepted but the
      // first delta is a long way off (cold backend).
      const result = await mountFake()
      await act(async () => {
        void result.current.send('hi')
        await pumpToSend()
        emit({ type: 'accepted', requestId: sendArgs!.requestId, runId: 'run-cold' })
        await vi.advanceTimersByTimeAsync(1)
      })
      // Pre-deadline: bubble empty (the spinner state), no interim copy yet.
      expect(lastAssistant(result.current.history)?.content).toBe('')

      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_SLOW_CONNECT_MS + 10)
      })
      // Feedback, not a terminal: the copy shows and the turn stays in flight.
      expect(lastAssistant(result.current.history)?.content).toBe(CHAT_SLOW_CONNECT_COPY)
      expect(result.current.sending).toBe(true)
      // Display-only: nothing was saved to the shared thread beyond human@start,
      // and nothing was spoken.
      expect(saveSpy).toHaveBeenCalledTimes(1)
      expect(speakSpy).not.toHaveBeenCalled()

      // The first real delta supersedes the interim copy.
      await act(async () => {
        emit({
          type: 'text_delta',
          requestId: sendArgs!.requestId,
          runId: 'run-cold',
          text: 'Hi there'
        })
        await vi.advanceTimersByTimeAsync(1)
      })
      expect(lastAssistant(result.current.history)?.content).toBe('Hi there')
    } finally {
      vi.useRealTimers()
    }
  })

  it('NO-OVERWRITE REGRESSION: a turn that streamed before the deadline never shows the connecting copy', async () => {
    vi.useFakeTimers()
    try {
      const result = await mountFake()
      await act(async () => {
        void result.current.send('hi')
        await pumpToSend()
        const rid = sendArgs!.requestId
        emit({ type: 'accepted', requestId: rid, runId: 'run-warm' })
        emit({ type: 'text_delta', requestId: rid, runId: 'run-warm', text: 'Hello' })
        await vi.advanceTimersByTimeAsync(1)
      })
      expect(lastAssistant(result.current.history)?.content).toBe('Hello')

      // Crossing the slow-connect deadline is a no-op once content streamed.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_SLOW_CONNECT_MS + 10)
      })
      expect(lastAssistant(result.current.history)?.content).toBe('Hello')
    } finally {
      vi.useRealTimers()
    }
  })
})
