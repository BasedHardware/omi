// runMainChatTurn routing tests — the kernel-routed main-chat door (PR-E1) driven
// end to end against a real SQLite store and a fake `pi-mono` adapter.
//
// Driver: injects node:sqlite's DatabaseSync via the store's `databaseFactory`
// seam (better-sqlite3 is rebuilt for Electron's ABI and cannot load under
// plain-node Vitest), exactly as kernel.test.ts does. This exercises the real
// resolveSurfaceSession -> sendAgentMessage -> subscribe/projection path, not mocks.
//
// Hermetic: no network, no sleeps, no timers — concurrency is coordinated by
// releasing adapter gates once both runs have been accepted.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from '../agentKernel/kernel'
import { AdapterRegistry } from '../agentKernel/adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from '../agentKernel/store'
import type { AgentEvent } from '../agentKernel/types'
import type {
  AdapterAttemptContext,
  AdapterAttemptResult,
  AdapterBindingHandle,
  AdapterCapabilities,
  AdapterEventSink,
  AdapterStreamEvent,
  CancelAttemptContext,
  CancelDispatchResult,
  OpenBindingInput,
  ResumeBindingInput,
  RuntimeAdapter
} from '../codingAgent/interface'
import type { MainChatEvent } from '../../shared/types'
import { DEFAULT_LOCAL_OWNER_ID } from '../agentKernel/controlTools'
import { projectKernelEvent, runMainChatTurn } from './mainChat'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const OWNER = 'owner-1'
const ADAPTER_ID = 'pi-mono'

afterEach(() => {
  nativeSessionCounter = 0
  for (const store of openStores.splice(0)) {
    try {
      store.close()
    } catch {
      // already closed
    }
  }
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

// === Fake pi-mono adapter ====================================================

interface Gate {
  promise: Promise<void>
  release: () => void
}

interface FakeAdapterOptions {
  /** Events the adapter streams (in order) before resolving. */
  stream?: (promptText: string) => AdapterStreamEvent[]
  /** Reply text (default: `reply:<prompt>`). */
  reply?: (promptText: string) => string
  /** Per-prompt gate map — executeAttempt awaits gates.get(promptText). */
  gates?: Map<string, Gate>
  /** When set, executeAttempt RETURNS terminalStatus:'failed' with this userMessage
   *  (the adapter-returned failure path — payload.failure.userMessage, no
   *  errorMessage), rather than throwing. */
  fail?: string
}

let nativeSessionCounter = 0

const capabilities: AdapterCapabilities = {
  resumeFidelity: 'native',
  supportsNativeResume: true,
  supportsCancellation: true,
  acknowledgesCancellation: true,
  requiresPinnedWorker: false,
  supportsModelSwitching: true,
  supportsArtifactEmission: false,
  supportsTools: true,
  restartBehavior: 'native_bindings_survive'
}

interface FakeAdapter extends RuntimeAdapter {
  readonly calls: {
    executeAttempt: AdapterAttemptContext[]
    cancelAttempt: CancelAttemptContext[]
    openBinding: OpenBindingInput[]
  }
}

function fakeAdapter(options: FakeAdapterOptions = {}): FakeAdapter {
  const calls: FakeAdapter['calls'] = { executeAttempt: [], cancelAttempt: [], openBinding: [] }
  return {
    adapterId: ADAPTER_ID,
    capabilities,
    calls,
    async start() {
      /* no-op fake */
    },
    async stop() {
      /* no-op fake */
    },
    async openBinding(input: OpenBindingInput): Promise<AdapterBindingHandle> {
      calls.openBinding.push(input)
      nativeSessionCounter += 1
      return {
        sessionId: input.sessionId,
        adapterId: ADAPTER_ID,
        adapterNativeSessionId: `native-${nativeSessionCounter}`,
        resumeFidelity: 'native',
        cwd: input.cwd,
        model: input.model
      }
    },
    async resumeBinding(input: ResumeBindingInput): Promise<AdapterBindingHandle> {
      return {
        sessionId: input.sessionId,
        adapterId: ADAPTER_ID,
        adapterNativeSessionId: input.adapterNativeSessionId,
        resumeFidelity: 'native',
        cwd: input.cwd,
        model: input.model
      }
    },
    async executeAttempt(
      context: AdapterAttemptContext,
      sink: AdapterEventSink,
      signal: AbortSignal
    ): Promise<AdapterAttemptResult> {
      calls.executeAttempt.push(context)
      const promptText = context.prompt.map((b) => (b.type === 'text' ? b.text : '')).join('')
      for (const event of options.stream?.(promptText) ?? [
        { type: 'text_delta', text: 'streaming' }
      ]) {
        sink(event)
      }
      const gate = options.gates?.get(promptText)
      if (gate) {
        await gate.promise
        if (signal.aborted) throw new Error('aborted')
      }
      if (options.fail !== undefined) {
        return {
          text: '',
          adapterSessionId: context.binding.adapterNativeSessionId,
          terminalStatus: 'failed',
          failure: {
            code: 'adapter_execution_failed',
            source: 'adapter_execution',
            userMessage: options.fail,
            retryable: false
          }
        }
      }
      return {
        text: options.reply?.(promptText) ?? `reply:${promptText}`,
        adapterSessionId: context.binding.adapterNativeSessionId,
        terminalStatus: 'succeeded',
        inputTokens: 10,
        outputTokens: 20,
        costUsd: 0.01
      }
    },
    async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
      calls.cancelAttempt.push(context)
      return { accepted: true, dispatchAttempted: true, adapterAcknowledged: true }
    }
  }
}

function makeGate(): Gate {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

// === Harness =================================================================

function newStore(): SqliteAgentStore {
  const dir = mkdtempSync(join(tmpdir(), 'omi-mainchat-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  return store
}

function newKernel(adapter: FakeAdapter, maxWorkers = 2): AgentRuntimeKernel {
  const registry = new AdapterRegistry()
  registry.register(adapter.adapterId, () => adapter, maxWorkers)
  return new AgentRuntimeKernel({ store: newStore(), registry, runtimeNodeId: 'node-a' })
}

// === projectKernelEvent (the enumerated type -> wire mapping) ================

function agentEvent(type: string, payload: unknown, runId = 'run-1'): AgentEvent {
  return {
    eventId: 'evt',
    sessionId: 'sess',
    runId,
    attemptId: 'att',
    type,
    retentionClass: 'core',
    visibility: 'ui',
    payloadJson: JSON.stringify(payload),
    createdAtMs: 0
  }
}

describe('projectKernelEvent', () => {
  const REQ = 'req-1'
  const RUN = 'run-1'

  it('maps message.delta -> text_delta', () => {
    expect(
      projectKernelEvent(agentEvent('message.delta', { type: 'text_delta', text: 'hi' }), REQ, RUN)
    ).toEqual({ type: 'text_delta', requestId: REQ, runId: RUN, text: 'hi' })
  })

  it('maps progress.updated(thinking) -> thinking_delta and ignores non-thinking', () => {
    expect(
      projectKernelEvent(
        agentEvent('progress.updated', { type: 'thinking_delta', text: 'mm' }),
        REQ,
        RUN
      )
    ).toEqual({ type: 'thinking_delta', requestId: REQ, runId: RUN, text: 'mm' })
    expect(
      projectKernelEvent(agentEvent('progress.updated', { type: 'other' }), REQ, RUN)
    ).toBeNull()
  })

  it('maps tool_activity payloads through the collapsed tool.* kernel types', () => {
    expect(
      projectKernelEvent(
        agentEvent('tool.started', {
          type: 'tool_activity',
          name: 'search',
          status: 'started',
          toolUseId: 't1'
        }),
        REQ,
        RUN
      )
    ).toEqual({
      type: 'tool_activity',
      requestId: REQ,
      runId: RUN,
      name: 'search',
      status: 'started',
      toolUseId: 't1',
      input: undefined
    })
  })

  it('distinguishes tool_result_display from tool_activity (both arrive as tool.completed)', () => {
    expect(
      projectKernelEvent(
        agentEvent('tool.completed', {
          type: 'tool_result_display',
          toolUseId: 't1',
          name: 'search',
          output: 'out'
        }),
        REQ,
        RUN
      )
    ).toEqual({
      type: 'tool_result_display',
      requestId: REQ,
      runId: RUN,
      toolUseId: 't1',
      name: 'search',
      output: 'out'
    })
  })

  it('maps message.completed -> completed and run.* terminals -> run_finished', () => {
    expect(projectKernelEvent(agentEvent('message.completed', { text: 'done' }), REQ, RUN)).toEqual(
      {
        type: 'completed',
        requestId: REQ,
        runId: RUN,
        text: 'done'
      }
    )
    expect(projectKernelEvent(agentEvent('run.succeeded', {}), REQ, RUN)).toEqual({
      type: 'run_finished',
      requestId: REQ,
      runId: RUN,
      status: 'succeeded'
    })
    expect(
      projectKernelEvent(agentEvent('run.failed', { errorMessage: 'boom' }), REQ, RUN)
    ).toEqual({
      type: 'run_finished',
      requestId: REQ,
      runId: RUN,
      status: 'failed',
      error: 'boom'
    })
    expect(projectKernelEvent(agentEvent('run.cancelled', {}), REQ, RUN)).toEqual({
      type: 'run_finished',
      requestId: REQ,
      runId: RUN,
      status: 'cancelled'
    })
  })

  it('ignores kernel events the chat UI does not render', () => {
    expect(projectKernelEvent(agentEvent('binding.created', {}), REQ, RUN)).toBeNull()
    expect(projectKernelEvent(agentEvent('usage.updated', {}), REQ, RUN)).toBeNull()
    expect(projectKernelEvent(agentEvent('attempt.failed', {}), REQ, RUN)).toBeNull()
  })
})

// === runMainChatTurn (real kernel + fake adapter) ============================

describe('runMainChatTurn', () => {
  it('streams projected events in order and resolves with the final outcome', async () => {
    const adapter = fakeAdapter({
      stream: () => [
        { type: 'text_delta', text: 'Hello ' },
        { type: 'text_delta', text: 'world' },
        { type: 'tool_activity', name: 'search', status: 'started', toolUseId: 't1' },
        { type: 'tool_activity', name: 'search', status: 'completed', toolUseId: 't1' }
      ],
      reply: () => 'Hello world'
    })
    const kernel = newKernel(adapter)
    const events: MainChatEvent[] = []

    const result = await runMainChatTurn(
      { requestId: 'req-1', prompt: 'hi there', cleanUserText: 'hi there' },
      (e) => events.push(e),
      { kernel, ownerId: OWNER }
    )

    expect(result).toMatchObject({
      ok: true,
      terminalStatus: 'succeeded',
      text: 'Hello world',
      requestId: 'req-1'
    })
    expect(result.runId).toBeTruthy()

    const types = events.map((e) => e.type)
    expect(types[0]).toBe('accepted')
    expect(types).toContain('text_delta')
    expect(types).toContain('tool_activity')
    expect(types).toContain('completed')
    expect(types[types.length - 1]).toBe('run_finished')

    // Text accumulates correctly, in order.
    const streamed = events
      .filter((e) => e.type === 'text_delta')
      .map((e) => (e as { text: string }).text)
    expect(streamed.join('')).toBe('Hello world')

    // Every event carries this run's id and the caller's requestId.
    expect(events.every((e) => e.runId === result.runId && e.requestId === 'req-1')).toBe(true)

    const terminal = events.at(-1) as Extract<MainChatEvent, { type: 'run_finished' }>
    expect(terminal.status).toBe('succeeded')
  })

  it('bakes the desktop-chat system prompt (initiative → spawn_agent) into the binding', async () => {
    // The macOS-parity fix: the model must receive the <initiative> instruction so
    // it hands long/coding work to spawn_agent instead of replying in text. Prove
    // the system prompt threads end to end — runMainChatTurn → sendAgentMessage →
    // executeRun → openBinding — by capturing what the adapter binding is opened
    // with. (piMono bakes this into the pi subprocess via --system-prompt.)
    const adapter = fakeAdapter({ reply: () => 'ok' })
    const kernel = newKernel(adapter)

    await runMainChatTurn({ requestId: 'req-sp', prompt: 'hi', cleanUserText: 'hi' }, () => {}, {
      kernel,
      ownerId: OWNER
    })

    expect(adapter.calls.openBinding).toHaveLength(1)
    const systemPrompt = adapter.calls.openBinding[0].systemPrompt ?? ''
    expect(systemPrompt).toContain('<initiative>')
    expect(systemPrompt).toContain('spawn_agent')
    expect(systemPrompt).toContain(
      'Work needing more than ~30 seconds of tool calls or research: start a background agent with spawn_agent'
    )
    // Persona is present too — this is the Omi desktop chat prompt, not pi's default.
    expect(systemPrompt).toContain('You are Omi')
  })

  it('reuses the binding across turns with the SAME system prompt (no per-turn restart)', async () => {
    // A stable prompt must not restart the pi subprocess every message. With an
    // identical system-prompt hash, the second turn resumes the binding rather than
    // opening a new one.
    const adapter = fakeAdapter({ reply: () => 'ok' })
    const kernel = newKernel(adapter)

    await runMainChatTurn(
      { requestId: 'req-1', prompt: 'first', cleanUserText: 'first', chatId: 'chat-z' },
      () => {},
      { kernel, ownerId: OWNER }
    )
    await runMainChatTurn(
      { requestId: 'req-2', prompt: 'second', cleanUserText: 'second', chatId: 'chat-z' },
      () => {},
      { kernel, ownerId: OWNER }
    )

    // Opened exactly once — turn 2 resumed the same binding (same prompt hash).
    expect(adapter.calls.openBinding).toHaveLength(1)
    expect(adapter.calls.executeAttempt).toHaveLength(2)
  })

  it('records one clean user turn + one assistant turn (no double-append, verbatim forward)', async () => {
    let dispatchedPrompt = ''
    const adapter = fakeAdapter({
      reply: () => 'the answer',
      stream: (prompt) => {
        dispatchedPrompt = prompt
        return []
      }
    })
    const kernel = newKernel(adapter)
    const store = openStores[openStores.length - 1]

    // `prompt` is the context-prepended string; `cleanUserText` is the raw message.
    // The adapter must receive `prompt` verbatim; the transcript must store the
    // clean text — never the contexted prompt.
    await runMainChatTurn(
      {
        requestId: 'req-1',
        prompt: '<<context>>\nthe question',
        cleanUserText: 'the question'
      },
      () => {},
      { kernel, ownerId: OWNER }
    )

    expect(store.allRows('SELECT run_id FROM runs')).toHaveLength(1)
    expect(store.allRows('SELECT attempt_id FROM run_attempts')).toHaveLength(1)
    // Adapter got the verbatim contexted prompt.
    expect(dispatchedPrompt).toBe('<<context>>\nthe question')
    // Transcript: clean user turn (main-side record) THEN assistant turn (the run),
    // both on the same conversation. The user turn stores the CLEAN text, not the
    // contexted prompt.
    const turns = store.allRows(
      'SELECT role, content, conversation_id FROM conversation_turns ORDER BY created_at_ms ASC, rowid ASC'
    )
    expect(turns.map((t) => t.role)).toEqual(['user', 'assistant'])
    expect(turns[0].content).toBe('the question')
    expect(turns[1].content).toBe('the answer')
    // Both turns landed on the same conversation the run used (no forked transcript).
    expect(turns[0].conversation_id).toBe(turns[1].conversation_id)
    // Exactly one of each — no double assistant append, adapter ran once.
    expect(adapter.calls.executeAttempt).toHaveLength(1)
  })

  it('injects the prior-turn tail as <conversation_history> on the next turn (per-session memory)', async () => {
    const dispatched: string[] = []
    const adapter = fakeAdapter({
      reply: (prompt) => `reply-to:${prompt.slice(-40)}`,
      stream: (prompt) => {
        dispatched.push(prompt)
        return []
      }
    })
    const kernel = newKernel(adapter)

    // Turn 1 on chat-x: the conversation is empty, so NO tail is prepended — the
    // adapter gets exactly the prompt.
    await runMainChatTurn(
      {
        requestId: 'req-1',
        prompt: 'what is the capital of france',
        cleanUserText: 'q1',
        chatId: 'chat-x'
      },
      () => {},
      { kernel, ownerId: OWNER }
    )
    expect(dispatched[0]).toBe('what is the capital of france')
    expect(dispatched[0]).not.toContain('<conversation_history>')

    // Turn 2 on the SAME chat-x: turn 1's user + assistant turns are now in the
    // transcript, so they are prepended as a <conversation_history> block, and the
    // current message is NOT duplicated into that block (read happens before record).
    await runMainChatTurn(
      { requestId: 'req-2', prompt: 'and its population', cleanUserText: 'q2', chatId: 'chat-x' },
      () => {},
      { kernel, ownerId: OWNER }
    )
    const second = dispatched[1]
    expect(second).toContain('<conversation_history>')
    expect(second).toContain('q1') // turn-1 clean user text
    expect(second).toContain('reply-to') // turn-1 assistant text
    expect(second).not.toContain('q2') // current turn is NOT in the injected tail
    expect(second.endsWith('and its population')).toBe(true) // prompt appended after the tail

    // A DIFFERENT chat gets no cross-session leak — its tail is empty.
    await runMainChatTurn(
      { requestId: 'req-3', prompt: 'unrelated question', cleanUserText: 'q3', chatId: 'chat-y' },
      () => {},
      { kernel, ownerId: OWNER }
    )
    expect(dispatched[2]).toBe('unrelated question')
    expect(dispatched[2]).not.toContain('<conversation_history>')
  })

  it('isolates concurrent runs — one run’s events never leak into another’s stream', async () => {
    const gates = new Map<string, Gate>([
      ['PROMPT_A', makeGate()],
      ['PROMPT_B', makeGate()]
    ])
    const adapter = fakeAdapter({
      gates,
      stream: (prompt) => [{ type: 'text_delta', text: `delta:${prompt}` }],
      reply: (prompt) => `reply:${prompt}`
    })
    const kernel = newKernel(adapter)

    const events: MainChatEvent[] = []
    let accepted = 0
    const emit = (e: MainChatEvent): void => {
      events.push(e)
      // Once both runs are in flight (both accepted), release the gates so they
      // complete concurrently with both subscriptions live.
      if (e.type === 'accepted') {
        accepted += 1
        if (accepted === 2) {
          gates.get('PROMPT_A')!.release()
          gates.get('PROMPT_B')!.release()
        }
      }
    }

    const pA = runMainChatTurn(
      { requestId: 'req-A', prompt: 'PROMPT_A', cleanUserText: 'PROMPT_A', chatId: 'chat-a' },
      emit,
      { kernel, ownerId: OWNER }
    )
    const pB = runMainChatTurn(
      { requestId: 'req-B', prompt: 'PROMPT_B', cleanUserText: 'PROMPT_B', chatId: 'chat-b' },
      emit,
      { kernel, ownerId: OWNER }
    )
    const [rA, rB] = await Promise.all([pA, pB])

    expect(rA.runId).not.toBe(rB.runId)
    expect(rA.ok && rB.ok).toBe(true)

    const eventsA = events.filter((e) => e.requestId === 'req-A')
    const eventsB = events.filter((e) => e.requestId === 'req-B')
    // No cross-contamination: A's stream carries only A's runId, B's only B's.
    expect(eventsA.every((e) => e.runId === rA.runId)).toBe(true)
    expect(eventsB.every((e) => e.runId === rB.runId)).toBe(true)
    // Each run streamed its own delta, not the other's.
    expect(eventsA.some((e) => e.type === 'text_delta' && e.text === 'delta:PROMPT_A')).toBe(true)
    expect(eventsB.some((e) => e.type === 'text_delta' && e.text === 'delta:PROMPT_B')).toBe(true)
    expect(eventsA.some((e) => e.type === 'text_delta' && e.text === 'delta:PROMPT_B')).toBe(false)
  })

  it('cancels an in-flight run and reports a cancelled terminal', async () => {
    const gates = new Map<string, Gate>([['PROMPT_C', makeGate()]])
    const adapter = fakeAdapter({ gates, stream: () => [{ type: 'text_delta', text: 'partial' }] })
    const kernel = newKernel(adapter)

    const events: MainChatEvent[] = []
    let runId: string | null = null
    let cancelScheduled = false
    const emit = (e: MainChatEvent): void => {
      events.push(e)
      if (e.type === 'accepted') runId = e.runId
      // Cancel once the adapter is mid-attempt (first delta) and parked on the
      // gate. Deferred off the subscriber stack (setImmediate) so cancelRun runs
      // non-re-entrantly, with the run active; then release the gate so the
      // adapter observes the abort and the run resolves cancelled.
      if (e.type === 'text_delta' && !cancelScheduled) {
        cancelScheduled = true
        const target = e.runId
        setImmediate(() => {
          void kernel
            .cancelRun(target, { ownerId: OWNER })
            .then(() => gates.get('PROMPT_C')!.release())
        })
      }
    }

    const result = await runMainChatTurn(
      { requestId: 'req-C', prompt: 'PROMPT_C', cleanUserText: 'PROMPT_C' },
      emit,
      { kernel, ownerId: OWNER }
    )

    expect(runId).toBeTruthy()
    expect(result.terminalStatus).toBe('cancelled')
    expect(result.ok).toBe(false)
    expect(adapter.calls.cancelAttempt).toHaveLength(1)
    const terminal = events.at(-1) as Extract<MainChatEvent, { type: 'run_finished' }>
    expect(terminal.status).toBe('cancelled')
  })

  it('propagates the error on an adapter-returned failure (failure.userMessage shape)', async () => {
    // The COMMON failure path: the adapter RETURNS terminalStatus:'failed' with a
    // failure object, so the kernel's run.failed payload carries the message at
    // failure.userMessage (NOT errorMessage). The streamed run_finished must still
    // surface it — a hand-crafted { errorMessage } unit fixture would miss this.
    const adapter = fakeAdapter({ fail: 'the model exploded' })
    const kernel = newKernel(adapter)
    const events: MainChatEvent[] = []

    const result = await runMainChatTurn(
      { requestId: 'req-f', prompt: 'boom', cleanUserText: 'boom' },
      (e) => events.push(e),
      { kernel, ownerId: OWNER }
    )

    expect(result.terminalStatus).toBe('failed')
    expect(result.ok).toBe(false)
    // The awaited invoke-return carries the error (from run.errorMessage).
    expect(result.error).toBe('the model exploded')
    // The STREAMED terminal event carries the same error — this is the wire
    // contract E2 builds against, and the regression the both-shape fix guards.
    const terminal = events.at(-1) as Extract<MainChatEvent, { type: 'run_finished' }>
    expect(terminal.status).toBe('failed')
    expect(terminal.error).toBe('the model exploded')
  })

  it('cold-start gate: refuses under the default owner without touching the kernel', async () => {
    // Before the auth relay wires the signed-in uid the owner is the shared
    // DEFAULT_LOCAL_OWNER_ID constant. A turn here must fail closed — never reach
    // resolveSurfaceSession, which would key a session under that constant and
    // collide across accounts. Use a kernel whose every method throws, proving the
    // gate refuses before any kernel call.
    const exploding = new Proxy(
      {},
      {
        get() {
          throw new Error('kernel must not be touched under an unknown owner')
        }
      }
    ) as unknown as AgentRuntimeKernel
    const events: MainChatEvent[] = []

    const result = await runMainChatTurn(
      { requestId: 'req-cold', prompt: 'hi', cleanUserText: 'hi' },
      (e) => events.push(e),
      { kernel: exploding, ownerId: DEFAULT_LOCAL_OWNER_ID }
    )

    expect(result.ok).toBe(false)
    expect(result.terminalStatus).toBe('failed')
    expect(result.error).toMatch(/sign-in has not completed/i)
    // No session was ever accepted — the gate fired before dispatch.
    expect(events.some((e) => e.type === 'accepted')).toBe(false)
    const terminal = events.at(-1) as Extract<MainChatEvent, { type: 'run_finished' }>
    expect(terminal.status).toBe('failed')
    expect(terminal.error).toMatch(/sign-in has not completed/i)
  })
})
