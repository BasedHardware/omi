// AgentRuntimeKernel behavioral tests — the run/attempt/binding state machine
// driven end to end against a real SQLite store and a fake RuntimeAdapter.
//
// Driver: injects node:sqlite's DatabaseSync via the store's `databaseFactory`
// seam, exactly as store.test.ts does. better-sqlite3 is rebuilt for Electron's
// ABI and cannot load under plain-node Vitest; both drivers satisfy the store's
// structural KernelDatabase interface, so this exercises the production path.
//
// Hermetic: no network, no sleeps, no ordering dependence between tests.
//
// SCOPE: the run / attempt / binding / delegation state machine and its guards.
// The coordinator surface — the context-packet security gates, the action-queue
// projection, and the intent-router decision order — lives in
// desktopCoordinator.test.ts. Do not read this file alone and conclude the
// context-packet gate is untested.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from './kernel'
import { AdapterRegistry } from './adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import type {
  AdapterAttemptContext,
  AdapterAttemptResult,
  AdapterBindingHandle,
  AdapterCapabilities,
  AdapterEventSink,
  CancelAttemptContext,
  CancelDispatchResult,
  OpenBindingInput,
  ResumeBindingInput,
  RuntimeAdapter
} from '../codingAgent/interface'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const OWNER = 'owner-1'

afterEach(() => {
  // Reset so native session ids are per-test deterministic (native-1, native-2, …)
  // rather than depending on how many tests ran before.
  nativeSessionCounter = 0
  // Windows holds the SQLite file open until the handle is closed; rmSync would
  // otherwise fail with EPERM.
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

// === Fake adapter ============================================================

interface FakeAdapterOptions {
  adapterId?: string
  supportsNativeResume?: boolean
  requiresPinnedWorker?: boolean
  /** Resolve executeAttempt with this text (default: echo the prompt). */
  reply?: string
  /** Throw from executeAttempt instead of resolving. */
  executeError?: Error
  /** Throw from resumeBinding (drives the stale-binding path). */
  resumeError?: Error
  /** Called with the assembled prompt on every attempt. */
  onPrompt?: (prompt: string) => void
  /** Block executeAttempt until the returned resolver is called. */
  gate?: { promise: Promise<void> }
}

interface FakeAdapter extends RuntimeAdapter {
  readonly calls: {
    openBinding: OpenBindingInput[]
    resumeBinding: ResumeBindingInput[]
    executeAttempt: AdapterAttemptContext[]
    cancelAttempt: CancelAttemptContext[]
  }
}

function capabilitiesFor(options: FakeAdapterOptions): AdapterCapabilities {
  const supportsNativeResume = options.supportsNativeResume ?? true
  return {
    resumeFidelity: supportsNativeResume ? 'native' : 'none',
    supportsNativeResume,
    supportsCancellation: true,
    acknowledgesCancellation: true,
    requiresPinnedWorker: options.requiresPinnedWorker ?? false,
    supportsModelSwitching: true,
    supportsArtifactEmission: false,
    supportsTools: true,
    restartBehavior: supportsNativeResume
      ? 'native_bindings_survive'
      : 'process_local_bindings_stale'
  }
}

let nativeSessionCounter = 0

function fakeAdapter(options: FakeAdapterOptions = {}): FakeAdapter {
  const adapterId = options.adapterId ?? 'test-adapter'
  const calls: FakeAdapter['calls'] = {
    openBinding: [],
    resumeBinding: [],
    executeAttempt: [],
    cancelAttempt: []
  }
  let aborted = false

  return {
    adapterId,
    capabilities: capabilitiesFor(options),
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
        adapterId,
        // INV-AGENT: never echo the Omi sessionId back as the native id.
        adapterNativeSessionId: `native-${nativeSessionCounter}`,
        resumeFidelity: capabilitiesFor(options).resumeFidelity,
        cwd: input.cwd,
        model: input.model
      }
    },
    async resumeBinding(input: ResumeBindingInput): Promise<AdapterBindingHandle> {
      calls.resumeBinding.push(input)
      if (options.resumeError) throw options.resumeError
      return {
        sessionId: input.sessionId,
        adapterId,
        adapterNativeSessionId: input.adapterNativeSessionId,
        resumeFidelity: capabilitiesFor(options).resumeFidelity,
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
      const promptText = context.prompt
        .map((block) => (block.type === 'text' ? block.text : ''))
        .join('')
      options.onPrompt?.(promptText)
      sink({ type: 'text_delta', text: 'streaming' })

      if (options.gate) {
        signal.addEventListener('abort', () => {
          aborted = true
        })
        await options.gate.promise
        if (aborted || signal.aborted) {
          throw new Error('aborted')
        }
      }
      if (options.executeError) throw options.executeError

      return {
        text: options.reply ?? `echo: ${promptText}`,
        adapterSessionId: context.binding.adapterNativeSessionId,
        terminalStatus: 'succeeded',
        inputTokens: 10,
        outputTokens: 20,
        costUsd: 0.01
      }
    },
    async cancelAttempt(context: CancelAttemptContext): Promise<CancelDispatchResult> {
      calls.cancelAttempt.push(context)
      return {
        accepted: true,
        dispatchAttempted: true,
        adapterAcknowledged: true
      }
    }
  }
}

// === Harness =================================================================

/** A fresh temp dir; reopen the same dir to simulate a process restart. */
function newStoreDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'omi-kernel-'))
  createdDirs.push(dir)
  return dir
}

/**
 * Open (or REOPEN) the store at a given dir. Reopening runs reconcileStartup —
 * that is what makes a restart test a real restart rather than a fresh kernel
 * over a live store object.
 */
function openStoreAt(dir: string): SqliteAgentStore {
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  return store
}

function newStore(): SqliteAgentStore {
  return openStoreAt(newStoreDir())
}

function newKernel(
  adapter: FakeAdapter,
  store: SqliteAgentStore = newStore()
): { kernel: AgentRuntimeKernel; store: SqliteAgentStore; adapter: FakeAdapter } {
  const registry = new AdapterRegistry()
  registry.register(adapter.adapterId, () => adapter, 2)
  const kernel = new AgentRuntimeKernel({ store, registry, runtimeNodeId: 'node-a' })
  return { kernel, store, adapter }
}

function runInput(overrides: Record<string, unknown> = {}) {
  return {
    ownerId: OWNER,
    surfaceKind: 'main_chat',
    externalRefKind: 'chat',
    externalRefId: 'default',
    defaultAdapterId: 'test-adapter',
    adapterId: 'test-adapter',
    clientId: 'client-1',
    requestId: 'request-1',
    prompt: 'hello there',
    ...overrides
  } as Parameters<AgentRuntimeKernel['executeRun']>[0]
}

// === Tests ===================================================================

describe('AgentRuntimeKernel — executeRun', () => {
  it('runs a turn end to end and persists the terminal state', async () => {
    const { kernel, store } = newKernel(fakeAdapter())

    const result = await kernel.executeRun(runInput())

    expect(result.terminalStatus).toBe('succeeded')
    expect(result.text).toContain('echo:')
    expect(result.run.status).toBe('succeeded')
    expect(result.attempt.status).toBe('succeeded')
    expect(result.run.inputTokens).toBe(10)
    expect(result.run.costUsd).toBeCloseTo(0.01)

    // The adapter's native session id is recorded, and is never the Omi id.
    const binding = store.getRow('SELECT * FROM adapter_bindings WHERE session_id = ?', [
      result.session.sessionId
    ])
    expect(binding.adapter_native_session_id).toMatch(/^native-/)
    expect(binding.adapter_native_session_id).not.toBe(result.session.sessionId)
    expect(result.adapterSessionId).not.toBe(result.session.sessionId)
  })

  it('records both turns of the conversation on the kernel transcript (INV-CHAT-1)', async () => {
    const { kernel, store } = newKernel(fakeAdapter({ reply: 'the answer' }))

    await kernel.executeRun(runInput({ prompt: 'the question' }))

    const turns = store.allRows(
      'SELECT role, content FROM conversation_turns ORDER BY created_at_ms ASC, rowid ASC'
    )
    expect(turns.map((turn) => turn.role)).toEqual(['user', 'assistant'])
    expect(turns[0].content).toBe('the question')
    expect(turns[1].content).toBe('the answer')
  })

  it('emits a subscriber event stream for the run lifecycle', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const types: string[] = []
    kernel.subscribe((event) => types.push(event.type))

    await kernel.executeRun(runInput())

    expect(types).toContain('run.queued')
    expect(types).toContain('binding.created')
    expect(types).toContain('attempt.started')
    expect(types).toContain('run.running')
    expect(types).toContain('message.delta')
    expect(types).toContain('message.completed')
    expect(types).toContain('run.succeeded')
  })

  it('fails the run and records the failure when the adapter throws', async () => {
    const adapter = fakeAdapter({ executeError: new Error('adapter exploded') })
    const { kernel } = newKernel(adapter)

    const result = await kernel.executeRun(runInput({ maxAttempts: 1 }))

    expect(result.terminalStatus).toBe('failed')
    expect(result.run.status).toBe('failed')
    expect(result.run.errorCode).toBe('adapter_execution_failed')
    expect(result.run.errorMessage).toBeTruthy()
    expect(adapter.calls.executeAttempt).toHaveLength(1)
  })

  it('fails the run when the adapter is not registered', async () => {
    const { kernel } = newKernel(fakeAdapter())

    const result = await kernel.executeRun(
      runInput({ adapterId: 'test-adapter', defaultAdapterId: 'test-adapter' })
    )
    expect(result.terminalStatus).toBe('succeeded')

    // A second session pinned to an adapter with no registered pool.
    // (requestId must differ — the store enforces UNIQUE(client_id, request_id)
    // as its run-idempotency key.)
    const unregistered = await kernel.executeRun(
      runInput({
        requestId: 'request-2',
        externalRefId: 'other',
        adapterId: 'ghost-adapter',
        defaultAdapterId: 'ghost-adapter'
      })
    )
    expect(unregistered.terminalStatus).toBe('failed')
    expect(unregistered.run.errorCode).toBe('adapter_not_registered')
  })

  it('cancels an in-flight run and dispatches the cancellation to the adapter', async () => {
    let release!: () => void
    const gate = {
      promise: new Promise<void>((resolve) => {
        release = resolve
      })
    }
    const adapter = fakeAdapter({ gate })
    const { kernel } = newKernel(adapter)

    const running = kernel.executeRun(runInput({ maxAttempts: 1 }))
    // Wait for the attempt to actually reach the adapter before cancelling.
    await waitFor(() => adapter.calls.executeAttempt.length === 1)

    const runId = adapter.calls.executeAttempt[0].runId
    const cancelled = await kernel.cancelRun(runId, { ownerId: OWNER })

    expect(cancelled.accepted).toBe(true)
    expect(cancelled.dispatchAttempted).toBe(true)
    expect(cancelled.adapterAcknowledged).toBe(true)
    // The kernel supplies host identity on cancel; ownerId is authoritative.
    expect(adapter.calls.cancelAttempt[0].ownerId).toBe(OWNER)

    release()
    const result = await running
    expect(result.terminalStatus).toBe('cancelled')
    expect(result.run.status).toBe('cancelled')
  })

  it('refuses to cancel an already-terminal run', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const result = await kernel.executeRun(runInput())

    const cancelled = await kernel.cancelRun(result.run.runId, { ownerId: OWNER })

    expect(cancelled.accepted).toBe(false)
    expect(cancelled.dispatchAttempted).toBe(false)
  })

  it('rejects a run whose session belongs to another owner', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const first = await kernel.executeRun(runInput())

    await expect(
      kernel.executeRun(runInput({ sessionId: first.session.sessionId, ownerId: 'intruder' }))
    ).rejects.toThrow(/does not belong to owner/)
  })
})

describe('AgentRuntimeKernel — bindings', () => {
  it('resumes the existing binding on a second turn rather than opening a new one', async () => {
    const adapter = fakeAdapter({ supportsNativeResume: true })
    const { kernel } = newKernel(adapter)

    const first = await kernel.executeRun(runInput({ requestId: 'r1' }))
    const second = await kernel.executeRun(runInput({ requestId: 'r2' }))

    expect(first.session.sessionId).toBe(second.session.sessionId)
    expect(adapter.calls.openBinding).toHaveLength(1)
    expect(adapter.calls.resumeBinding).toHaveLength(1)
    expect(adapter.calls.resumeBinding[0].adapterNativeSessionId).toMatch(/^native-/)
  })

  // NOTE: this is a fresh-kernel test, NOT a restart test. It shares the SAME
  // store object, so reconcileStartup() never runs. It proves the kernel keeps no
  // in-memory binding cache — the binding row alone is enough to resume. The real
  // restart (store closed and reopened, reconcileStartup fired) is the next test;
  // do not let this one stand in for it.
  it('resumes from the binding row alone, with no in-memory carryover', async () => {
    const store = newStore()
    const firstAdapter = fakeAdapter()
    const first = newKernel(firstAdapter, store)
    const seeded = await first.kernel.executeRun(runInput())
    const nativeId = firstAdapter.calls.executeAttempt[0].binding.adapterNativeSessionId

    const secondAdapter = fakeAdapter()
    const second = newKernel(secondAdapter, store)
    const resumed = await second.kernel.executeRun(runInput({ requestId: 'r2' }))

    expect(resumed.session.sessionId).toBe(seeded.session.sessionId)
    expect(secondAdapter.calls.openBinding).toHaveLength(0)
    expect(secondAdapter.calls.resumeBinding).toHaveLength(1)
    expect(secondAdapter.calls.resumeBinding[0].adapterNativeSessionId).toBe(nativeId)
    expect(resumed.terminalStatus).toBe('succeeded')
  })

  it('resumes a natively-resumable binding across a real process restart', async () => {
    // First process: run a turn, then CLOSE the store.
    const dir = newStoreDir()
    const firstAdapter = fakeAdapter({ supportsNativeResume: true })
    const firstStore = openStoreAt(dir)
    const seeded = await newKernel(firstAdapter, firstStore).kernel.executeRun(runInput())
    const nativeId = firstAdapter.calls.executeAttempt[0].binding.adapterNativeSessionId
    firstStore.close()

    // Second process: reopen the SAME file. reconcileStartup() runs on open and
    // NULLs adapter_instance_id on every binding — a native binding must still
    // resume, because its native session id outlives the process.
    const secondStore = openStoreAt(dir)
    const secondAdapter = fakeAdapter({ supportsNativeResume: true })
    const resumed = await newKernel(secondAdapter, secondStore).kernel.executeRun(
      runInput({ requestId: 'r2' })
    )

    expect(resumed.session.sessionId).toBe(seeded.session.sessionId)
    expect(secondAdapter.calls.resumeBinding).toHaveLength(1)
    expect(secondAdapter.calls.resumeBinding[0].adapterNativeSessionId).toBe(nativeId)
    expect(secondAdapter.calls.openBinding).toHaveLength(0)
    expect(resumed.terminalStatus).toBe('succeeded')
  })

  it('never reuses a process-local binding across a real process restart', async () => {
    // The dangerous case: a pinned-worker adapter whose session lives only inside
    // the dead process. Its handle is worthless after a restart, and reusing it
    // would hand the model a dead worker. reconcileStartup marks every
    // resume_fidelity='none' binding stale precisely to stop that; without it,
    // canUseProcessLocalBinding (which keys on adapterInstanceId === runtimeNodeId)
    // would happily reuse the row.
    const dir = newStoreDir()
    const firstAdapter = fakeAdapter({ supportsNativeResume: false, requiresPinnedWorker: true })
    const firstStore = openStoreAt(dir)
    await newKernel(firstAdapter, firstStore).kernel.executeRun(runInput())

    const beforeRestart = firstStore.getRow(
      'SELECT status, resume_fidelity, adapter_instance_id FROM adapter_bindings'
    )
    expect(String(beforeRestart.status)).toBe('active')
    expect(String(beforeRestart.resume_fidelity)).toBe('none')
    expect(String(beforeRestart.adapter_instance_id)).toBe('node-a')
    firstStore.close()

    // Restart: reopening the file runs reconcileStartup.
    const secondStore = openStoreAt(dir)
    const staleAfterRestart = secondStore.getRow(
      "SELECT status, adapter_instance_id FROM adapter_bindings WHERE resume_fidelity = 'none'"
    )
    expect(String(staleAfterRestart.status)).toBe('stale')
    expect(staleAfterRestart.adapter_instance_id).toBeNull()

    const secondAdapter = fakeAdapter({ supportsNativeResume: false, requiresPinnedWorker: true })
    const result = await newKernel(secondAdapter, secondStore).kernel.executeRun(
      runInput({ requestId: 'r2' })
    )

    // A brand new binding, never the dead process-local one.
    expect(secondAdapter.calls.resumeBinding).toHaveLength(0)
    expect(secondAdapter.calls.openBinding).toHaveLength(1)
    expect(result.terminalStatus).toBe('succeeded')
    expect(
      Number(
        secondStore.getRow('SELECT COUNT(*) AS c FROM adapter_bindings WHERE status = ?', [
          'active'
        ]).c
      )
    ).toBe(1)
  })

  it('marks the binding stale and opens a fresh one when resume fails', async () => {
    const store = newStore()
    await newKernel(fakeAdapter(), store).kernel.executeRun(runInput())

    const resumeFails = fakeAdapter({ resumeError: new Error('native session gone') })
    const { kernel } = newKernel(resumeFails, store)
    const result = await kernel.executeRun(runInput({ requestId: 'r2', maxAttempts: 2 }))

    expect(resumeFails.calls.resumeBinding).toHaveLength(1)
    // Attempt 1 fails stale; attempt 2 opens a new binding and succeeds.
    expect(resumeFails.calls.openBinding).toHaveLength(1)
    expect(result.terminalStatus).toBe('succeeded')

    const staleCount = store.getRow(
      "SELECT COUNT(*) AS count FROM adapter_bindings WHERE status = 'stale'"
    )
    expect(Number(staleCount.count)).toBe(1)
  })

  it('opens a new binding instead of resuming when the cwd changed', async () => {
    const store = newStore()
    const adapter = fakeAdapter()
    const { kernel } = newKernel(adapter, store)

    await kernel.executeRun(runInput({ cwd: '/work/a' }))
    await kernel.executeRun(runInput({ requestId: 'r2', cwd: '/work/b' }))

    expect(adapter.calls.openBinding).toHaveLength(2)
    expect(adapter.calls.resumeBinding).toHaveLength(0)
  })

  it('invalidates the active bindings of an owner', async () => {
    const adapter = fakeAdapter()
    const { kernel, store } = newKernel(adapter)
    await kernel.executeRun(runInput())

    const invalidated = kernel.invalidateBindings({ ownerId: OWNER, surfaceKind: 'main_chat' })
    expect(invalidated.invalidatedBindingIds).toHaveLength(1)

    // Assert the STATE CHANGE, not the returned array — that array is built by
    // the SELECT that runs before the UPDATE, so it would still be populated if
    // the UPDATE were deleted.
    const binding = store.getRow('SELECT status FROM adapter_bindings WHERE binding_id = ?', [
      invalidated.invalidatedBindingIds[0]
    ])
    expect(String(binding.status)).toBe('invalid')

    // And the next run must open a fresh binding rather than resume the dead one.
    await kernel.executeRun(runInput({ requestId: 'r2' }))
    expect(adapter.calls.openBinding).toHaveLength(2)
    expect(adapter.calls.resumeBinding).toHaveLength(0)
  })
})

describe('AgentRuntimeKernel — single-active-run enforcement (INV-AGENT)', () => {
  // STORE-LEVEL guard, exercised while the kernel holds a live attempt: this
  // calls store.insertAttempt directly, so it proves the DB authority index — not
  // a kernel code path. The kernel-level equivalent is the binding-lock test
  // below (two concurrent runs on one session). Duplicates store.test.ts's index
  // coverage on purpose, under a live run.
  it('store authority index refuses a second active attempt while a run is in flight', async () => {
    let release!: () => void
    const gate = {
      promise: new Promise<void>((resolve) => {
        release = resolve
      })
    }
    const adapter = fakeAdapter({ gate })
    const { kernel, store } = newKernel(adapter)

    const running = kernel.executeRun(runInput({ maxAttempts: 1 }))
    await waitFor(() => adapter.calls.executeAttempt.length === 1)
    const runId = adapter.calls.executeAttempt[0].runId

    // The store's partial-unique authority index is what backs this: a run may
    // only ever hold one active attempt.
    expect(() =>
      store.insertAttempt({
        runId,
        attemptNo: 99,
        status: 'running',
        adapterId: 'test-adapter',
        adapterInstanceId: 'node-a',
        runtimeNodeId: 'node-a',
        retryable: 0
      })
    ).toThrow()

    release()
    await running
  })

  it('serializes two concurrent runs on one session behind the binding lock', async () => {
    const adapter = fakeAdapter()
    const { kernel } = newKernel(adapter)

    const [a, b] = await Promise.all([
      kernel.executeRun(runInput({ requestId: 'r1' })),
      kernel.executeRun(runInput({ requestId: 'r2' }))
    ])

    expect(a.session.sessionId).toBe(b.session.sessionId)
    expect(a.terminalStatus).toBe('succeeded')
    expect(b.terminalStatus).toBe('succeeded')
    // Exactly one binding was opened for the session despite the race.
    expect(adapter.calls.openBinding).toHaveLength(1)
  })
})

describe('AgentRuntimeKernel — sendAgentMessage', () => {
  it('continues an existing session by id', async () => {
    const adapter = fakeAdapter()
    const { kernel } = newKernel(adapter)
    const first = await kernel.executeRun(runInput())

    const followUp = await kernel.sendAgentMessage({
      sessionId: first.session.sessionId,
      ownerId: OWNER,
      clientId: 'client-1',
      requestId: 'request-2',
      prompt: 'follow up'
    })

    expect(followUp.session.sessionId).toBe(first.session.sessionId)
    expect(followUp.terminalStatus).toBe('succeeded')
    expect(adapter.calls.executeAttempt).toHaveLength(2)
    expect(adapter.calls.openBinding).toHaveLength(1)
  })
})

describe('AgentRuntimeKernel — leaf-role guards (INV-AGENT)', () => {
  it('lets a trusted user spawn a background agent', async () => {
    const { kernel } = newKernel(fakeAdapter())

    const spawned = await kernel.spawnBackgroundAgent({
      ownerId: OWNER,
      clientId: 'client-1',
      requestId: 'request-bg',
      prompt: 'do the thing',
      adapterId: 'test-adapter',
      defaultAdapterId: 'test-adapter',
      trustedUserSpawn: true
    })

    expect(spawned.session.executionRole).toBe('leaf')
    expect(spawned.run.status).toBe('queued')
  })

  it('refuses an agent-originated spawn with no caller session', async () => {
    const { kernel } = newKernel(fakeAdapter())

    await expect(
      kernel.spawnBackgroundAgent({
        ownerId: OWNER,
        clientId: 'client-1',
        requestId: 'request-bg',
        prompt: 'do the thing',
        adapterId: 'test-adapter',
        defaultAdapterId: 'test-adapter'
      })
    ).rejects.toThrow(/requires a coordinator caller session/)
  })

  it('refuses a leaf worker spawning another background agent', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const leaf = await kernel.spawnBackgroundAgent({
      ownerId: OWNER,
      clientId: 'client-1',
      requestId: 'request-bg',
      prompt: 'parent work',
      adapterId: 'test-adapter',
      defaultAdapterId: 'test-adapter',
      trustedUserSpawn: true
    })

    await expect(
      kernel.spawnBackgroundAgent({
        ownerId: OWNER,
        clientId: 'client-1',
        requestId: 'request-bg-2',
        prompt: 'child work',
        adapterId: 'test-adapter',
        defaultAdapterId: 'test-adapter',
        callerSessionId: leaf.session.sessionId
      })
    ).rejects.toThrow(/Leaf workers cannot create background agents/)
  })
})

describe('AgentRuntimeKernel — surface sessions and transcript', () => {
  it('resolves one canonical session per surface and reuses it', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const surfaceRef = {
      surfaceKind: 'main_chat',
      externalRefKind: 'chat',
      externalRefId: 'default'
    }

    const first = kernel.resolveSurfaceSession({ ownerId: OWNER, surfaceRef })
    const again = kernel.resolveSurfaceSession({ ownerId: OWNER, surfaceRef })

    expect(again.agentSessionId).toBe(first.agentSessionId)
    expect(again.conversationId).toBe(first.conversationId)

    const run = await kernel.executeRun(runInput())
    expect(run.session.sessionId).toBe(first.agentSessionId)
  })

  it('records a surface turn and returns it in the main-chat tail', () => {
    const { kernel } = newKernel(fakeAdapter())

    kernel.recordSurfaceTurn({
      ownerId: OWNER,
      surfaceRef: {
        surfaceKind: 'main_chat',
        externalRefKind: 'chat',
        externalRefId: 'default'
      },
      userText: 'ping',
      assistantText: 'pong',
      origin: 'typed'
    })

    const tail = kernel.getMainChatTurnTail(OWNER)
    expect(tail.turns.map((turn) => turn.content)).toEqual(['ping', 'pong'])
  })

  it('clears owner state and invalidates its bindings', async () => {
    const { kernel, store } = newKernel(fakeAdapter())
    await kernel.executeRun(runInput())

    const cleared = kernel.clearOwnerState(OWNER)
    expect(cleared.invalidatedBindingIds.length).toBeGreaterThan(0)

    // Assert the state change, not the returned array (which the pre-UPDATE
    // SELECT populates). No binding of this owner may remain usable.
    expect(
      Number(
        store.getRow('SELECT COUNT(*) AS c FROM adapter_bindings WHERE status = ?', ['active']).c
      )
    ).toBe(0)
  })
})

describe('AgentRuntimeKernel — startup reconciliation', () => {
  // STORE-LEVEL: calls store.reconcileStartup() directly against rows the kernel
  // wrote. The kernel-level consequences of a restart (bindings resumed vs. never
  // reused) are the two "real process restart" tests above.
  it('store reconcileStartup orphans a run and attempt left in flight by a crash', async () => {
    let release!: () => void
    const gate = {
      promise: new Promise<void>((resolve) => {
        release = resolve
      })
    }
    const adapter = fakeAdapter({ gate })
    const store = newStore()
    const { kernel } = newKernel(adapter, store)

    const running = kernel.executeRun(runInput({ maxAttempts: 1 }))
    await waitFor(() => adapter.calls.executeAttempt.length === 1)
    const runId = adapter.calls.executeAttempt[0].runId

    // Simulate the process dying mid-attempt: the row stays 'running'.
    const reconciled = store.reconcileStartup()

    expect(reconciled.orphanedRunIds).toContain(runId)
    expect(reconciled.orphanedAttemptIds).toHaveLength(1)
    expect(store.getRow('SELECT status FROM runs WHERE run_id = ?', [runId]).status).toBe(
      'orphaned'
    )

    release()
    await running.catch(() => undefined)
  })
})

describe('AgentRuntimeKernel — turn context assembly', () => {
  it('injects the coordinator route and context packet into a main-chat prompt', async () => {
    const prompts: string[] = []
    const adapter = fakeAdapter({ onPrompt: (prompt) => prompts.push(prompt) })
    const { kernel, store } = newKernel(adapter)

    await kernel.executeRun(runInput({ prompt: 'what should I do next' }))

    expect(prompts).toHaveLength(1)
    const prompt = prompts[0]
    expect(prompt).toContain('[Desktop Coordinator Route Context]')
    expect(prompt).toContain('routeIntent=')
    expect(prompt).toContain('# Context Packet')
    expect(prompt).toContain('# User Message')
    expect(prompt).toContain('what should I do next')

    // The context packet is really persisted (the stub-free path), with its
    // redacted preview, and the packet id in the prompt matches the row.
    const packet = store.getRow('SELECT * FROM desktop_context_packets')
    expect(prompt).toContain(String(packet.packet_id))
    expect(String(packet.owner_id)).toBe(OWNER)
  })

  it('suppresses the coordinator route on an explicit agent-control-tool turn', async () => {
    const prompts: string[] = []
    const adapter = fakeAdapter({ onPrompt: (prompt) => prompts.push(prompt) })
    const { kernel } = newKernel(adapter)

    await kernel.executeRun(runInput({ prompt: 'call spawn_background_agent for me' }))

    expect(prompts[0]).not.toContain('[Desktop Coordinator Route Context]')
    expect(prompts[0]).not.toContain('# Context Packet')
  })

  it('gives a leaf worker the no-spawn execution boundary', async () => {
    const prompts: string[] = []
    const adapter = fakeAdapter({ onPrompt: (prompt) => prompts.push(prompt) })
    const { kernel } = newKernel(adapter)

    await kernel.spawnBackgroundAgent({
      ownerId: OWNER,
      clientId: 'client-1',
      requestId: 'request-bg',
      prompt: 'background work',
      surfaceKind: 'background_agent',
      externalRefKind: 'pill',
      externalRefId: 'pill-1',
      adapterId: 'test-adapter',
      defaultAdapterId: 'test-adapter',
      trustedUserSpawn: true
    })
    await waitFor(() => prompts.length === 1)

    expect(prompts[0]).toContain('# Execution Boundary')
    expect(prompts[0]).toContain('background agents cannot create more agents')
  })

  it('carries the prior transcript into the next turn', async () => {
    const prompts: string[] = []
    // A non-resumable adapter has no native history, so the kernel must inject
    // the full transcript tail rather than only the undelivered delta.
    const adapter = fakeAdapter({
      supportsNativeResume: false,
      requiresPinnedWorker: true,
      onPrompt: (prompt) => prompts.push(prompt),
      reply: 'first answer'
    })
    const { kernel } = newKernel(adapter)

    await kernel.executeRun(runInput({ prompt: 'first question' }))
    await kernel.executeRun(runInput({ requestId: 'r2', prompt: 'second question' }))

    expect(prompts).toHaveLength(2)
    expect(prompts[1]).toContain('<conversation_history>')
    expect(prompts[1]).toContain('first question')
    expect(prompts[1]).toContain('first answer')
  })
})

describe('AgentRuntimeKernel — desktop action queue and intent routing', () => {
  it('surfaces a failed run on the action queue', async () => {
    const { kernel } = newKernel(fakeAdapter({ executeError: new Error('boom') }))
    await kernel.executeRun(runInput({ maxAttempts: 1 }))

    const queue = kernel.listDesktopActionQueue({ ownerId: OWNER })

    expect(queue.some((item) => item.kind === 'failed_run')).toBe(true)
  })

  it('routes an ordinary utterance to a new run when nothing matches', () => {
    const { kernel } = newKernel(fakeAdapter())

    const route = kernel.routeDesktopIntent({
      ownerId: OWNER,
      utterance: 'hello',
      surfaceKind: 'main_chat'
    })

    expect(route.intent).toBe('new_run')
  })

  it('routes an ambiguous external send to a dispatch', () => {
    const { kernel } = newKernel(fakeAdapter())

    const route = kernel.routeDesktopIntent({
      ownerId: OWNER,
      utterance: 'email this to the team',
      surfaceKind: 'main_chat'
    })

    expect(route.intent).toBe('dispatch')
  })

  it('resumes a healthy related session', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const seeded = await kernel.executeRun(runInput())

    const route = kernel.routeDesktopIntent({
      ownerId: OWNER,
      utterance: 'and now the next step',
      surfaceKind: 'main_chat'
    })

    expect(route.intent).toBe('resume')
    expect(route.sessionId).toBe(seeded.session.sessionId)
  })

  it('answers a status question from local state', async () => {
    const { kernel } = newKernel(fakeAdapter())
    await kernel.executeRun(runInput({ surfaceKind: 'floating_bar', externalRefId: 'bar' }))

    const route = kernel.routeDesktopIntent({
      ownerId: OWNER,
      utterance: "what's running",
      surfaceKind: 'main_chat'
    })

    expect(route.intent).toBe('quick_answer')
  })

  it('hides a queue item behind an attention override', async () => {
    const { kernel } = newKernel(fakeAdapter({ executeError: new Error('boom') }))
    const failed = await kernel.executeRun(runInput({ maxAttempts: 1 }))

    kernel.setDesktopAttentionOverride({
      ownerId: OWNER,
      subjectKind: 'run',
      subjectId: failed.run.runId,
      // A fixed timestamp: suppression keys on dismissedAtMs being non-null, so
      // there is no reason to make this test depend on the wall clock.
      dismissedAtMs: 1_000_000_000
    })

    const queue = kernel.listDesktopActionQueue({ ownerId: OWNER })
    expect(queue.some((item) => item.subjectId === failed.run.runId)).toBe(false)
  })
})

describe('AgentRuntimeKernel — execution role derived from the surface (INV-AGENT)', () => {
  // REGRESSION: executionRoleForSurface had no production caller. macOS derives
  // the role at its transport boundary; Windows is in-process and has no
  // transport, so the kernel is the funnel. Before the fix, resolveSession
  // defaulted an unset role to 'coordinator', so a run created directly on a LEAF
  // surface became a coordinator session — and, because the role is persisted on
  // the session row, kept coordinator spawn rights forever. That is a leaf escape.

  it.each([
    ['background_agent', undefined],
    ['delegated_agent', undefined],
    ['floating_bar', 'pill']
  ])('derives leaf for surface %s/%s', async (surfaceKind, externalRefKind) => {
    const { kernel } = newKernel(fakeAdapter())

    const result = await kernel.executeRun(
      runInput({
        surfaceKind,
        externalRefKind: externalRefKind ?? 'ref',
        externalRefId: 'x-1'
      })
    )

    expect(result.session.executionRole).toBe('leaf')
  })

  it('derives coordinator for an ordinary chat surface', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const result = await kernel.executeRun(runInput())
    expect(result.session.executionRole).toBe('coordinator')

    const bar = await kernel.executeRun(
      runInput({ requestId: 'r2', surfaceKind: 'floating_bar', externalRefKind: 'chat' })
    )
    expect(bar.session.executionRole).toBe('coordinator')
  })

  it('lets an explicit role from the caller win over the derived one', async () => {
    const { kernel } = newKernel(fakeAdapter())

    // spawnBackgroundAgent/delegateAgent pass 'leaf' explicitly; an explicit role
    // must still be honored rather than re-derived from the surface.
    const result = await kernel.executeRun(
      runInput({ surfaceKind: 'main_chat', executionRole: 'leaf' })
    )

    expect(result.session.executionRole).toBe('leaf')
  })

  it('derives leaf through resolveSurfaceSession too, not just executeRun', async () => {
    // The OTHER door: kernel.resolveSurfaceSession() (and getVoiceSeedContextForSurface)
    // reach store.insertSession via surfaceSession.ts WITHOUT passing through
    // KernelCore.resolveSession. Deriving the role in only one of the two leaves
    // this one escaping.
    const { kernel, store } = newKernel(fakeAdapter())

    const leaf = kernel.resolveSurfaceSession({
      ownerId: OWNER,
      surfaceRef: {
        surfaceKind: 'floating_bar',
        externalRefKind: 'pill',
        externalRefId: 'pill-1'
      }
    })
    expect(
      String(
        store.getRow('SELECT execution_role FROM sessions WHERE session_id = ?', [
          leaf.agentSessionId
        ]).execution_role
      )
    ).toBe('leaf')

    const coordinator = kernel.resolveSurfaceSession({
      ownerId: OWNER,
      surfaceRef: {
        surfaceKind: 'main_chat',
        externalRefKind: 'chat',
        externalRefId: 'default'
      }
    })
    expect(
      String(
        store.getRow('SELECT execution_role FROM sessions WHERE session_id = ?', [
          coordinator.agentSessionId
        ]).execution_role
      )
    ).toBe('coordinator')
  })

  it('closes the escape: a session created on a leaf surface cannot spawn or delegate', async () => {
    const { kernel } = newKernel(fakeAdapter())

    // A plain executeRun on a leaf surface — no spawnBackgroundAgent involved.
    const leaf = await kernel.executeRun(
      runInput({
        surfaceKind: 'background_agent',
        externalRefKind: 'ref',
        externalRefId: 'bg-1'
      })
    )
    expect(leaf.session.executionRole).toBe('leaf')

    // Pre-fix this session was a 'coordinator' and BOTH of these would have been
    // allowed — the leaf worker could fan out indefinitely.
    await expect(
      kernel.spawnBackgroundAgent({
        ownerId: OWNER,
        clientId: 'client-1',
        requestId: 'request-escape',
        prompt: 'spawn a child',
        adapterId: 'test-adapter',
        defaultAdapterId: 'test-adapter',
        callerSessionId: leaf.session.sessionId
      })
    ).rejects.toThrow(/Leaf workers cannot create background agents/)

    await expect(
      kernel.delegateAgent({
        mode: 'call',
        parentRunId: leaf.run.runId,
        objective: 'delegate onward',
        ownerId: OWNER,
        clientId: 'client-1',
        requestId: 'request-escape-2',
        adapterId: 'test-adapter',
        defaultAdapterId: 'test-adapter'
      })
    ).rejects.toThrow(/Leaf workers cannot create delegated agents/)
  })
})

describe('AgentRuntimeKernel — delegateAgent', () => {
  /** Run a coordinator turn and return its run id, to delegate from. */
  async function parentRun(kernel: AgentRuntimeKernel): Promise<string> {
    const parent = await kernel.executeRun(runInput())
    return parent.run.runId
  }

  function delegation(parentRunId: string, overrides: Record<string, unknown> = {}) {
    return {
      mode: 'call' as const,
      parentRunId,
      objective: 'summarize the release notes',
      ownerId: OWNER,
      clientId: 'client-1',
      requestId: 'request-delegate',
      adapterId: 'test-adapter',
      defaultAdapterId: 'test-adapter',
      ...overrides
    } as Parameters<AgentRuntimeKernel['delegateAgent']>[0]
  }

  it('call mode awaits the child and returns its result', async () => {
    const adapter = fakeAdapter({ reply: 'child answer' })
    const { kernel, store } = newKernel(adapter)
    const parentRunId = await parentRun(kernel)

    const result = await kernel.delegateAgent(delegation(parentRunId))

    expect(result.delegation.status).toBe('succeeded')
    expect(result.terminalStatus).toBe('succeeded')
    expect(result.result?.summary).toBe('child answer')
    // The child is a distinct leaf session, not the parent.
    expect(result.childSession.sessionId).not.toBe(
      store.getRow('SELECT session_id FROM runs WHERE run_id = ?', [parentRunId]).session_id
    )
    expect(result.childSession.executionRole).toBe('leaf')
    // The objective reached the child as its prompt.
    const childPrompt = adapter.calls.executeAttempt.at(-1)!.prompt
    expect(JSON.stringify(childPrompt)).toContain('summarize the release notes')
  })

  it('call mode carries the caller-supplied context into the child prompt', async () => {
    const adapter = fakeAdapter()
    const { kernel } = newKernel(adapter)
    const parentRunId = await parentRun(kernel)

    await kernel.delegateAgent(delegation(parentRunId, { context: 'the repo is at v2' }))

    const childPrompt = JSON.stringify(adapter.calls.executeAttempt.at(-1)!.prompt)
    expect(childPrompt).toContain('Objective:')
    expect(childPrompt).toContain('Context:')
    expect(childPrompt).toContain('the repo is at v2')
  })

  it('spawn mode returns immediately with a running delegation', async () => {
    const adapter = fakeAdapter()
    const { kernel, store } = newKernel(adapter)
    const parentRunId = await parentRun(kernel)

    const spawned = await kernel.delegateAgent(delegation(parentRunId, { mode: 'spawn' }))

    // Returns without awaiting the child: status is still running and there is no
    // result payload (call mode would have both).
    expect(spawned.delegation.status).toBe('running')
    expect(spawned.result).toBeUndefined()

    await waitFor(
      () =>
        String(
          store.getRow('SELECT status FROM delegations WHERE delegation_id = ?', [
            spawned.delegation.delegationId
          ]).status
        ) === 'succeeded'
    )
  })

  it('spawn mode records the failure instead of swallowing it', async () => {
    // The fire-and-forget path: nothing awaits the child, so a thrown error must
    // still land on the delegation row or it is lost entirely.
    const adapter = fakeAdapter({ executeError: new Error('child exploded') })
    const { kernel, store } = newKernel(adapter)
    const parentRunId = await parentRun(kernel)

    const spawned = await kernel.delegateAgent(
      delegation(parentRunId, { mode: 'spawn', maxAttempts: 1 })
    )

    await waitFor(
      () =>
        String(
          store.getRow('SELECT status FROM delegations WHERE delegation_id = ?', [
            spawned.delegation.delegationId
          ]).status
        ) === 'failed'
    )

    const childRun = store.getRow('SELECT status, error_code FROM runs WHERE run_id = ?', [
      spawned.childRun.runId
    ])
    expect(String(childRun.status)).toBe('failed')
    expect(String(childRun.error_code)).toBe('adapter_execution_failed')
    // The parent is told, via a delegation.completed event carrying the failure.
    const events = store.allRows(
      "SELECT payload_json FROM events WHERE type = 'delegation.completed'"
    )
    expect(events).toHaveLength(1)
    expect(String(events[0].payload_json)).toContain('failed')
  })

  it('refuses a leaf worker delegating further (INV-AGENT)', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const parentRunId = await parentRun(kernel)

    // Delegate once to obtain a leaf child, then try to delegate FROM the leaf.
    const child = await kernel.delegateAgent(delegation(parentRunId))
    expect(child.childSession.executionRole).toBe('leaf')

    await expect(
      kernel.delegateAgent(delegation(child.childRun.runId, { requestId: 'request-delegate-2' }))
    ).rejects.toThrow(/Leaf workers cannot create delegated agents/)
  })

  it('enforces the delegation depth bound', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const parentRunId = await parentRun(kernel)

    await expect(kernel.delegateAgent(delegation(parentRunId, { maxDepth: 0 }))).rejects.toThrow(
      /maxDepth must be between 1 and 5/
    )
    await expect(kernel.delegateAgent(delegation(parentRunId, { maxDepth: 6 }))).rejects.toThrow(
      /maxDepth must be between 1 and 5/
    )
  })

  it('enforces the delegation budget bound', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const parentRunId = await parentRun(kernel)

    await expect(
      kernel.delegateAgent(delegation(parentRunId, { maxBudgetUsd: 0 }))
    ).rejects.toThrow(/maxBudgetUsd must be greater than 0 and at most 10/)
    await expect(
      kernel.delegateAgent(delegation(parentRunId, { maxBudgetUsd: 11 }))
    ).rejects.toThrow(/maxBudgetUsd must be greater than 0 and at most 10/)
  })

  it('refuses to delegate from another owner’s run', async () => {
    const { kernel } = newKernel(fakeAdapter())
    const parentRunId = await parentRun(kernel)

    await expect(
      kernel.delegateAgent(delegation(parentRunId, { ownerId: 'intruder' }))
    ).rejects.toThrow(/does not belong to owner/)
  })
})

describe('AgentRuntimeKernel — provider boundary enforced through executeRun (INV-AGENT)', () => {
  // executionPolicy.test.ts tests resolveAdapterWithinBoundary in isolation. These
  // prove executeRun actually CALLS it — that a session pinned to one credential
  // scope cannot be rerouted to another, and that no run row survives the attempt.
  it('refuses to reroute a local-credential session to a different local adapter', async () => {
    const { kernel, store } = newKernel(fakeAdapter())
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp' // -> providerBoundary local_user:acp
    })
    expect(session.providerBoundary).toBe('local_user:acp')

    await expect(
      kernel.executeRun(
        runInput({
          sessionId: session.sessionId,
          externalRefKind: undefined,
          externalRefId: undefined,
          adapterId: 'hermes',
          defaultAdapterId: 'acp'
        })
      )
    ).rejects.toThrow(/Local provider mode is pinned to acp/)

    // The run was refused at admission — nothing persisted.
    expect(
      Number(
        store.getRow('SELECT COUNT(*) AS c FROM runs WHERE session_id = ?', [session.sessionId]).c
      )
    ).toBe(0)
  })

  it('refuses to route a managed-cloud session to a local-credential adapter', async () => {
    const { kernel, store } = newKernel(fakeAdapter())
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'pi-mono' // -> providerBoundary managed_cloud
    })
    expect(session.providerBoundary).toBe('managed_cloud')

    // NOTE the error text. PR-D registered pi-mono as a managed_cloud production
    // adapter, so 'pi-mono' IS now in ADAPTER_CAPABILITY_MATRIX and
    // resolveAdapterWithinBoundary takes its production branch: a managed_cloud
    // session refuses local Claude ('acp') with the User-Claude-mode error. The run
    // is still refused (that is what matters here), now via the managed_cloud branch.
    await expect(
      kernel.executeRun(
        runInput({
          sessionId: session.sessionId,
          externalRefKind: undefined,
          externalRefId: undefined,
          adapterId: 'acp',
          defaultAdapterId: 'pi-mono'
        })
      )
    ).rejects.toThrow(/Local Claude is available only when the User Claude mode is selected/)

    expect(
      Number(
        store.getRow('SELECT COUNT(*) AS c FROM runs WHERE session_id = ?', [session.sessionId]).c
      )
    ).toBe(0)
  })
})

/** Poll a synchronous predicate without wall-clock sleeps in the test body. */
async function waitFor(predicate: () => boolean, attempts = 200): Promise<void> {
  for (let i = 0; i < attempts; i += 1) {
    if (predicate()) return
    await new Promise((resolve) => setImmediate(resolve))
  }
  throw new Error('waitFor: predicate never became true')
}
