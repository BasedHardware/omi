// INV-AGENT-* Windows control-plane guards.
//
// These mirror the macOS agent runtime's guard tests
// (desktop/macos/agent/tests/{runtime-adapter,run-attempt-lifecycle,control-tools}.test.ts)
// for the invariants that actually port to the trimmed Windows stack. The Windows
// port has NO kernel, NO SQLite session store, and NO owner-scoped control tools
// (bindings live in memory for the life of a task — see interface.ts header), so
// the macOS `adapter-binding` / `sqlite-store` / most `control-tools` guards have
// no Windows analog and are deliberately not reproduced here.
//
// Each `describe` names the specific "MUST NOT" from
// docs/product/invariants/agent-control-plane.md that it guards, so the linkage
// stays greppable:
//   (a) Conflate Omi ids with adapter-native session ids.
//   (b) Authorize control operations from a tool-supplied owner alone.
//   (c) Allow >1 non-terminal attempt with execution authority per run.
// Semantic (d) — request-scoped state keyed by bare requestId under concurrent
// clients — is already covered by acp.test.ts ("ignores session/update
// notifications from other sessions"); the Windows JSON-RPC id map is keyed by a
// host-generated monotonic counter, never a client-supplied id, so it is not
// re-guarded here.

import { spawn, execFile } from 'child_process'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AcpRuntimeAdapter } from './acp'
import {
  adapterCapabilitiesFor,
  assertAdapterAttemptResultContract,
  assertAdapterBindingContract,
  type AdapterAttemptContext,
  type AdapterStreamEvent,
  type ProductionAdapterId,
  type RuntimeAdapter
} from './interface'
import {
  answerCommonHandshake,
  createMockProcess,
  notify,
  respond,
  scriptJsonRpc,
  type JsonRpcMessage,
  type MockAcpProcess
} from './acp.testkit'
import { cancelTask, runCodingAgentTask } from './taskRunner'
import { ADAPTER_PROFILES, adapterConfiguredCommand, adapterIsActivated } from './adapterRegistry'
import type { CodingAgentEvent } from '../../shared/types'

vi.mock('child_process', async () => {
  const actual = await vi.importActual<typeof import('child_process')>('child_process')
  return { ...actual, spawn: vi.fn(), execFile: vi.fn() }
})

// Guard (c) drives the real taskRunner but swaps in fake adapters per test, the
// same way taskRunner.test.ts does. Guards (a)/(b) construct AcpRuntimeAdapter
// directly and never touch this module, so the mock is inert for them.
vi.mock('./adapterRegistry', async () => {
  const actual = await vi.importActual<typeof import('./adapterRegistry')>('./adapterRegistry')
  return {
    ...actual,
    ADAPTER_PROFILES: Object.fromEntries(
      Object.entries(actual.ADAPTER_PROFILES).map(([id, profile]) => [id, { ...profile }])
    ),
    adapterIsActivated: vi.fn(),
    adapterConfiguredCommand: vi.fn(() => undefined)
  }
})

// ── INV-AGENT (a): identity is never conflated ───────────────────────────────
// The macOS runtime enforces this in the AdapterRegistry acquire path
// (runtime-adapter.test.ts "rejects fake adapters that conflate…"). Windows has
// no registry doing that check, and acp.ts does not self-assert the contract, so
// this is the one place the PRODUCTION adapter's real openBinding/executeAttempt
// output is run through the identity-contract assertions.
describe('INV-AGENT (a): Omi ids are never conflated with adapter-native ids', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('the real ACP openBinding + executeAttempt outputs satisfy the identity contract', async () => {
    const proc = createMockProcess()
    vi.mocked(spawn).mockReset()
    vi.mocked(spawn).mockReturnValue(proc as never)

    scriptJsonRpc(proc, (message) => {
      if (answerCommonHandshake(proc, message)) return
      if (message.method === 'session/prompt' && message.id !== undefined) {
        notify(proc, 'session/update', {
          sessionId: 'native-session-1',
          update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: 'ok' } }
        })
        respond(proc, message.id, { stopReason: 'end_turn' })
      }
    })

    const adapter = new AcpRuntimeAdapter({ acpEntry: 'stub-entry.mjs' })

    const binding = await adapter.openBinding({ sessionId: 'omi-session', cwd: 'C:/work' })
    // openBinding half: a real, non-empty native id distinct from the Omi id.
    expect(() => assertAdapterBindingContract(binding, 'openBinding')).not.toThrow()
    expect(binding.adapterNativeSessionId).not.toBe(binding.sessionId)

    const context: AdapterAttemptContext = {
      sessionId: 'omi-session',
      runId: 'run-1',
      attemptId: 'attempt-1',
      binding,
      prompt: [{ type: 'text', text: 'hi' }],
      mode: 'act'
    }
    const events: AdapterStreamEvent[] = []
    const result = await adapter.executeAttempt(
      context,
      (event) => events.push(event),
      new AbortController().signal
    )

    // executeAttempt half: the result's native id matches the binding's native
    // id and is never the Omi correlation id.
    expect(() => assertAdapterAttemptResultContract(context, result, 'executeAttempt')).not.toThrow()
    expect(result.adapterSessionId).toBe(binding.adapterNativeSessionId)
    expect(result.adapterSessionId).not.toBe(context.sessionId)

    await adapter.stop()
  })
})

// ── INV-AGENT (b): control authority is host-owned, not tool-supplied ─────────
// The macOS control-tools guard rejects a tool-supplied ownerId that disagrees
// with the active owner. Windows exposes no owner-scoped control tools, but it
// DOES make one trust decision in response to an adapter-originated request:
// which permission policy resolves a session/request_permission. That decision
// is keyed on the host-owned `this.adapterId`, never on the request payload.
// Here the SAME spoofed request (claiming adapterId/ownerId "acp") is replayed
// to a trusted adapter and to an external one; only host identity decides.
describe('INV-AGENT (b): permission trust is decided by host identity, not the request', () => {
  beforeEach(() => {
    vi.mocked(spawn).mockReset()
    vi.mocked(execFile).mockReset()
    // stop() teardown must settle on any platform: fail taskkill so the
    // proc.kill() fallback (which emits 'exit' on the mock) runs, and make the
    // POSIX process-group kill throw so it can never signal a real group.
    vi.mocked(execFile).mockImplementation(((...args: unknown[]) => {
      const callback = args.find((arg) => typeof arg === 'function') as
        | ((error: Error | null) => void)
        | undefined
      callback?.(new Error('taskkill unavailable in tests'))
      return undefined as never
    }) as never)
    vi.spyOn(process, 'kill').mockImplementation(() => {
      throw new Error('ESRCH')
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // A permission request that offers ONLY a permanent grant AND lies about its
  // identity. A trusted adapter auto-selects; an external one must refuse.
  const spoofedPermissionRequest = {
    jsonrpc: '2.0',
    id: 42,
    method: 'session/request_permission',
    params: {
      adapterId: 'acp',
      ownerId: 'trusted-owner',
      options: [{ kind: 'allow_always', optionId: 'always' }]
    }
  }

  async function replayPermissionRequest(adapter: AcpRuntimeAdapter, proc: MockAcpProcess) {
    const seen = scriptJsonRpc(proc, () => {})
    await adapter.start()
    proc.stdout.write(`${JSON.stringify(spoofedPermissionRequest)}\n`)
    // Let readline deliver the request and the reply flush back onto stdin.
    for (let i = 0; i < 50 && !seen.find((m) => m.id === 42); i++) {
      await new Promise((resolve) => setImmediate(resolve))
    }
    return seen.find((m) => m.id === 42) as JsonRpcMessage | undefined
  }

  it('a first-party (acp) request is auto-approved by host trust', async () => {
    const proc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(proc as never)
    const adapter = new AcpRuntimeAdapter({ acpEntry: 'stub-entry.mjs' })

    const reply = await replayPermissionRequest(adapter, proc)

    expect(reply?.result).toEqual({ outcome: { outcome: 'selected', optionId: 'always' } })
    expect(reply?.error).toBeUndefined()
    await adapter.stop()
  })

  it('an external (hermes) request cannot escalate via a spoofed acp identity', async () => {
    const proc = createMockProcess()
    vi.mocked(spawn).mockReturnValue(proc as never)
    const adapter = new AcpRuntimeAdapter({ adapterId: 'hermes', command: 'hermes acp' })

    const reply = await replayPermissionRequest(adapter, proc)

    // The request-supplied adapterId "acp"/ownerId is ignored; the external
    // policy refuses a permanent-only grant with ACP error -32001.
    expect(reply?.error?.code).toBe(-32001)
    expect(reply?.result).toBeUndefined()
    await adapter.stop()
  })
})

// ── INV-AGENT (c): at most one non-terminal execution-authority attempt ───────
// macOS enforces this in the kernel ("does not allow another non-terminal
// attempt for the same run"). The Windows analog is the sequential fallback loop
// in runCodingAgentTask: authority is granted to one adapter at a time and only
// advances after the current attempt reaches a terminal state. Existing
// taskRunner.test.ts covers the "already produced output → no retry" case; this
// guards the concurrency edge — while an attempt is live, no second adapter is
// ever granted authority (parallelizing the fallback would violate the rule).
describe('INV-AGENT (c): one execution-authority attempt at a time per run', () => {
  beforeEach(() => {
    vi.mocked(adapterIsActivated).mockReset()
    vi.mocked(adapterConfiguredCommand).mockReturnValue(undefined)
  })

  it('never grants a second adapter authority while the first attempt is non-terminal', async () => {
    const created: ProductionAdapterId[] = []
    let reachedExecute!: () => void
    const reachedExecutePromise = new Promise<void>((resolve) => {
      reachedExecute = resolve
    })

    const hangingAdapter = (adapterId: ProductionAdapterId): RuntimeAdapter => ({
      adapterId,
      capabilities: adapterCapabilitiesFor(adapterId),
      start: async () => {},
      stop: async () => {},
      openBinding: async (input) => ({
        sessionId: input.sessionId,
        adapterId,
        adapterNativeSessionId: `${adapterId}-native`,
        resumeFidelity: 'none',
        cwd: input.cwd
      }),
      resumeBinding: async () => {
        throw new Error('not used')
      },
      // Signal that authority was granted, then hang until aborted — the run
      // stays non-terminal for the whole assertion window.
      executeAttempt: async (_context, _sink, signal) => {
        reachedExecute()
        await new Promise<void>((resolve) => {
          if (signal.aborted) return resolve()
          signal.addEventListener('abort', () => resolve(), { once: true })
        })
        throw new Error('aborted')
      },
      cancelAttempt: async () => ({
        accepted: true,
        dispatchAttempted: true,
        adapterAcknowledged: false
      })
    })

    ADAPTER_PROFILES.acp.createAdapter = () => {
      created.push('acp')
      return hangingAdapter('acp')
    }
    ADAPTER_PROFILES.openclaw.createAdapter = () => {
      created.push('openclaw')
      return hangingAdapter('openclaw')
    }
    // Two candidates are connected, so a fallback target exists — yet it must
    // not be built while the first attempt is still running.
    vi.mocked(adapterIsActivated).mockImplementation(((id: ProductionAdapterId) =>
      id === 'acp' || id === 'openclaw') as never)

    const events: CodingAgentEvent[] = []
    const run = runCodingAgentTask({ taskId: 'inv-c', prompt: 'x', agentId: 'acp' }, (event) =>
      events.push(event)
    )
    await reachedExecutePromise

    expect(events.filter((event) => event.type === 'agent_selected')).toHaveLength(1)
    expect(created).toEqual(['acp'])

    expect(cancelTask('inv-c')).toBe(true)
    const result = await run
    expect(result.ok).toBe(false)
    expect(result.error).toBe('Cancelled.')
  })
})
