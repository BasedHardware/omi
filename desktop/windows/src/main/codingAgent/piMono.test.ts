// Ported from desktop/macos/agent/tests/pi-mono-adapter.test.ts, adapted to the
// Windows adapter: the constructor takes an options object (piPath /
// extensionPath / nodeBin), the subprocess spawns `nodeBin [piPath, ...args]`
// under ELECTRON_RUN_AS_NODE, and the RuntimeAdapter forwards only the narrow
// AdapterStreamEvent set to the kernel sink. All subprocess machinery is mocked;
// no real pi CLI is spawned.

import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { spawn } from 'child_process'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PiMonoAdapter, PiMonoRuntimeAdapter, HarnessFeature } from './piMono'
import type { AdapterAttemptContext, AdapterStreamEvent } from './interface'

vi.mock('child_process', async () => {
  const actual = await vi.importActual<typeof import('child_process')>('child_process')
  return {
    ...actual,
    spawn: vi.fn()
  }
})

type FakeProc = EventEmitter & {
  stdin: PassThrough
  stdout: PassThrough
  stderr: PassThrough
  kill: ReturnType<typeof vi.fn>
  pid: number
}

let currentProc: FakeProc | null = null

function newFakeProc(): FakeProc {
  // kill is a no-op (does NOT emit exit) so restart tests can spawn cleanly —
  // matches the macOS test harness.
  return Object.assign(new EventEmitter(), {
    stdin: new PassThrough(),
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    kill: vi.fn(),
    pid: 4242
  }) as FakeProc
}

// Typed view of the adapter's private surface so tests can drive RPC handlers
// and inspect internal state without `any` (lint forbids explicit any).
interface PiInternals {
  sendCommand: (cmd: Record<string, unknown>) => void
  handleTurnEnd: (event: Record<string, unknown>) => void
  handleToolStart: (event: Record<string, unknown>) => void
  handleToolEnd: (event: Record<string, unknown>) => void
  contextFilePath: string
  sessions: Map<string, unknown>
  process: EventEmitter | null
  activePromptGeneration: number
  pendingRequests: Map<number, unknown>
  eventHandler: ((event: unknown) => void) | null
}

function internals(adapter: PiMonoAdapter): PiInternals {
  return adapter as unknown as PiInternals
}

function createAdapter(
  configOverrides: {
    authToken?: string
    omiApiBaseUrl?: string
    onRestart?: (reason: string) => void
  } = {}
): { adapter: PiMonoAdapter; events: Array<Record<string, unknown>> } {
  const adapter = new PiMonoAdapter(
    { authToken: 'test-token', ...configOverrides },
    { piPath: '/fake/pi', extensionPath: '/fake/ext.ts', nodeBin: '/fake/node' }
  )
  const events: Array<Record<string, unknown>> = []
  internals(adapter).sendCommand = vi.fn()
  return { adapter, events }
}

function seedSessions(adapter: PiMonoAdapter, ...sessionIds: string[]): void {
  const sessions = internals(adapter).sessions
  for (const sessionId of sessionIds) {
    sessions.set(sessionId, { cwd: '/tmp' })
  }
}

type AttemptContextOverrides = Omit<Partial<AdapterAttemptContext>, 'binding'> & {
  binding?: Partial<AdapterAttemptContext['binding']>
}

function makeAttemptContext(overrides: AttemptContextOverrides = {}): AdapterAttemptContext {
  const attemptId = overrides.attemptId ?? 'att_runtime'
  const sessionId = overrides.sessionId ?? 'ses_runtime'
  const adapterNativeSessionId = overrides.binding?.adapterNativeSessionId ?? 'session-1'
  return {
    sessionId,
    ownerId: overrides.ownerId ?? 'owner-runtime',
    requestId: overrides.requestId ?? 'request-runtime',
    clientId: overrides.clientId ?? 'client-runtime',
    runId: overrides.runId ?? 'run_runtime',
    attemptId,
    binding: {
      bindingId: 'bind-runtime',
      sessionId,
      adapterId: 'pi-mono',
      adapterNativeSessionId,
      resumeFidelity: 'none',
      cwd: '/tmp',
      ...overrides.binding
    },
    prompt: overrides.prompt ?? [{ type: 'text', text: 'hello' }],
    tools: overrides.tools,
    mode: overrides.mode ?? 'act',
    metadata: overrides.metadata
  }
}

function makeTurnEndEvent(text: string, totalCost = 1.25): Record<string, unknown> {
  return {
    type: 'turn_end',
    message: {
      role: 'assistant',
      content: [{ type: 'text', text }],
      usage: {
        input: 11,
        output: 7,
        cacheRead: 3,
        cacheWrite: 2,
        totalTokens: 23,
        cost: { input: 0.1, output: 0.2, cacheRead: 0.3, cacheWrite: 0.4, total: totalCost }
      }
    }
  }
}

function makeErrorTurnEndEvent(errorMessage: string): Record<string, unknown> {
  return {
    type: 'turn_end',
    message: { role: 'assistant', errorMessage, content: [] }
  }
}

beforeEach(() => {
  currentProc = null
  vi.mocked(spawn).mockReset()
  vi.mocked(spawn).mockImplementation(() => {
    currentProc = newFakeProc()
    return currentProc as never
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PiMonoAdapter prompt correlation', () => {
  it('writes the active runtime attempt context before prompt execution', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const execution = runtime.executeAttempt(
      makeAttemptContext({ metadata: { protocolVersion: 2, disableSwiftBackedTools: true } }),
      () => {},
      new AbortController().signal
    )
    const relayContext = JSON.parse(readFileSync(internals(adapter).contextFilePath, 'utf8'))
    expect(relayContext).toMatchObject({
      adapterId: 'pi-mono',
      protocolVersion: 2,
      requestId: 'request-runtime',
      clientId: 'client-runtime',
      sessionId: 'ses_runtime',
      runId: 'run_runtime',
      attemptId: 'att_runtime',
      adapterSessionId: 'session-1',
      disableSwiftBackedTools: true
    })

    internals(adapter).handleTurnEnd(makeTurnEndEvent('done'))
    await expect(execution).resolves.toMatchObject({ terminalStatus: 'succeeded' })
    expect(existsSync(internals(adapter).contextFilePath)).toBe(false)
  })

  it('removes the runtime attempt context after adapter errors', async () => {
    const { adapter } = createAdapter()
    internals(adapter).sendCommand = vi.fn(() => {
      throw new Error('adapter send failed')
    })
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    await expect(
      runtime.executeAttempt(
        makeAttemptContext({ attemptId: 'att_error' }),
        () => {},
        new AbortController().signal
      )
    ).rejects.toThrow('adapter send failed')
    expect(existsSync(internals(adapter).contextFilePath)).toBe(false)
  })

  it('removes the runtime attempt context after abort (cancelled result)', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)
    const controller = new AbortController()

    const execution = runtime.executeAttempt(
      makeAttemptContext({ attemptId: 'att_abort' }),
      () => {},
      controller.signal
    )
    expect(JSON.parse(readFileSync(internals(adapter).contextFilePath, 'utf8')).attemptId).toBe(
      'att_abort'
    )
    controller.abort()

    await expect(execution).resolves.toMatchObject({ terminalStatus: 'cancelled' })
    expect(existsSync(internals(adapter).contextFilePath)).toBe(false)
  })

  it('rejects a concurrent attempt without clearing the active attempt context', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1', 'session-2')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const first = runtime.executeAttempt(
      makeAttemptContext({
        attemptId: 'att_first',
        binding: { adapterNativeSessionId: 'session-1' }
      }),
      () => {},
      new AbortController().signal
    )
    expect(JSON.parse(readFileSync(internals(adapter).contextFilePath, 'utf8')).attemptId).toBe(
      'att_first'
    )

    const second = runtime.executeAttempt(
      makeAttemptContext({
        attemptId: 'att_second',
        binding: { adapterNativeSessionId: 'session-2' }
      }),
      () => {},
      new AbortController().signal
    )

    await expect(second).rejects.toThrow('pi-mono prompt already in flight')
    expect(JSON.parse(readFileSync(internals(adapter).contextFilePath, 'utf8')).attemptId).toBe(
      'att_first'
    )

    internals(adapter).handleTurnEnd(makeTurnEndEvent('first done'))
    await expect(first).resolves.toMatchObject({ terminalStatus: 'succeeded' })
    expect(existsSync(internals(adapter).contextFilePath)).toBe(false)
  })

  it('removes invalid relay context for the completed attempt', () => {
    const { adapter } = createAdapter()
    writeFileSync(internals(adapter).contextFilePath, '{invalid json')

    adapter.clearRelayContextForAttempt('att_invalid')

    expect(existsSync(internals(adapter).contextFilePath)).toBe(false)
  })

  it('rejects a second prompt while one is in flight and never emits a result event', async () => {
    const { adapter, events } = createAdapter()
    seedSessions(adapter, 'session-1', 'session-2')

    const firstPrompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'first' }],
      [],
      'act',
      (event) => events.push(event as Record<string, unknown>),
      async () => ''
    )

    await expect(
      adapter.sendPrompt(
        'session-2',
        [{ type: 'text', text: 'second' }],
        [],
        'act',
        (event) => events.push(event as Record<string, unknown>),
        async () => ''
      )
    ).rejects.toThrow('pi-mono prompt already in flight')

    internals(adapter).handleTurnEnd(makeTurnEndEvent('first response', 2.5))

    await expect(firstPrompt).resolves.toMatchObject({
      text: 'first response',
      sessionId: 'session-1',
      costUsd: 2.5,
      inputTokens: 11,
      outputTokens: 7,
      cacheReadTokens: 3,
      cacheWriteTokens: 2
    })
    expect(events.some((event) => event.type === 'result')).toBe(false)
  })

  it('rejects turn_end errors instead of resolving success', async () => {
    const { adapter, events } = createAdapter()
    seedSessions(adapter, 'session-1')

    const prompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'fail' }],
      [],
      'act',
      (event) => events.push(event as Record<string, unknown>),
      async () => ''
    )

    internals(adapter).handleTurnEnd(makeErrorTurnEndEvent('adapter failed'))

    await expect(prompt).rejects.toThrow('adapter failed')
    expect(events).toContainEqual(
      expect.objectContaining({
        type: 'error',
        message: 'adapter failed',
        adapterSessionId: 'session-1'
      })
    )
  })

  it('does not report success after a required agent-control operation fails', async () => {
    const { adapter, events } = createAdapter()
    seedSessions(adapter, 'session-1')

    const prompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'create a child' }],
      [],
      'act',
      (event) => events.push(event as Record<string, unknown>),
      async () => ''
    )

    internals(adapter).handleToolEnd({
      toolName: 'spawn_agent',
      toolCallId: 'tool-spawn',
      result: {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              ok: false,
              error: {
                code: 'missing_request_context',
                message: 'missing active Omi request context'
              }
            })
          }
        ]
      }
    })
    internals(adapter).handleTurnEnd(
      makeTurnEndEvent('I could not create the child, but I am done.')
    )

    await expect(prompt).rejects.toThrow('Required spawn_agent operation failed')
    expect(events).toContainEqual(
      expect.objectContaining({
        type: 'error',
        message: expect.stringContaining('missing active Omi request context')
      })
    )
  })

  it('allows a successful required-control retry to complete the parent turn', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')

    const prompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'create a child' }],
      [],
      'act',
      () => {},
      async () => ''
    )

    internals(adapter).handleToolEnd({
      toolName: 'spawn_agent',
      toolCallId: 'tool-spawn-1',
      result: {
        content: [
          {
            type: 'text',
            text: JSON.stringify({ ok: false, error: { message: 'temporary failure' } })
          }
        ]
      }
    })
    internals(adapter).handleToolEnd({
      toolName: 'spawn_agent',
      toolCallId: 'tool-spawn-2',
      result: { content: [{ type: 'text', text: JSON.stringify({ ok: true }) }] }
    })
    internals(adapter).handleTurnEnd(makeTurnEndEvent('child created'))

    await expect(prompt).resolves.toMatchObject({ text: 'child created' })
  })

  it('does not let an unrelated control success erase a failed obligation', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')
    const prompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'create both children' }],
      [],
      'act',
      () => {},
      async () => ''
    )

    internals(adapter).handleToolStart({
      toolName: 'spawn_agent',
      toolCallId: 'tool-child-a',
      args: { objective: 'child A' }
    })
    internals(adapter).handleToolEnd({
      toolName: 'spawn_agent',
      toolCallId: 'tool-child-a',
      result: {
        content: [
          { type: 'text', text: JSON.stringify({ ok: false, error: { message: 'failed A' } }) }
        ]
      }
    })
    internals(adapter).handleToolStart({
      toolName: 'spawn_agent',
      toolCallId: 'tool-child-b',
      args: { objective: 'child B' }
    })
    internals(adapter).handleToolEnd({
      toolName: 'spawn_agent',
      toolCallId: 'tool-child-b',
      result: { content: [{ type: 'text', text: JSON.stringify({ ok: true }) }] }
    })
    internals(adapter).handleTurnEnd(makeTurnEndEvent('child B created'))

    await expect(prompt).rejects.toThrow('failed A')
  })

  it('resolves abort before turn_end and drops the late completion', async () => {
    const { adapter, events } = createAdapter()
    seedSessions(adapter, 'session-1')

    const prompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'abort me' }],
      [],
      'act',
      (event) => events.push(event as Record<string, unknown>),
      async () => ''
    )

    adapter.abort('session-1')

    await expect(prompt).resolves.toMatchObject({
      text: '',
      sessionId: 'session-1',
      costUsd: 0,
      inputTokens: 0,
      outputTokens: 0
    })

    internals(adapter).handleTurnEnd(makeTurnEndEvent('late response'))

    expect(events).toEqual([])
    expect(internals(adapter).activePromptGeneration).toBe(0)
  })

  it('drops stray turn_end events when no prompt is in flight', () => {
    const { adapter, events } = createAdapter()

    internals(adapter).eventHandler = (event) => events.push(event as Record<string, unknown>)
    internals(adapter).handleTurnEnd(makeTurnEndEvent('orphaned response'))

    expect(events).toEqual([])
    expect(internals(adapter).pendingRequests.size).toBe(0)
  })
})

describe('PiMonoAdapter subprocess death', () => {
  it('rejects the pending prompt and clears relay context when the subprocess exits', async () => {
    const { adapter } = createAdapter()
    await adapter.start()
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const execution = runtime.executeAttempt(
      makeAttemptContext({ attemptId: 'att_exit' }),
      () => {},
      new AbortController().signal
    )
    expect(JSON.parse(readFileSync(internals(adapter).contextFilePath, 'utf8')).attemptId).toBe(
      'att_exit'
    )

    currentProc!.emit('exit', 7)

    await expect(execution).rejects.toThrow('pi-mono process exited (code 7)')
    expect(existsSync(internals(adapter).contextFilePath)).toBe(false)
  })
})

describe('PiMonoAdapter restart lifecycle', () => {
  it('restarts the subprocess and notifies observers after a system-prompt change', async () => {
    const onRestart = vi.fn()
    const { adapter } = createAdapter({ onRestart })

    await adapter.start()
    await expect(adapter.setSystemPrompt('new prompt')).resolves.toBe(true)

    expect(onRestart).toHaveBeenCalledWith('systemPrompt')
    expect(spawn).toHaveBeenCalledTimes(2)
    await adapter.stop()
  })
})

describe('PiMonoAdapter spawn shape (behavioral, Windows)', () => {
  it('spawns Electron-as-Node with the pi cli.js as argv[0] and the rpc flags', async () => {
    const adapter = new PiMonoAdapter(
      { authToken: 'test-token' },
      { piPath: '/fake/pi.js', extensionPath: '/fake/ext.ts', nodeBin: '/fake/node' }
    )
    await adapter.start()

    expect(spawn).toHaveBeenCalledOnce()
    const [cmd, args, options] = vi.mocked(spawn).mock.calls[0] as [
      string,
      string[],
      { env: Record<string, string>; shell?: boolean; windowsHide?: boolean }
    ]
    // Windows deviation from macOS: spawn nodeBin, not the cli directly.
    expect(cmd).toBe('/fake/node')
    expect(args[0]).toBe('/fake/pi.js')
    expect(args).toEqual(
      expect.arrayContaining([
        '--mode',
        'rpc',
        '-e',
        '/fake/ext.ts',
        '--provider',
        'omi',
        '--model',
        'omi-sonnet'
      ])
    )
    expect(args).not.toContain('--no-extensions')
    expect(options.shell).toBe(false)
    expect(options.windowsHide).toBe(true)

    await adapter.stop()
  })

  it('runs the child as plain Node and scrubs credentials in the env', async () => {
    const adapter = new PiMonoAdapter(
      { authToken: 'firebase-id-token-xyz', omiApiBaseUrl: 'https://api.example/v2' },
      { piPath: '/fake/pi.js', extensionPath: '/fake/ext.ts', nodeBin: '/fake/node' }
    )
    await adapter.start()

    const [, , options] = vi.mocked(spawn).mock.calls[0] as [
      string,
      string[],
      { env: Record<string, string> }
    ]
    expect(options.env.ELECTRON_RUN_AS_NODE).toBe('1')
    // Raw token, NOT "Bearer <token>" (pi prepends the scheme itself).
    expect(options.env.OMI_API_KEY).toBe('firebase-id-token-xyz')
    expect(options.env.OMI_API_BASE_URL).toBe('https://api.example/v2')
    expect(options.env.OMI_ADAPTER_ID).toBe('pi-mono')
    expect(options.env.OMI_EXECUTION_ROLE).toBe('coordinator')
    // Upstream provider secret must never reach the extension.
    expect(options.env.ANTHROPIC_API_KEY).toBeUndefined()

    await adapter.stop()
  })

  it('refuses to start without an auth token', async () => {
    const adapter = new PiMonoAdapter(
      {},
      { piPath: '/fake/pi.js', extensionPath: '/fake/ext.ts', nodeBin: '/fake/node' }
    )
    await expect(adapter.start()).rejects.toThrow('requires config.authToken')
    expect(spawn).not.toHaveBeenCalled()
  })
})

describe('PiMonoAdapter image channel (no bytes leak into text)', () => {
  // Security property: screenshot pixels ride pi's separate cmd.images RPC and
  // are NEVER concatenated into the text `message`. This mirrors the throw-gate
  // in agentKernel/desktopContextPacket.ts (assertNoScreenshotBytes) which
  // rejects any text snippet that looks like base64 image bytes.
  const BASE64_BYTES_RE = /^[A-Za-z0-9+/]{400,}={0,2}$/
  const DATA_URL_RE = /^data:image\//i

  it('routes image bytes to cmd.images and keeps the text message clean', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')

    let captured: Record<string, unknown> | undefined
    internals(adapter).sendCommand = (cmd) => {
      captured = cmd
    }

    const imageBytes = 'A'.repeat(600) // >400 chars — trips the throw-gate pattern
    const prompt = adapter.sendPrompt(
      'session-1',
      [
        { type: 'text', text: 'what is on my screen?' },
        { type: 'image', data: imageBytes, mimeType: 'image/jpeg' }
      ],
      [],
      'act',
      () => {},
      async () => ''
    )

    expect(captured).toBeDefined()
    expect(captured!.type).toBe('prompt')
    // The text channel contains ONLY the text block.
    expect(captured!.message).toBe('what is on my screen?')
    expect(String(captured!.message)).not.toContain(imageBytes)
    // The image rides the separate images RPC field.
    expect(captured!.images).toEqual([{ type: 'image', data: imageBytes, mimeType: 'image/jpeg' }])
    // The text message would survive the desktopContextPacket throw-gate.
    expect(DATA_URL_RE.test(String(captured!.message))).toBe(false)
    expect(BASE64_BYTES_RE.test(String(captured!.message))).toBe(false)

    internals(adapter).handleTurnEnd(makeTurnEndEvent('ok'))
    await prompt
  })

  it('omits cmd.images entirely for a text-only prompt', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')

    let captured: Record<string, unknown> | undefined
    internals(adapter).sendCommand = (cmd) => {
      captured = cmd
    }

    const prompt = adapter.sendPrompt(
      'session-1',
      [{ type: 'text', text: 'plain text' }],
      [],
      'act',
      () => {},
      async () => ''
    )

    expect(captured!.message).toBe('plain text')
    expect('images' in captured!).toBe(false)

    internals(adapter).handleTurnEnd(makeTurnEndEvent('ok'))
    await prompt
  })
})

describe('PiMonoRuntimeAdapter sink event forwarding', () => {
  it('forwards canonical stream events but drops tool_use and error from the narrow sink', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const sinkEvents: AdapterStreamEvent[] = []
    const execution = runtime.executeAttempt(
      makeAttemptContext(),
      (event) => sinkEvents.push(event),
      new AbortController().signal
    )

    // text_delta and tool_activity are canonical stream events → forwarded.
    internals(adapter).handleToolStart({
      toolName: 'read',
      toolCallId: 'call-1',
      args: { path: '/tmp/x' }
    })
    // toolcall_end emits a `tool_use` harness event → must NOT reach the sink.
    ;(
      adapter as unknown as { handleMessageUpdate: (e: Record<string, unknown>) => void }
    ).handleMessageUpdate({
      type: 'message_update',
      assistantMessageEvent: {
        type: 'toolcall_end',
        toolCall: { id: 'call-1', name: 'read', arguments: { path: '/tmp/x' } }
      }
    })
    ;(
      adapter as unknown as { handleMessageUpdate: (e: Record<string, unknown>) => void }
    ).handleMessageUpdate({
      type: 'message_update',
      assistantMessageEvent: { type: 'text_delta', delta: 'hello' }
    })

    internals(adapter).handleTurnEnd(makeTurnEndEvent('done'))
    await expect(execution).resolves.toMatchObject({ terminalStatus: 'succeeded' })

    const types = sinkEvents.map((e) => e.type)
    expect(types).toContain('tool_activity')
    expect(types).toContain('text_delta')
    expect(types).not.toContain('tool_use')
    expect(types).not.toContain('error')
  })

  it('rejects executeAttempt on a turn_end error without surfacing an error event to the sink', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const sinkEvents: AdapterStreamEvent[] = []
    const execution = runtime.executeAttempt(
      makeAttemptContext(),
      (event) => sinkEvents.push(event),
      new AbortController().signal
    )

    internals(adapter).handleTurnEnd(makeErrorTurnEndEvent('boom'))

    await expect(execution).rejects.toThrow('boom')
    expect(sinkEvents.map((e) => e.type)).not.toContain('error')
  })
})

describe('PiMonoRuntimeAdapter binding + capabilities', () => {
  it('opens a binding whose native session id differs from the Omi session id', async () => {
    const { adapter } = createAdapter()
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const binding = await runtime.openBinding({ sessionId: 'omi-ses', cwd: '/work' })

    expect(binding.adapterId).toBe('pi-mono')
    expect(binding.sessionId).toBe('omi-ses')
    expect(binding.adapterNativeSessionId).not.toBe('omi-ses')
    expect(binding.adapterNativeSessionId).toBeTruthy()
    expect(binding.resumeFidelity).toBe('none')
    await adapter.stop()
  })

  it('exposes managed-cloud, worker-pinned, non-resumable capabilities', () => {
    const { adapter } = createAdapter()
    const runtime = new PiMonoRuntimeAdapter(adapter)

    expect(runtime.adapterId).toBe('pi-mono')
    expect(runtime.capabilities).toMatchObject({
      resumeFidelity: 'none',
      supportsNativeResume: false,
      supportsCancellation: true,
      acknowledgesCancellation: false,
      requiresPinnedWorker: true,
      supportsModelSwitching: true,
      supportsArtifactEmission: false,
      supportsTools: true,
      restartBehavior: 'process_local_bindings_stale'
    })
  })

  it('acknowledges cancellation dispatch and marks the attempt cancelled', async () => {
    const { adapter } = createAdapter()
    seedSessions(adapter, 'session-1')
    const runtime = new PiMonoRuntimeAdapter(adapter)

    const result = await runtime.cancelAttempt({
      sessionId: 'ses',
      attemptId: 'att-1',
      binding: makeAttemptContext().binding
    })
    expect(result).toMatchObject({
      accepted: true,
      dispatchAttempted: true,
      adapterAcknowledged: false
    })
  })

  it('does not advertise native session resume as a feature', () => {
    const { adapter } = createAdapter()
    expect(adapter.supportsFeature(HarnessFeature.SESSION_RESUME)).toBe(false)
    expect(adapter.supportsFeature(HarnessFeature.BIDIRECTIONAL_RPC)).toBe(true)
    expect(adapter.supportsFeature(HarnessFeature.COST_TRACKING)).toBe(true)
  })
})
