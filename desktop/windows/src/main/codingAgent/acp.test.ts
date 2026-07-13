import { spawn } from 'child_process'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AcpRuntimeAdapter } from './acp'
import { AdapterRuntimeError } from './failures'
import type { AdapterAttemptContext, AdapterStreamEvent } from './interface'
import {
  answerCommonHandshake,
  createMockProcess,
  notify,
  respond,
  scriptJsonRpc,
  type MockAcpProcess
} from './acp.testkit'

vi.mock('child_process', async () => {
  const actual = await vi.importActual<typeof import('child_process')>('child_process')
  return {
    ...actual,
    spawn: vi.fn(),
    execFile: vi.fn()
  }
})

function makeAttemptContext(
  adapterNativeSessionId = 'native-session-1',
  adapterId = 'acp'
): AdapterAttemptContext {
  return {
    sessionId: 'omi-session',
    runId: 'omi-run',
    attemptId: 'omi-attempt',
    binding: {
      sessionId: 'omi-session',
      adapterId,
      adapterNativeSessionId,
      resumeFidelity: 'native',
      cwd: 'C:/work'
    },
    prompt: [{ type: 'text', text: 'hello' }],
    mode: 'act'
  }
}

describe('AcpRuntimeAdapter (mocked subprocess)', () => {
  let proc: MockAcpProcess

  beforeEach(() => {
    vi.mocked(spawn).mockReset()
    proc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(proc as never)
  })

  afterEach(() => {
    // A timed-out test can abandon its own cleanup — never leak fake timers
    // into the next test.
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  function makeAdapter(): AcpRuntimeAdapter {
    // Default "acp" adapter shape but with a stub entry path — spawn is mocked,
    // so the file never actually runs.
    return new AcpRuntimeAdapter({ acpEntry: 'stub-entry.mjs' })
  }

  it('opens a binding via initialize + session/new + session/set_model + session/set_mode', async () => {
    const adapter = makeAdapter()
    const seen = scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/set_model' && message.id !== undefined) {
        expect(message.params).toMatchObject({ sessionId: 'native-session-1', modelId: 'model-x' })
        respond(proc, message.id, null)
      }
    })

    const binding = await adapter.openBinding({
      sessionId: 'omi-session',
      cwd: 'C:/work',
      model: 'model-x'
    })

    expect(binding.adapterNativeSessionId).toBe('native-session-1')
    expect(binding.sessionId).toBe('omi-session')
    expect(binding.model).toBe('model-x')
    expect(seen.map((m) => m.method)).toEqual([
      'initialize',
      'session/new',
      'session/set_model',
      'session/set_mode'
    ])
    await adapter.stop()
  })

  it('pins the acp session to "default" permission mode so the machine global cannot disable its tools', async () => {
    const adapter = makeAdapter()
    let setModeParams: Record<string, unknown> | undefined
    scriptJsonRpc(proc, (message) => {
      if (message.method === 'initialize' && message.id !== undefined) {
        respond(proc, message.id, { protocolVersion: 1 })
      }
      if (message.method === 'session/new' && message.id !== undefined) {
        respond(proc, message.id, { sessionId: 'native-session-1' })
      }
      if (message.method === 'session/set_mode' && message.id !== undefined) {
        setModeParams = message.params as Record<string, unknown>
        respond(proc, message.id, {})
      }
    })

    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })

    // Regression: without an explicit set_mode the session inherits the user's
    // global ~/.claude permissions.defaultMode (e.g. 'plan'/'dontAsk'), which
    // disables Write/Bash — the agent connects but can't actually do anything.
    // Verified end to end against real Claude Code: default mode routes tool
    // calls through resolveAcpPermission (high-trust auto-approve) and they run.
    expect(setModeParams).toMatchObject({ sessionId: 'native-session-1', modeId: 'default' })
    await adapter.stop()
  })

  it('streams session/update events into canonical adapter events and returns usage', async () => {
    const adapter = makeAdapter()
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/prompt' && message.id !== undefined) {
        notify(proc, 'session/update', {
          update: {
            sessionUpdate: 'tool_call',
            toolCallId: 'tool-1',
            title: 'Read file',
            status: 'in_progress',
            rawInput: { path: 'a.txt' }
          }
        })
        notify(proc, 'session/update', {
          update: {
            sessionUpdate: 'agent_message_chunk',
            content: { type: 'text', text: 'Done reading.' }
          }
        })
        respond(proc, message.id, {
          stopReason: 'end_turn',
          usage: { inputTokens: 10, outputTokens: 5, cachedReadTokens: 2, cachedWriteTokens: 1 },
          _meta: { costUsd: 0.012 }
        })
      }
    })

    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })

    const events: AdapterStreamEvent[] = []
    const result = await adapter.executeAttempt(
      makeAttemptContext(),
      (event) => events.push(event),
      new AbortController().signal
    )

    expect(result.terminalStatus).toBe('succeeded')
    expect(result.text).toBe('Done reading.')
    expect(result.adapterSessionId).toBe('native-session-1')
    expect(result.costUsd).toBeCloseTo(0.012)
    expect(result.inputTokens).toBe(10)
    expect(result.outputTokens).toBe(5)
    expect(events).toEqual([
      {
        type: 'tool_activity',
        name: 'Read file',
        status: 'started',
        toolUseId: 'tool-1',
        input: { path: 'a.txt' }
      },
      // Pending tool completes when the first message text arrives.
      { type: 'tool_activity', name: 'Read file', status: 'completed', toolUseId: 'tool-1' },
      { type: 'text_delta', text: 'Done reading.' }
    ])
    await adapter.stop()
  })

  it('auto-resolves session/request_permission via the trusted policy for adapter id acp', async () => {
    const adapter = makeAdapter()
    let promptId: number | undefined
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/prompt' && message.id !== undefined) {
        promptId = message.id
        // Adapter must answer this request before the prompt resolves.
        proc.stdout.write(
          `${JSON.stringify({
            jsonrpc: '2.0',
            id: 999,
            method: 'session/request_permission',
            params: {
              options: [
                { kind: 'allow_once', optionId: 'once' },
                { kind: 'allow_always', optionId: 'always' }
              ]
            }
          })}\n`
        )
      }
      if (message.id === undefined && message.method) return
      // The permission reply is a raw response (no method) with id 999.
      if (message.method === undefined && message.id === 999) {
        expect(message.result).toEqual({ outcome: { outcome: 'selected', optionId: 'always' } })
        if (promptId !== undefined) respond(proc, promptId, { stopReason: 'end_turn' })
      }
    })

    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
    const result = await adapter.executeAttempt(
      makeAttemptContext(),
      () => {},
      new AbortController().signal
    )
    expect(result.terminalStatus).toBe('succeeded')
    await adapter.stop()
  })

  it('rejects pending requests with a sanitized typed failure when the process exits', async () => {
    const adapter = makeAdapter()
    scriptJsonRpc(proc, (message) => {
      if (message.method === 'initialize' && message.id !== undefined) {
        respond(proc, message.id, {})
        return
      }
      if (message.method === 'session/new') {
        // Simulate a crash mid-request with a secret in stderr.
        proc.stderr.write('fatal: auth failed Bearer abc123secrettoken and sk-aaaabbbbccccdddd\n')
        setImmediate(() => proc.emit('exit', 1))
      }
    })

    const failure = await adapter
      .openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
      .then(() => null)
      .catch((error: unknown) => (error instanceof AdapterRuntimeError ? error.failure : null))

    expect(failure).not.toBeNull()
    expect(failure!.code).toBe('adapter_process_exited')
    expect(failure!.technicalMessage).toContain('Bearer [redacted]')
    expect(failure!.technicalMessage).toContain('sk-[redacted]')
    expect(failure!.technicalMessage).not.toContain('abc123secrettoken')
  })

  it('cancels a session that makes no recognized progress within the watchdog window', async () => {
    const adapter = new AcpRuntimeAdapter({
      adapterId: 'hermes',
      command: 'hermes acp',
      noProgressTimeoutMs: 10_000
    })
    const cancels: unknown[] = []
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/cancel') {
        cancels.push(message.params)
      }
      // session/prompt intentionally never answered — the watchdog must fire.
    })

    // Handshake runs on real timers (stream delivery); only the watchdog wait
    // itself is virtualized.
    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
    vi.useFakeTimers()
    try {
      const attempt = adapter.executeAttempt(
        makeAttemptContext('native-session-1', 'hermes'),
        () => {},
        new AbortController().signal
      )
      const outcome = attempt.catch((error: Error) => error)
      // The watchdog polls every timeoutMs/6 = 1666ms; the first tick at which
      // idle time exceeds 10s is tick 7 (11,662ms) — advance past it.
      await vi.advanceTimersByTimeAsync(13_000)
      const error = await outcome
      expect(error).toBeInstanceOf(Error)
      expect((error as Error).message).toContain('no progress')
      expect(cancels).toEqual([{ sessionId: 'native-session-1' }])
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports per-attempt cost as the delta of cumulative usage_update notifications', async () => {
    const adapter = makeAdapter()
    let promptCount = 0
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/prompt' && message.id !== undefined) {
        promptCount++
        notify(proc, 'session/update', {
          sessionId: 'native-session-1',
          update: {
            sessionUpdate: 'usage_update',
            used: 10,
            size: 200000,
            // Cumulative session cost: 0.05 after attempt 1, 0.08 after attempt 2.
            cost: { amount: promptCount === 1 ? 0.05 : 0.08, currency: 'USD' }
          }
        })
        respond(proc, message.id, { stopReason: 'end_turn' })
      }
    })

    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
    const first = await adapter.executeAttempt(
      makeAttemptContext(),
      () => {},
      new AbortController().signal
    )
    const second = await adapter.executeAttempt(
      makeAttemptContext(),
      () => {},
      new AbortController().signal
    )

    expect(first.costUsd).toBeCloseTo(0.05)
    expect(second.costUsd).toBeCloseTo(0.03) // 0.08 cumulative − 0.05 already reported
    await adapter.stop()
  })

  it('ignores session/update notifications from other sessions', async () => {
    const adapter = makeAdapter()
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/prompt' && message.id !== undefined) {
        // Another session's stream must never contaminate this attempt.
        notify(proc, 'session/update', {
          sessionId: 'some-other-session',
          update: {
            sessionUpdate: 'agent_message_chunk',
            content: { type: 'text', text: 'WRONG SESSION ' }
          }
        })
        notify(proc, 'session/update', {
          sessionId: 'native-session-1',
          update: {
            sessionUpdate: 'agent_message_chunk',
            content: { type: 'text', text: 'right session' }
          }
        })
        respond(proc, message.id, { stopReason: 'end_turn' })
      }
    })

    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
    const events: AdapterStreamEvent[] = []
    const result = await adapter.executeAttempt(
      makeAttemptContext(),
      (event) => events.push(event),
      new AbortController().signal
    )

    expect(result.text).toBe('right session')
    expect(events).toEqual([{ type: 'text_delta', text: 'right session' }])
    await adapter.stop()
  })

  it('settles a cancelled attempt even when the adapter never answers (no-watchdog path)', async () => {
    const adapter = makeAdapter() // adapterId "acp" → noProgressTimeoutMs 0
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      // session/prompt intentionally never answered.
    })

    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
    const abort = new AbortController()
    const attempt = adapter.executeAttempt(makeAttemptContext(), () => {}, abort.signal)
    const outcome = attempt.catch((error: Error) => error)
    abort.abort()
    const error = await outcome
    expect(error).toBeInstanceOf(Error)
    expect((error as Error).message).toContain('cancelled')
  })

  it('pre-aborted attempts still observe the in-flight request (no unhandled rejection)', async () => {
    const adapter = makeAdapter()
    scriptJsonRpc(proc, (message) => {
      answerCommonHandshake(proc, message)
      // session/prompt intentionally never answered.
    })
    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })

    const abort = new AbortController()
    abort.abort() // aborted BEFORE the attempt starts
    const error = await adapter
      .executeAttempt(makeAttemptContext(), () => {}, abort.signal)
      .catch((e: Error) => e)
    expect((error as Error).message).toContain('cancelled')

    // The pending session/prompt request now rejects (process exit). It must
    // already have handlers attached — an unhandled rejection here would fail
    // the vitest run.
    proc.emit('exit', 1)
    await new Promise((resolve) => setImmediate(resolve))
  })

  it('dispatches session/cancel on cancelAttempt', async () => {
    const adapter = makeAdapter()
    const cancels: unknown[] = []
    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/cancel') cancels.push(message.params)
    })
    await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })

    const dispatch = await adapter.cancelAttempt({
      sessionId: 'omi-session',
      binding: {
        sessionId: 'omi-session',
        adapterId: 'acp',
        adapterNativeSessionId: 'native-session-1',
        resumeFidelity: 'native',
        cwd: 'C:/work'
      }
    })

    expect(dispatch).toEqual({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false
    })
    // notify() is fire-and-forget; give the PassThrough a tick to flush.
    await new Promise((resolve) => setImmediate(resolve))
    expect(cancels).toEqual([{ sessionId: 'native-session-1' }])
    await adapter.stop()
  })
})
