// The pi-mono product/control tool relay — security + protocol tests.
//
// Same discipline as controlMcpBridge.test.ts: every test drives the REAL bridge
// over its REAL line-delimited socket (a same-process client connection — piped,
// not a spawned subprocess), and asserts through the wire, never by calling a
// private method. A guard that isn't reachable this way is not a guard.
//
// The load-bearing ones: identity is host-authoritative (a `tool_use` frame that
// claims a different sessionId/ownerId cannot change the resolved authority); the
// leaf-role guard holds for the fanout tools; an unsupported product tool degrades
// cleanly AND fires fallback telemetry; and the per-socket pending map handles
// timeout, duplicate callId, and disconnect without clobbering another client.
//
// Driver: node:sqlite via the store's databaseFactory seam (better-sqlite3 is built
// for Electron's ABI and cannot load under plain-node Vitest).

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { createConnection, type Socket } from 'node:net'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentRuntimeKernel } from './kernel'
import { AdapterRegistry } from './adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import {
  AgentToolRelayBridge,
  executeHostTool,
  type ProductToolExecutor,
  type ToolRelayBridgeOptions
} from './toolRelayBridge'
import { LEAF_AGENT_CONTROL_TOOLS } from './executionPolicy'
import {
  createCaptureScreenExecutor,
  screenshotSharingDeniedMessage
} from './captureScreenExecutor'
import type { AgentExecutionRole } from './types'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const OWNER = 'owner-relay-1'

const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const openBridges: AgentToolRelayBridge[] = []
const openClients: RelayClient[] = []

afterEach(async () => {
  for (const client of openClients.splice(0)) client.destroy()
  for (const bridge of openBridges.splice(0)) await bridge.close()
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

function newKernel(): { kernel: AgentRuntimeKernel; store: SqliteAgentStore } {
  const dir = mkdtempSync(join(tmpdir(), 'omi-tool-relay-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() })
  return { kernel, store }
}

function insertSession(store: SqliteAgentStore, role: AgentExecutionRole): string {
  return store.insertSession({
    ownerId: OWNER,
    surfaceKind: 'main_chat',
    defaultAdapterId: 'acp',
    executionRole: role
  }).sessionId
}

/** A persisted session with a chosen role, registered for a relay token. */
function bindSession(
  bridge: AgentToolRelayBridge,
  store: SqliteAgentStore,
  role: AgentExecutionRole
): { sessionId: string; token: string; pipePath: string } {
  const sessionId = insertSession(store, role)
  const { pipePath, token } = bridge.register(sessionId, 'pi-mono')
  return { sessionId, token, pipePath }
}

type HostFrame = Record<string, unknown>

/** A minimal, deliberately-dumb client for the relay protocol: hello handshake,
 *  then `tool_use` frames correlated by callId. It will send whatever raw frame a
 *  test hands it, so malformed / host-authoritative tests can misbehave. */
class RelayClient {
  private readonly socket: Socket
  private buffer = ''
  private counter = 0
  private readonly inbox: HostFrame[] = []
  private readonly waiters: Array<{
    pred: (f: HostFrame) => boolean
    resolve: (f: HostFrame) => void
  }> = []
  private helloResolve: (() => void) | null = null
  private helloReject: ((error: Error) => void) | null = null
  closed = false

  constructor(pipePath: string) {
    this.socket = createConnection(pipePath)
    this.socket.setEncoding('utf8')
    this.socket.on('data', (chunk: string) => this.onData(chunk))
    this.socket.on('close', () => {
      this.closed = true
      this.helloReject?.(new Error('closed before hello'))
    })
    this.socket.on('error', () => {
      /* close handler does the rejecting */
    })
    openClients.push(this)
  }

  private onData(chunk: string): void {
    this.buffer += chunk
    let nl = this.buffer.indexOf('\n')
    while (nl >= 0) {
      const line = this.buffer.slice(0, nl)
      this.buffer = this.buffer.slice(nl + 1)
      if (line.trim()) {
        const frame = JSON.parse(line) as HostFrame
        if (frame.type === 'hello_ok') {
          this.helloResolve?.()
          this.helloResolve = null
          this.helloReject = null
        } else if (frame.type === 'tool_result') {
          const idx = this.waiters.findIndex((w) => w.pred(frame))
          if (idx >= 0) {
            const [w] = this.waiters.splice(idx, 1)
            w.resolve(frame)
          } else {
            this.inbox.push(frame)
          }
        }
      }
      nl = this.buffer.indexOf('\n')
    }
  }

  hello(token: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.helloResolve = resolve
      this.helloReject = reject
      this.socket.write(`${JSON.stringify({ type: 'hello', token })}\n`)
    })
  }

  private awaitResult(pred: (f: HostFrame) => boolean): Promise<HostFrame> {
    const idx = this.inbox.findIndex(pred)
    if (idx >= 0) return Promise.resolve(this.inbox.splice(idx, 1)[0])
    return new Promise((resolve) => this.waiters.push({ pred, resolve }))
  }

  /** Send a tool_use and resolve with the raw `result` string of its tool_result. */
  async call(
    name: string,
    input: Record<string, unknown> = {},
    extra: Record<string, unknown> = {}
  ): Promise<string> {
    const callId = `t-${++this.counter}`
    this.socket.write(`${JSON.stringify({ type: 'tool_use', callId, name, input, ...extra })}\n`)
    const frame = await this.awaitResult((f) => f.callId === callId)
    return String(frame.result)
  }

  /** Write a fully-explicit frame (used for duplicate-callId and malformed tests). */
  writeFrame(frame: HostFrame): void {
    this.socket.write(`${JSON.stringify(frame)}\n`)
  }

  writeRaw(line: string): void {
    this.socket.write(`${line}\n`)
  }

  resultForCallId(callId: string): Promise<HostFrame> {
    return this.awaitResult((f) => f.callId === callId)
  }

  waitForClose(): Promise<void> {
    if (this.closed) return Promise.resolve()
    return new Promise((resolve) => this.socket.on('close', () => resolve()))
  }

  destroy(): void {
    this.socket.destroy()
  }
}

async function startBridge(
  kernel: AgentRuntimeKernel,
  options: Partial<ToolRelayBridgeOptions> = {}
): Promise<AgentToolRelayBridge> {
  const bridge = new AgentToolRelayBridge({ kernel, ...options })
  openBridges.push(bridge)
  await bridge.start()
  return bridge
}

async function connect(pipePath: string, token: string): Promise<RelayClient> {
  const client = new RelayClient(pipePath)
  await client.hello(token)
  return client
}

const deferred = <T>(): { promise: Promise<T>; resolve: (v: T) => void } => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

// === handshake ================================================================

describe('the token handshake gates the connection', () => {
  it('a valid token authenticates and a control tool round-trips', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const envelope = JSON.parse(await client.call('list_agent_sessions', {}))
    expect(envelope.ok).toBe(true)
    expect(Array.isArray(envelope.sessions)).toBe(true)
  })

  it('a bad token is rejected and the connection dropped', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { pipePath } = bindSession(bridge, store, 'coordinator')

    const client = new RelayClient(pipePath)
    openClients.push(client)
    await expect(client.hello('not-a-real-token')).rejects.toThrow()
    expect(client.closed).toBe(true)
  })
})

// === per-binding eviction =====================================================

describe('closeBinding evicts a binding so the maps stay bounded', () => {
  it('re-minting after closeBinding yields a fresh token, and the old one is dead', async () => {
    const { kernel } = newKernel()
    const bridge = await startBridge(kernel)

    const first = bridge.register('sess-1', 'pi-mono')
    // register is idempotent while the binding is live.
    expect(bridge.register('sess-1', 'pi-mono').token).toBe(first.token)

    bridge.closeBinding('sess-1', 'pi-mono')

    // After eviction a re-register mints a NEW token (proof the entry was removed).
    const second = bridge.register('sess-1', 'pi-mono')
    expect(second.token).not.toBe(first.token)

    // The evicted token no longer authenticates.
    const client = new RelayClient(first.pipePath)
    openClients.push(client)
    await expect(client.hello(first.token)).rejects.toThrow()
  })

  it('is a no-op for an unknown binding', async () => {
    const { kernel } = newKernel()
    const bridge = await startBridge(kernel)
    expect(() => bridge.closeBinding('nope', 'pi-mono')).not.toThrow()
  })
})

// === control-tool dispatch with host-derived context ==========================

describe('control tools dispatch through handleAgentControlToolCall', () => {
  it('list_agent_sessions returns the host-bound owner’s sessions', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    // A session owned by OWNER — it must be visible to the host-bound owner.
    store.insertSession({ ownerId: OWNER, surfaceKind: 'main_chat', defaultAdapterId: 'acp' })
    const client = await connect(pipePath, token)

    const envelope = JSON.parse(await client.call('list_agent_sessions', {}))
    expect(envelope.ok).toBe(true)
    expect((envelope.sessions as unknown[]).length).toBeGreaterThan(0)
  })

  it('a throw inside dispatch becomes an "Error:" result, never a socket crash', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    // A control tool with structurally-invalid input still comes back as a result
    // envelope (ok:false), and the connection stays alive for the next call.
    const first = JSON.parse(await client.call('get_agent_run', { runId: 12345 }))
    expect(first.ok).toBe(false)
    const second = JSON.parse(await client.call('list_agent_sessions', {}))
    expect(second.ok).toBe(true)
  })
})

// === the leaf-role guard holds through the relay ==============================

describe('a leaf caller is blocked from every fanout control tool', () => {
  const validInput: Record<string, Record<string, unknown>> = {
    send_agent_message: { sessionId: 'ses_1', prompt: 'keep going' },
    spawn_background_agent: { prompt: 'do the thing' },
    spawn_agent: { objective: 'research this' },
    run_agent_and_wait: { objective: 'compute this', parentRunId: 'run_1' }
  }

  for (const tool of [...LEAF_AGENT_CONTROL_TOOLS]) {
    it(`rejects ${tool}`, async () => {
      const { kernel, store } = newKernel()
      const bridge = await startBridge(kernel)
      const { token, pipePath } = bindSession(bridge, store, 'leaf')
      const client = await connect(pipePath, token)

      const envelope = JSON.parse(await client.call(tool, validInput[tool]))
      expect(envelope.ok).toBe(false)
      // The leaf guard throws inside handleAgentControlToolCall; the MESSAGE proves
      // the rejection is the role guard, not schema validation or a kernel miss.
      // (MUTATION: no-op assertLeafControlToolsAllowed and these turn ok:true.)
      expect(envelope.error?.message).toMatch(
        tool === 'send_agent_message'
          ? /Leaf workers cannot continue agent sessions\./
          : /Background agents are leaf workers and cannot start additional agents\./
      )
    })
  }
})

// === identity is host-authoritative, never off the wire =======================

describe('identity comes from the token binding, not the frame', () => {
  it('a wire ownerId that differs from the bound owner is rejected', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const envelope = JSON.parse(
      await client.call('list_agent_sessions', { ownerId: 'someone-else' })
    )
    expect(envelope.ok).toBe(false)
    expect(envelope.error?.message).toMatch(/does not match the active control owner/)
  })

  it('a wire sessionId cannot elevate a leaf caller to a coordinator session', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    // The connection is bound to a LEAF session…
    const { token, pipePath } = bindSession(bridge, store, 'leaf')
    // …and there is a separate coordinator session the frame will try to claim.
    const coordinatorSessionId = insertSession(store, 'coordinator')
    const client = await connect(pipePath, token)

    // Frame-level sessionId/ownerId are correlation fields the relay must ignore.
    const envelope = JSON.parse(
      await client.call(
        'spawn_agent',
        { objective: 'research this' },
        { sessionId: coordinatorSessionId, ownerId: OWNER, runId: 'run_forged' }
      )
    )
    // Still blocked as a leaf — the wire sessionId did NOT change resolved authority.
    expect(envelope.ok).toBe(false)
    expect(envelope.error?.message).toMatch(
      /Background agents are leaf workers and cannot start additional agents\./
    )
  })

  it('a serviceable product executor is invoked with the host-bound sessionId', async () => {
    const { kernel, store } = newKernel()
    let seenSessionId = ''
    const executor: ProductToolExecutor = async (_input, ctx) => {
      seenSessionId = ctx.sessionId
      return 'ok'
    }
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([['execute_sql', executor]])
    })
    const { token, pipePath, sessionId } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call(
      'execute_sql',
      { query: 'SELECT 1' },
      { sessionId: 'ses-forged', ownerId: 'someone-else' }
    )
    expect(result).toBe('ok')
    expect(seenSessionId).toBe(sessionId)
    expect(seenSessionId).not.toBe('ses-forged')
  })
})

// === serviceable vs unsupported product tools =================================

describe('product-tool dispatch', () => {
  it('a serviceable product tool round-trips its result string', async () => {
    const { kernel, store } = newKernel()
    const executor: ProductToolExecutor = async (input) =>
      `rows: ${String((input as { query?: string }).query)}`
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([['execute_sql', executor]])
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    expect(await client.call('execute_sql', { query: 'X' })).toBe('rows: X')
  })

  it('an unsupported product tool degrades cleanly AND fires fallback telemetry', async () => {
    const { kernel, store } = newKernel()
    const recordFallback = vi.fn()
    // Empty serviceable set — execute_sql is a real product tool but not wired here
    // (an explicit empty map, since the production default registry now services it).
    const bridge = await startBridge(kernel, { recordFallback, productExecutors: new Map() })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    expect(await client.call('execute_sql', { query: 'X' })).toBe(
      'Error: execute_sql is not available on Windows yet'
    )
    expect(recordFallback).toHaveBeenCalledTimes(1)
    expect(recordFallback).toHaveBeenCalledWith(
      expect.objectContaining({
        component: 'tool_relay',
        outcome: 'exhausted',
        reason: 'unsupported_tool',
        tool: 'execute_sql'
      })
    )
  })
})

// === capture_screen: the Screen-Sharing-in-Chat gate at the relay layer =======

describe('capture_screen dispatches through its consent gate', () => {
  it('gate ON → the executor captures and the file path round-trips', async () => {
    const { kernel, store } = newKernel()
    const capture = vi.fn(
      async () => 'C:\\Users\\me\\AppData\\Roaming\\omi\\chat-screenshots\\shot.jpg'
    )
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([
        ['capture_screen', createCaptureScreenExecutor({ isSharingEnabled: () => true, capture })]
      ])
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    expect(await client.call('capture_screen', {})).toBe(
      'C:\\Users\\me\\AppData\\Roaming\\omi\\chat-screenshots\\shot.jpg'
    )
    expect(capture).toHaveBeenCalledTimes(1)
  })

  it('gate OFF → dispatch is refused with POLICY_DENIED and NO capture happens', async () => {
    const { kernel, store } = newKernel()
    const capture = vi.fn(async () => 'should-not-run.jpg')
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([
        ['capture_screen', createCaptureScreenExecutor({ isSharingEnabled: () => false, capture })]
      ])
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call('capture_screen', {})
    expect(result).toBe(screenshotSharingDeniedMessage())
    expect(result).toContain('POLICY_DENIED:')
    expect(JSON.parse(result.slice('POLICY_DENIED: '.length))).toMatchObject({
      ok: false,
      code: 'disabled_by_user_setting',
      capability: 'desktop.context.screenshot_image',
      tool: 'capture_screen'
    })
    // The gate is enforced at dispatch: the executor never ran the capture.
    expect(capture).not.toHaveBeenCalled()
  })
})

// === the pending map: timeout, duplicate, disconnect ==========================

describe('the per-socket pending map', () => {
  it('resolves a hung normal-class call with a timeout error string', async () => {
    const { kernel, store } = newKernel()
    const hang: ProductToolExecutor = () => new Promise<string>(() => {})
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([['execute_sql', hang]]),
      timeouts: { normalMs: 40, longMs: 5000 }
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call('execute_sql', { query: 'X' })
    expect(result).toMatch(/tool 'execute_sql' timed out after 40ms/)
    expect(bridge.pendingCallCount()).toBe(0)
  })

  it('selects the long timeout class from the manifest', async () => {
    const { kernel, store } = newKernel()
    const hang: ProductToolExecutor = () => new Promise<string>(() => {})
    // scan_files has timeoutClass 'long'; normalMs is huge so only longMs can fire.
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([['scan_files', hang]]),
      timeouts: { normalMs: 5000, longMs: 40 }
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    expect(await client.call('scan_files', {})).toMatch(/timed out after 40ms/)
  })

  it('rejects a duplicate callId without clobbering the live call', async () => {
    const { kernel, store } = newKernel()
    const gate = deferred<string>()
    const executor: ProductToolExecutor = () => gate.promise
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([['execute_sql', executor]]),
      timeouts: { normalMs: 5000, longMs: 5000 }
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    // First tool_use hangs on the gate; the duplicate is rejected immediately.
    client.writeFrame({ type: 'tool_use', callId: 'dup-1', name: 'execute_sql', input: {} })
    client.writeFrame({ type: 'tool_use', callId: 'dup-1', name: 'execute_sql', input: {} })

    const duplicate = await client.resultForCallId('dup-1')
    expect(String(duplicate.result)).toBe('Error: duplicate callId dup-1')

    // The original is still live and resolves normally once the gate opens.
    gate.resolve('done')
    const original = await client.resultForCallId('dup-1')
    expect(String(original.result)).toBe('done')
    expect(bridge.pendingCallCount()).toBe(0)
  })

  it('a socket disconnect rejects only that socket’s pending calls', async () => {
    const { kernel, store } = newKernel()
    const gates: Record<string, ReturnType<typeof deferred<string>>> = {
      A: deferred<string>(),
      B: deferred<string>()
    }
    const executor: ProductToolExecutor = (input) =>
      gates[String((input as { id?: string }).id)].promise
    const bridge = await startBridge(kernel, {
      productExecutors: new Map([['execute_sql', executor]]),
      timeouts: { normalMs: 5000, longMs: 5000 }
    })
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')

    const clientA = await connect(pipePath, token)
    const clientB = await connect(pipePath, token)
    clientA.writeFrame({ type: 'tool_use', callId: 'a-1', name: 'execute_sql', input: { id: 'A' } })
    clientB.writeFrame({ type: 'tool_use', callId: 'b-1', name: 'execute_sql', input: { id: 'B' } })

    // Wait until both are registered as pending.
    await vi.waitFor(() => expect(bridge.pendingCallCount()).toBe(2))

    // Drop A. Only A's pending entry is reaped; B's survives.
    clientA.destroy()
    await vi.waitFor(() => expect(bridge.pendingCallCount()).toBe(1))

    // B still completes normally when its executor resolves.
    gates.B.resolve('done-B')
    const bResult = await clientB.resultForCallId('b-1')
    expect(String(bResult.result)).toBe('done-B')

    // A's executor resolving after disconnect is a harmless no-op (no crash).
    gates.A.resolve('done-A')
    await vi.waitFor(() => expect(bridge.pendingCallCount()).toBe(0))
  })
})

// === hostile input ============================================================

describe('hostile input is handled without crashing the bridge', () => {
  it('a malformed (non-JSON) line drops the connection but the bridge keeps serving', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')

    const bad = await connect(pipePath, token)
    bad.writeRaw('this is not json at all')
    await bad.waitForClose()
    expect(bad.closed).toBe(true)

    // The bridge is still alive: a fresh connection still round-trips.
    const good = await connect(pipePath, token)
    const envelope = JSON.parse(await good.call('list_agent_sessions', {}))
    expect(envelope.ok).toBe(true)
  })
})

// === executeHostTool: the in-process dispatcher (voice-kernel reuse) ===========
//
// The shared, socket-free entry the hub dispatcher will reuse (macOS parity: one
// executor code path for voice + chat). It must enforce the IDENTICAL host-side
// posture as the relay — control tools through handleAgentControlToolCall with
// role/owner resolved fresh from the session, product tools through the registry,
// and errors returned as strings, never thrown.

describe('executeHostTool (in-process dispatch)', () => {
  it('dispatches a control tool in-process with host-derived authority', async () => {
    const { kernel, store } = newKernel()
    const sessionId = insertSession(store, 'coordinator')

    const result = JSON.parse(
      await executeHostTool('list_agent_sessions', {}, { kernel, sessionId, adapterId: 'pi-mono' })
    )
    expect(result.ok).toBe(true)
    expect(Array.isArray(result.sessions)).toBe(true)
  })

  it('holds the leaf-role guard (spawn_agent refused for a leaf session)', async () => {
    const { kernel, store } = newKernel()
    const sessionId = insertSession(store, 'leaf')

    const result = JSON.parse(
      await executeHostTool(
        'spawn_agent',
        { objective: 'research this' },
        { kernel, sessionId, adapterId: 'pi-mono' }
      )
    )
    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(
      /Background agents are leaf workers and cannot start additional agents\./
    )
  })

  it('ignores an input-supplied ownerId — authority is the session owner', async () => {
    const { kernel, store } = newKernel()
    const sessionId = insertSession(store, 'coordinator')

    const result = JSON.parse(
      await executeHostTool(
        'list_agent_sessions',
        { ownerId: 'someone-else' },
        { kernel, sessionId, adapterId: 'pi-mono' }
      )
    )
    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(/does not match the active control owner/)
  })

  it('invokes a product executor with the caller-supplied host session id', async () => {
    const { kernel, store } = newKernel()
    const sessionId = insertSession(store, 'coordinator')
    let seenSessionId = ''
    const executor: ProductToolExecutor = async (input, ctx) => {
      seenSessionId = ctx.sessionId
      return `rows: ${String((input as { query?: string }).query)}`
    }

    const result = await executeHostTool(
      'execute_sql',
      { query: 'X' },
      {
        kernel,
        sessionId,
        adapterId: 'pi-mono',
        productExecutors: new Map([['execute_sql', executor]])
      }
    )
    expect(result).toBe('rows: X')
    expect(seenSessionId).toBe(sessionId)
  })

  it('degrades cleanly for an unserviceable product tool (empty registry)', async () => {
    const { kernel, store } = newKernel()
    const sessionId = insertSession(store, 'coordinator')

    const result = await executeHostTool(
      'execute_sql',
      { query: 'X' },
      { kernel, sessionId, adapterId: 'pi-mono', productExecutors: new Map() }
    )
    expect(result).toBe('Error: execute_sql is not available on Windows yet')
  })

  it('returns a throwing executor as an "Error:" string (never throws)', async () => {
    const { kernel, store } = newKernel()
    const sessionId = insertSession(store, 'coordinator')
    const boom: ProductToolExecutor = async () => {
      throw new Error('executor exploded')
    }

    const result = await executeHostTool(
      'execute_sql',
      {},
      {
        kernel,
        sessionId,
        adapterId: 'pi-mono',
        productExecutors: new Map([['execute_sql', boom]])
      }
    )
    expect(result).toBe('Error: executor exploded')
  })
})
