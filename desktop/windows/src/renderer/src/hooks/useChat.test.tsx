// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import type { ChatMessage, CodingAgentEvent } from '../../../shared/types'

// useChat is the app's single chat engine. These tests cover the two wiring
// fixes: C4 — the terminal `done:` payload (citation-stripped text + server id +
// citations) must win over the raw streamed text; and C5 — reset() mid-stream
// must abort the fetch and prevent the dismissed reply from writing into state
// or SQLite (no zombie resurface, no busy-flag interleaving).
//
// Everything useChat imports that touches firebase/IPC/screen is mocked; the SSE
// parser (messagesSse) and the merge helper (chatConversation) are the REAL
// modules, since the fix lives at their boundary.

vi.mock('../lib/firebase', () => ({
  auth: { currentUser: { getIdToken: async () => 'test-token' } }
}))
vi.mock('../lib/pageCache', () => ({ invalidateConversationsCache: vi.fn() }))
vi.mock('../lib/localAgent', () => ({ gatherLocalContext: async () => '' }))
vi.mock('../lib/screenContext', () => ({ readCurrentScreen: async () => '' }))
vi.mock('../lib/actionPlanner', () => ({
  looksLikeAction: () => false,
  looksLikeRawPlan: () => false,
  planActions: vi.fn()
}))
vi.mock('../lib/agentLLM', () => ({ callAgentLLM: vi.fn() }))
// detectAgentTask is controllable per-test: default null (fall through to chat),
// overridden to return a detection for the agent-task path test.
const agentMocks = vi.hoisted(() => ({
  detectAgentTask: vi.fn<(t: string) => { agentId?: string; prompt: string } | null>(() => null),
  resolveTaskCwd: vi.fn(async () => '/tmp/cwd')
}))
vi.mock('../lib/agentTask', () => ({
  detectAgentTask: agentMocks.detectAgentTask,
  resolveTaskCwd: agentMocks.resolveTaskCwd
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

import { useChat, CHAT_STREAM_TIMEOUT_MS } from './useChat'
import {
  addAttachments,
  awaitUploadsSettled,
  clearAttachments,
  getPendingAttachments
} from '../lib/chatAttachments'
import type { FileChat } from '../lib/omiApi.generated'
import type { PickedChatFile } from '../../../shared/types'

const b64 = (s: string): string => Buffer.from(s, 'utf-8').toString('base64')

// A hand-driven ReadableStream reader: push() enqueues an SSE frame, close()
// ends the stream. read() resolves immediately if data is queued, else waits for
// the next push/close — so a test can interleave reset()/timeouts between frames.
// Abort-aware: when the fetch signal aborts, a pending read rejects with an
// AbortError, exactly like a real fetch stream, so the hook's catch runs.
function makeManualStream(signal?: AbortSignal): {
  push: (text: string) => void
  close: () => void
  reader: { read: () => Promise<{ done: boolean; value?: Uint8Array }> }
} {
  const enc = new TextEncoder()
  const queue: Array<{ done: boolean; value?: Uint8Array }> = []
  let pendingRes: ((v: { done: boolean; value?: Uint8Array }) => void) | null = null
  let pendingRej: ((e: unknown) => void) | null = null
  const abortError = (): Error =>
    Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' })
  const deliver = (item: { done: boolean; value?: Uint8Array }): void => {
    if (pendingRes) {
      pendingRes(item)
      pendingRes = pendingRej = null
    } else {
      queue.push(item)
    }
  }
  if (signal) {
    signal.addEventListener('abort', () => {
      if (pendingRej) {
        pendingRej(abortError())
        pendingRes = pendingRej = null
      }
    })
  }
  return {
    push: (text) => deliver({ done: false, value: enc.encode(text) }),
    close: () => deliver({ done: true }),
    reader: {
      read: () => {
        if (signal?.aborted) return Promise.reject(abortError())
        if (queue.length)
          return Promise.resolve(queue.shift() as { done: boolean; value?: Uint8Array })
        return new Promise((res, rej) => {
          pendingRes = res
          pendingRej = rej
        })
      }
    }
  }
}

let streams: ReturnType<typeof makeManualStream>[] = []
let signals: Array<AbortSignal | undefined> = []
let bodies: string[] = []
let persisted: ChatMessage[][] = []
// Coding-agent bridge harness (agent-task path).
let agentEventCb: ((e: CodingAgentEvent) => void) | null = null
let agentRunTaskId: string | null = null
let agentRunResolve: ((r: { ok: boolean; text?: string; error?: string }) => void) | null = null
const codingAgentCancelSpy = vi.fn(async () => {})

beforeEach(() => {
  vi.clearAllMocks()
  streams = []
  signals = []
  bodies = []
  persisted = []
  clearAttachments() // reset the module-level pending-attachment singleton
  agentEventCb = null
  agentRunTaskId = null
  agentRunResolve = null
  agentMocks.detectAgentTask.mockReset()
  agentMocks.detectAgentTask.mockReturnValue(null)
  agentMocks.resolveTaskCwd.mockReset()
  agentMocks.resolveTaskCwd.mockResolvedValue('/tmp/cwd')
  global.fetch = vi.fn(async (_url: unknown, init?: { signal?: AbortSignal; body?: unknown }) => {
    const s = makeManualStream(init?.signal)
    streams.push(s)
    signals.push(init?.signal)
    bodies.push(typeof init?.body === 'string' ? init.body : String(init?.body ?? ''))
    return { ok: true, body: { getReader: () => s.reader } } as unknown as Response
  }) as unknown as typeof fetch
  ;(window as unknown as { omi: unknown }).omi = {
    automationEnabled: false,
    getLocalConversation: async () => null,
    insertLocalConversation: async (c: { messages?: ChatMessage[] }) => {
      // Snapshot the thread as-persisted so later mutations can't rewrite history.
      persisted.push(JSON.parse(JSON.stringify(c.messages ?? [])))
    },
    notifyConversationsChanged: vi.fn(),
    // Coding-agent bridge (used only by the agent-task path test).
    codingAgentList: async () => [
      { id: 'claude', connected: true, displayName: 'Claude', installHint: null }
    ],
    onCodingAgentEvent: (cb: (e: CodingAgentEvent) => void) => {
      agentEventCb = cb
      return () => {
        if (agentEventCb === cb) agentEventCb = null
      }
    },
    codingAgentRun: (opts: { taskId: string }) => {
      agentRunTaskId = opts.taskId
      return new Promise((res) => (agentRunResolve = res))
    },
    codingAgentCancel: codingAgentCancelSpy,
    kgSearchFiles: async () => [],
    kgExecuteSql: async () => ({ columns: [], rows: [] })
  }
})
afterEach(() => cleanup())

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))
// send() awaits the planner + context gather + fetch before the stream opens, so
// wait for fetch to have created stream `i` before pushing frames into it.
async function waitForStream(i: number): Promise<void> {
  for (let k = 0; k < 100 && !streams[i]; k++) await flush()
  if (!streams[i]) throw new Error(`stream ${i} never opened`)
}
const lastAssistant = (
  msgs: { role: string; content: string }[]
): { content: string } | undefined => [...msgs].reverse().find((m) => m.role === 'assistant')

describe('useChat — C4 done payload', () => {
  it('replaces streamed text with the citation-stripped final text and stores the server id + citations', async () => {
    const { result } = renderHook(() => useChat())
    const done = {
      id: 'srv-msg-9',
      text: 'Your standup is at 10am.', // [1] stripped by the backend
      memories: [
        {
          id: 'conv-1',
          structured: { title: 'Standup', emoji: '📝' },
          created_at: '2026-07-13T00:00:00Z'
        }
      ],
      ask_for_nps: true
    }
    await act(async () => {
      const p = result.current.send('when is standup')
      await waitForStream(0)
      // Streamed chunks still carry the literal [1] citation marker...
      streams[0].push('data: Your standup is at 10am. [1]\n')
      // ...but the done frame's text has it stripped, and carries the metadata.
      streams[0].push(`done: ${b64(JSON.stringify(done))}\n\n`)
      streams[0].close()
      await p
    })

    const msg = lastAssistant(result.current.history) as {
      content: string
      serverId?: string
      citations?: { id: string; title: string }[]
      askForNps?: boolean
    }
    expect(msg.content).toBe('Your standup is at 10am.')
    expect(msg.content).not.toContain('[1]')
    expect(msg.serverId).toBe('srv-msg-9')
    expect(msg.citations).toEqual([{ id: 'conv-1', title: 'Standup', emoji: '📝' }])
    expect(msg.askForNps).toBe(true)

    // The FINAL persisted thread carries the stripped text + server id (so a
    // reload shows no bracket leak and rating/report have an id to key off).
    const finalThread = persisted.at(-1) as (ChatMessage & { serverId?: string })[]
    const persistedAssistant = [...finalThread]
      .reverse()
      .find((m) => m.role === 'assistant') as ChatMessage & {
      serverId?: string
    }
    expect(persistedAssistant.content).toBe('Your standup is at 10am.')
    expect(persistedAssistant.content).not.toContain('[1]')
    expect(persistedAssistant.serverId).toBe('srv-msg-9')
  })

  it('drops a message: side-frame instead of leaking its base64 into the reply', async () => {
    const { result } = renderHook(() => useChat())
    const sideFrame = b64(JSON.stringify({ id: 'file-msg', text: 'side' }))
    await act(async () => {
      const p = result.current.send('summarize this file')
      await waitForStream(0)
      streams[0].push('data: Here is the summary.\n')
      // A `message:` side-frame (file-chat) must NOT be concatenated as text.
      streams[0].push(`message: ${sideFrame}\n`)
      streams[0].push(
        `done: ${b64(JSON.stringify({ id: 'srv', text: 'Here is the summary.' }))}\n\n`
      )
      streams[0].close()
      await p
    })
    const content = lastAssistant(result.current.history)?.content ?? ''
    expect(content).toBe('Here is the summary.')
    expect(content).not.toContain('message:')
    expect(content).not.toContain(sideFrame)
  })
})

describe('useChat — blank-reply guard', () => {
  it('surfaces an error instead of persisting a blank bubble when the stream ends empty', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('when is standup')
      await waitForStream(0)
      // 200 OK, zero bytes: no data chunks, no done: frame — the stream just ends.
      streams[0].close()
      await p
    })
    // The empty pending bubble is replaced with the error copy, not left blank.
    expect(lastAssistant(result.current.history)?.content).toBe(
      "Omi didn't send a reply. Try again."
    )
    // The FINAL persisted assistant message carries the error, never blank text.
    const finalThread = persisted.at(-1) as { role: string; content: string }[]
    const persistedAssistant = [...finalThread].reverse().find((m) => m.role === 'assistant')
    expect(persistedAssistant?.content).toBe("Omi didn't send a reply. Try again.")
    expect(persistedAssistant?.content).not.toBe('')
    // Like the catch path, the no-reply error is never spoken.
    expect(speakSpy).not.toHaveBeenCalled()
  })

  it('does not speak the no-reply error on a voice turn', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('when is standup', { fromVoice: true })
      await waitForStream(0)
      streams[0].close()
      await p
    })
    expect(lastAssistant(result.current.history)?.content).toBe(
      "Omi didn't send a reply. Try again."
    )
    expect(speakSpy).not.toHaveBeenCalled()
  })

  it('renders streamed text unchanged (guard does not fire)', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('hi')
      await waitForStream(0)
      streams[0].push('data: hello there\n')
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv', text: 'hello there' }))}\n\n`)
      streams[0].close()
      await p
    })
    expect(lastAssistant(result.current.history)?.content).toBe('hello there')
  })

  it('renders a done-only reply (text in the done frame, no data chunks)', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('hi')
      await waitForStream(0)
      // No `data:` chunks at all — only the terminal done frame carries text.
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv', text: 'from done only' }))}\n\n`)
      streams[0].close()
      await p
    })
    expect(lastAssistant(result.current.history)?.content).toBe('from done only')
  })

  it('does not fire when a done frame carries structured content with empty text', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('chart me')
      await waitForStream(0)
      // Empty text but a chart payload — an intentional empty-but-valid completion.
      streams[0].push(
        `done: ${b64(JSON.stringify({ id: 'srv', text: '', chart_data: { series: [1, 2, 3] } }))}\n\n`
      )
      streams[0].close()
      await p
    })
    const msg = lastAssistant(result.current.history) as { content: string; chartData?: unknown }
    expect(msg.content).toBe('')
    expect(msg.content).not.toBe("Omi didn't send a reply. Try again.")
    expect(msg.chartData).toEqual({ series: [1, 2, 3] })
  })
})

describe('useChat — C5 abort on reset', () => {
  it('aborts the fetch and never persists/renders a dismissed reply; a new send is unaffected', async () => {
    const { result } = renderHook(() => useChat())

    // Start a send and let one chunk stream in.
    let firstSend: Promise<void>
    await act(async () => {
      firstSend = result.current.send('question one')
      await waitForStream(0)
      streams[0].push('data: partial zombie reply\n')
      await flush()
    })
    expect(lastAssistant(result.current.history)?.content).toBe('partial zombie reply')

    // Dismiss mid-stream.
    act(() => result.current.reset())
    expect(signals[0]?.aborted).toBe(true)
    expect(result.current.history).toEqual([])

    // The stream keeps draining (more text + a done frame) AFTER the dismiss —
    // none of it may reach state or SQLite.
    await act(async () => {
      streams[0].push('data: more zombie\n')
      streams[0].push(
        `done: ${b64(JSON.stringify({ id: 'z', text: 'ZOMBIE FINAL', ask_for_nps: false }))}\n\n`
      )
      streams[0].close()
      await firstSend
    })
    expect(result.current.history).toEqual([])
    const anyZombiePersisted = persisted.some((thread) =>
      thread.some((m) => /zombie|ZOMBIE FINAL/i.test(m.content))
    )
    expect(anyZombiePersisted).toBe(false)
    expect(speakSpy).not.toHaveBeenCalled()

    // A fresh send after the dismiss streams cleanly into a new thread.
    await act(async () => {
      const p = result.current.send('question two')
      await waitForStream(1)
      streams[1].push('data: clean answer\n')
      streams[1].push(`done: ${b64(JSON.stringify({ id: 'srv-2', text: 'clean answer' }))}\n\n`)
      streams[1].close()
      await p
    })
    expect(lastAssistant(result.current.history)?.content).toBe('clean answer')
    expect((lastAssistant(result.current.history) as { serverId?: string }).serverId).toBe('srv-2')
  })
})

describe('useChat — C5 stream watchdog (180s)', () => {
  // Under fake timers, send()'s pre-fetch awaits (token, context, fetch) are
  // microtasks — advancing 1ms flushes them, opening the stream.
  const pumpFakeUntilStream = async (i: number): Promise<void> => {
    for (let k = 0; k < 100 && !streams[i]; k++) await vi.advanceTimersByTimeAsync(1)
    if (!streams[i]) throw new Error(`stream ${i} never opened`)
  }

  it('aborts a wedged stream at the deadline, unlatches, and surfaces the timeout copy', async () => {
    vi.useFakeTimers()
    try {
      const { result } = renderHook(() => useChat())
      await act(async () => {
        void result.current.send('never finishes')
        await pumpFakeUntilStream(0)
        streams[0].push('data: partial and then silence forever\n') // never closes
        await vi.advanceTimersByTimeAsync(1)
      })
      expect(result.current.sending).toBe(true)

      // Just before the deadline: still streaming, not aborted.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_STREAM_TIMEOUT_MS - 1000)
      })
      expect(signals[0]?.aborted).toBe(false)
      expect(result.current.sending).toBe(true)

      // Crossing the deadline: watchdog aborts, engine unlatches, timeout shown.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })
      expect(signals[0]?.aborted).toBe(true)
      expect(result.current.sending).toBe(false)
      expect(lastAssistant(result.current.history)?.content).toBe(
        'Response took too long. Try again.'
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it("an earlier send's watchdog never aborts or times out a later generation", async () => {
    vi.useFakeTimers()
    try {
      const { result } = renderHook(() => useChat())
      // Send #1 wedges.
      await act(async () => {
        void result.current.send('first, will be dismissed')
        await pumpFakeUntilStream(0)
        streams[0].push('data: partial one\n')
        await vi.advanceTimersByTimeAsync(1)
      })
      // Dismiss #1 and immediately open a fresh generation (#2), which wedges too.
      await act(async () => {
        result.current.reset()
        void result.current.send('second, fresh generation')
        await pumpFakeUntilStream(1)
        streams[1].push('data: partial two\n')
        await vi.advanceTimersByTimeAsync(1)
      })
      // #1's teardown must not have aborted #2 nor unlatched the engine.
      expect(signals[1]?.aborted).toBe(false)
      expect(result.current.sending).toBe(true)

      // Advancing a FULL deadline from here fires ONLY #2's own fresh watchdog —
      // #1's (cleared on its dismissal) can't reach across to this generation.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(CHAT_STREAM_TIMEOUT_MS)
      })
      expect(signals[1]?.aborted).toBe(true)
      expect(result.current.sending).toBe(false)
      expect(lastAssistant(result.current.history)?.content).toBe(
        'Response took too long. Try again.'
      )
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('useChat — C5 abort on reset (agent-task path)', () => {
  it('reset during an in-flight agent task persists nothing from it and never steals the latch', async () => {
    // First send is an agent task; later sends fall through to normal chat.
    agentMocks.detectAgentTask.mockReturnValueOnce({ prompt: 'refactor the parser' })
    const { result } = renderHook(() => useChat())

    // Kick off the agent task (codingAgentRun stays pending until we resolve it).
    await act(async () => {
      void result.current.send('use an agent to refactor the parser')
      for (let k = 0; k < 100 && !agentRunTaskId; k++) await flush()
    })
    expect(agentRunTaskId).toBeTruthy()
    expect(result.current.sending).toBe(true)
    expect(result.current.agentActive).toBe(true)

    // The agent streams some output into the bubble.
    await act(async () => {
      agentEventCb?.({
        taskId: agentRunTaskId as string,
        type: 'text_delta',
        text: 'zombie agent output'
      } as CodingAgentEvent)
      await flush()
    })

    // Dismiss mid-task: cancels the subprocess, clears UI, unlatches, bumps gen.
    act(() => result.current.reset())
    expect(codingAgentCancelSpy).toHaveBeenCalledWith(agentRunTaskId)
    expect(result.current.sending).toBe(false)
    expect(result.current.agentActive).toBe(false)
    expect(result.current.history).toEqual([])

    // A fresh chat send takes over and starts streaming (holds the busy latch).
    await act(async () => {
      void result.current.send('what is next')
      await waitForStream(0)
      streams[0].push('data: clean answer\n')
      await flush()
    })
    expect(result.current.sending).toBe(true)
    expect(lastAssistant(result.current.history)?.content).toBe('clean answer')

    // NOW the dismissed agent run finally resolves. Its finally must NOT persist
    // the cancelled thread, unlatch the newer send, or clear the orb pose.
    await act(async () => {
      agentRunResolve?.({ ok: true, text: 'zombie final answer' })
      await flush()
    })
    expect(result.current.sending).toBe(true) // still owned by the chat send
    const anyZombie = persisted.some((thread) => thread.some((m) => /zombie/i.test(m.content)))
    expect(anyZombie).toBe(false)

    // The chat send completes cleanly and owns the final state.
    await act(async () => {
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv-x', text: 'clean answer' }))}\n\n`)
      streams[0].close()
      await flush()
    })
    expect(result.current.sending).toBe(false)
    expect(lastAssistant(result.current.history)?.content).toBe('clean answer')
    const finalThread = persisted.at(-1) as ChatMessage[]
    expect(finalThread.some((m) => /zombie/i.test(m.content))).toBe(false)
  })
})

describe('useChat — recordVoiceTurn (native hub turn → one timeline, no LLM/TTS)', () => {
  it('appends the user + assistant messages and persists them, with NO fetch', async () => {
    const { result } = renderHook(() => useChat())
    act(() => result.current.recordVoiceTurn('what time is it', "it's noon"))
    await act(async () => {
      await flush()
    })
    expect(result.current.history.map((m) => [m.role, m.content])).toEqual([
      ['user', 'what time is it'],
      ['assistant', "it's noon"]
    ])
    const thread = persisted.at(-1) as ChatMessage[]
    expect(thread.map((m) => [m.role, m.content])).toEqual([
      ['user', 'what time is it'],
      ['assistant', "it's noon"]
    ])
    // Append-only: it must NOT re-answer via the LLM stream.
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('ignores an empty turn (missing user or assistant text)', () => {
    const { result } = renderHook(() => useChat())
    act(() => result.current.recordVoiceTurn('', 'orphan'))
    act(() => result.current.recordVoiceTurn('orphan', '   '))
    expect(result.current.history).toHaveLength(0)
  })
})

describe('useChat — chat attachments (file_ids)', () => {
  const pick = (name: string): PickedChatFile => ({
    name,
    mimeType: 'text/plain',
    size: 3,
    bytes: new Uint8Array([1, 2, 3])
  })
  const fileChat = (name: string): FileChat => ({
    id: `srv-${name}`,
    name,
    mime_type: 'text/plain',
    openai_file_id: `oai-${name}`,
    created_at: '2026-07-14T00:00:00Z'
  })
  const immediateUpload = async (f: { name: string }): Promise<FileChat> => fileChat(f.name)
  // An upload whose settlement the test controls.
  function deferredUpload(): {
    upload: (f: { name: string }) => Promise<FileChat>
    resolve: (n: string) => void
  } {
    const resolvers = new Map<string, (fc: FileChat) => void>()
    const upload = (f: { name: string }): Promise<FileChat> =>
      new Promise<FileChat>((res) => resolvers.set(f.name, res))
    return { upload, resolve: (n) => resolvers.get(n)?.(fileChat(n)) }
  }

  it('sends NO file_ids and a byte-identical body when there are no attachments (regression guard)', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('hi')
      await waitForStream(0)
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv', text: 'hello' }))}\n\n`)
      streams[0].close()
      await p
    })
    // Body is exactly `{ text: 'hi' }` — no file_ids key at all.
    expect(JSON.parse(bodies[0])).toEqual({ text: 'hi' })
    expect(bodies[0]).not.toContain('file_ids')
  })

  it('includes uploaded attachments as file_ids and attaches them to the user message', async () => {
    addAttachments([pick('a.txt')], { upload: immediateUpload })
    await awaitUploadsSettled()

    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('describe this')
      await waitForStream(0)
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv', text: 'ok' }))}\n\n`)
      streams[0].close()
      await p
    })

    expect(JSON.parse(bodies[0])).toEqual({ text: 'describe this', file_ids: ['srv-a.txt'] })
    const userMsg = result.current.history.find((m) => m.role === 'user') as {
      attachments?: { id: string; name: string; mimeType: string }[]
    }
    expect(userMsg.attachments).toEqual([
      { id: 'srv-a.txt', name: 'a.txt', mimeType: 'text/plain' }
    ])
  })

  it('allows an attachment-only send (empty text) — the guard keys on text OR files', async () => {
    addAttachments([pick('img.png')], { upload: immediateUpload })
    await awaitUploadsSettled()

    const { result } = renderHook(() => useChat())
    await act(async () => {
      const p = result.current.send('')
      await waitForStream(0)
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv', text: 'ok' }))}\n\n`)
      streams[0].close()
      await p
    })
    // NOT dropped: it opened /v2/messages with the file_ids and empty text.
    expect(JSON.parse(bodies[0])).toEqual({ text: '', file_ids: ['srv-img.png'] })
  })

  it('still drops a truly empty send — no text AND no attachments', async () => {
    const { result } = renderHook(() => useChat())
    await act(async () => {
      await result.current.send('   ')
      await flush()
    })
    expect(streams[0]).toBeUndefined() // never opened a fetch
  })

  it('aborts an attachment-only send when every upload FAILED (no empty POST)', async () => {
    // The guard passes at click time (an attachment is pending), but after the
    // uploads settle they all failed → zero file_ids + empty text. Must NOT post.
    const failing = (): Promise<never> => Promise.reject(new Error('upload failed'))
    addAttachments([pick('x.png')], { upload: failing })
    await awaitUploadsSettled()

    const { result } = renderHook(() => useChat())
    await act(async () => {
      await result.current.send('')
      await flush()
    })
    expect(streams[0]).toBeUndefined() // no fetch opened — the empty send was aborted
    // The failed attachment is LEFT for retry/remove, not silently cleared.
    expect(getPendingAttachments().map((a) => a.status)).toEqual(['failed'])
  })

  it('blocks the send until an in-flight upload settles (no half-uploaded send)', async () => {
    const { upload, resolve } = deferredUpload()
    addAttachments([pick('a.txt')], { upload }) // stays `uploading`

    const { result } = renderHook(() => useChat())
    let sendP: Promise<void> | undefined
    await act(async () => {
      sendP = result.current.send('later')
      await flush()
    })
    // The upload hasn't settled, so send must NOT have opened the /v2/messages fetch.
    expect(streams[0]).toBeUndefined()

    await act(async () => {
      resolve('a.txt') // upload finishes → send unblocks
      await waitForStream(0)
      streams[0].push(`done: ${b64(JSON.stringify({ id: 'srv', text: 'ok' }))}\n\n`)
      streams[0].close()
      await sendP
    })
    expect(JSON.parse(bodies[0])).toEqual({ text: 'later', file_ids: ['srv-a.txt'] })
  })
})
