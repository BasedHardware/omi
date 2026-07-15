// The model-facing control-tool server — security tests.
//
// WHY THESE MATTER. This bridge is the ONLY door that lets a model reach the 18
// agent-control tools. Every guard that was latent while the control plane was
// host-only becomes live here. So each test drives the REAL bridge over its REAL
// line-delimited socket (the same transport the MCP subprocess speaks) and
// asserts through the wire — never by calling a private method. A guard that
// isn't reachable this way is not a guard.
//
// The load-bearing ones: a hidden tool named by the wire is rejected AT DISPATCH
// (not merely hidden from `tools/list`); a leaf caller is rejected for every
// fanout tool with VALID input (so only the role guard can be the reason);
// `resolve_desktop_dispatch` — which mints consent approvals — is unreachable
// because `trustedUserControl` is hard-false host-side; and `ownerId` is bound
// from the session, so a wire-supplied owner cannot widen scope.
//
// Driver: node:sqlite via the store's databaseFactory seam (better-sqlite3 is
// built for Electron's ABI and cannot load under plain-node Vitest). The socket
// is a same-process client connection — piped, not a spawned subprocess — so the
// suite stays hermetic: no network, no real clock, no ordering dependence.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { createConnection, type Socket } from 'node:net'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from './kernel'
import { AdapterRegistry } from './adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import { AgentControlMcpBridge } from './controlMcpBridge'
import { AGENT_CONTROL_TOOL_NAMES, TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES } from './controlTools'
import { LEAF_AGENT_CONTROL_TOOLS } from './executionPolicy'
import type { AgentExecutionRole } from './types'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const OWNER = 'owner-mcp-1'

const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const openBridges: AgentControlMcpBridge[] = []
const openClients: BridgeClient[] = []

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
  const dir = mkdtempSync(join(tmpdir(), 'omi-mcp-bridge-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() })
  return { kernel, store }
}

/** A persisted session with a chosen execution role, plus its bridge token. */
function bindSession(
  bridge: AgentControlMcpBridge,
  store: SqliteAgentStore,
  role: AgentExecutionRole
): { sessionId: string; token: string; pipePath: string } {
  const session = store.insertSession({
    ownerId: OWNER,
    surfaceKind: 'main_chat',
    defaultAdapterId: 'acp',
    executionRole: role
  })
  const { pipePath, token } = bridge.register(session.sessionId, 'acp')
  return { sessionId: session.sessionId, token, pipePath }
}

type HostFrame = Record<string, unknown>
type ToolEnvelope = { ok: boolean; error?: { code: string; message: string }; [k: string]: unknown }

/**
 * A minimal client for the host relay protocol: hello handshake, then
 * callId-correlated list/call frames. It is deliberately dumb — it will send
 * whatever raw line a test hands it, so malformed-input tests can misbehave.
 */
class BridgeClient {
  private readonly socket: Socket
  private buffer = ''
  private counter = 0
  private readonly pending = new Map<string, (frame: HostFrame) => void>()
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
      for (const [, resolve] of this.pending) resolve({ type: 'closed' })
      this.pending.clear()
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
        } else if (typeof frame.callId === 'string' && this.pending.has(frame.callId)) {
          const resolve = this.pending.get(frame.callId)!
          this.pending.delete(frame.callId)
          resolve(frame)
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

  private send(frame: HostFrame): Promise<HostFrame> {
    const callId = `c-${++this.counter}`
    return new Promise((resolve) => {
      this.pending.set(callId, resolve)
      this.socket.write(`${JSON.stringify({ ...frame, callId })}\n`)
    })
  }

  async list(): Promise<string[]> {
    const frame = await this.send({ type: 'list' })
    const tools = (frame.tools ?? []) as Array<{ name: string }>
    return tools.map((t) => t.name)
  }

  /** The parsed tool envelope, or the raw error frame if the host rejected the relay. */
  async call(name: string, input: Record<string, unknown> = {}): Promise<ToolEnvelope> {
    const frame = await this.send({ type: 'call', name, input })
    if (frame.type === 'error') {
      return { ok: false, error: { code: 'relay_error', message: String(frame.message) } }
    }
    return JSON.parse(String(frame.result)) as ToolEnvelope
  }

  /** Send a raw line (possibly malformed) and resolve on the next host frame or close. */
  sendRaw(line: string): Promise<HostFrame> {
    const callId = `raw-${++this.counter}`
    return new Promise((resolve) => {
      this.pending.set(callId, resolve)
      this.socket.write(`${line}\n`)
    })
  }

  waitForClose(): Promise<void> {
    if (this.closed) return Promise.resolve()
    return new Promise((resolve) => this.socket.on('close', () => resolve()))
  }

  destroy(): void {
    this.socket.destroy()
  }
}

async function startBridge(kernel: AgentRuntimeKernel): Promise<AgentControlMcpBridge> {
  const bridge = new AgentControlMcpBridge({ kernel })
  openBridges.push(bridge)
  await bridge.start()
  return bridge
}

async function connect(pipePath: string, token: string): Promise<BridgeClient> {
  const client = new BridgeClient(pipePath)
  await client.hello(token)
  return client
}

// === tools/list visibility ===================================================

describe('tools/list visibility for a model-facing caller', () => {
  it('a model-facing coordinator sees every tool EXCEPT the trusted-only two', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const names = await client.list()

    // 16 of 18: never spawn_background_agent, never resolve_desktop_dispatch.
    for (const trustedOnly of TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES) {
      expect(names).not.toContain(trustedOnly)
    }
    const expected = AGENT_CONTROL_TOOL_NAMES.filter(
      (n) => !TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES.has(n)
    )
    expect(names.sort()).toEqual([...expected].sort())
  })

  it('a leaf caller is shown none of the four fanout tools', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'leaf')
    const client = await connect(pipePath, token)

    const names = await client.list()
    for (const fanout of LEAF_AGENT_CONTROL_TOOLS) {
      expect(names).not.toContain(fanout)
    }
  })
})

// === visibility is enforced at DISPATCH, not just at listing =================

describe('a hidden tool named on the wire is rejected at dispatch', () => {
  it('spawn_background_agent (surfaces: [], never listed) is rejected when called by name', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    // Valid input — so a rejection can only be the policy gate, never schema.
    const result = await client.call('spawn_background_agent', { prompt: 'do the thing' })
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('policy_denied')
  })

  it('resolve_desktop_dispatch (trusted-only) is rejected when called by name', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call('resolve_desktop_dispatch', {
      dispatchId: 'disp_x',
      status: 'resolved',
      resolution: { decision: 'allow' }
    })
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('policy_denied')
  })
})

// === the leaf-role guard holds through the bridge ============================

describe('leaf caller is rejected for every fanout tool (valid input, through the wire)', () => {
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

      const result = await client.call(tool, validInput[tool])
      expect(result.ok).toBe(false)
      // The leaf guard throws inside handleAgentControlToolCall (surfaced as
      // control_tool_failed); the MESSAGE is what proves the rejection is the
      // role guard and not schema validation or a kernel miss.
      expect(result.error?.code).toBe('control_tool_failed')
      expect(result.error?.message).toMatch(
        tool === 'send_agent_message'
          ? /Leaf workers cannot continue agent sessions\./
          : /Background agents are leaf workers and cannot start additional agents\./
      )
    })
  }
})

// === trustedUserControl is hard-false; consent-approval minting is unreachable

describe('a model can never gain trusted user control', () => {
  it('resolve_desktop_dispatch stays denied even if the wire input asserts trustedUserControl', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    // A model trying to flip the gate that mints consent approvals.
    const result = await client.call('resolve_desktop_dispatch', {
      dispatchId: 'disp_x',
      status: 'resolved',
      resolution: { decision: 'allow' },
      trustedUserControl: true
    })
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('policy_denied')
  })
})

// === ownerId is host-authoritative ===========================================

describe('ownerId is bound from the session, not the wire', () => {
  it('a wire ownerId that differs from the session owner is rejected', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call('list_agent_sessions', { ownerId: 'someone-else' })
    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(/does not match the active control owner/)
  })

  it('the host-bound owner is used when the wire omits ownerId', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    // A session that belongs to OWNER — it must appear for the host-bound owner.
    store.insertSession({ ownerId: OWNER, surfaceKind: 'main_chat', defaultAdapterId: 'acp' })
    const client = await connect(pipePath, token)

    const result = await client.call('list_agent_sessions', {})
    expect(result.ok).toBe(true)
    expect(Array.isArray(result.sessions)).toBe(true)
    expect((result.sessions as unknown[]).length).toBeGreaterThan(0)
  })
})

// === the consent gate stays closed on the model path =========================

describe('the sensitive-context consent gate holds through the bridge', () => {
  it('a sensitive screenshot snippet with no approved dispatch is refused', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call('build_desktop_context_packet', {
      surfaceKind: 'main_chat',
      objective: 'what am I looking at',
      ttlMs: 900_000,
      retentionClass: 'ephemeral',
      packetJson: {
        snippets: [
          {
            snippetId: 'snip-1',
            sourceKind: 'screenshot_image',
            operation: 'capture',
            provenance: {},
            metadata: {},
            content: 'a description of the screen',
            sensitivityTier: 'sensitive'
          }
        ]
      }
    })
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('control_tool_failed')
  })
})

// === input validation on the JSON-RPC envelope ===============================

describe('hostile input is handled without crashing main', () => {
  it('an unknown frame type gets a clean error, not a crash', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const frame = await client.sendRaw(JSON.stringify({ type: 'nonsense', callId: 'raw-1' }))
    expect(frame.type).toBe('error')
    expect(String(frame.message)).toMatch(/Unknown frame type/)
  })

  it('a malformed (non-JSON) frame drops the connection but the bridge keeps serving', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')

    const bad = await connect(pipePath, token)
    bad.sendRaw('this is not json at all')
    await bad.waitForClose()
    expect(bad.closed).toBe(true)

    // The bridge is still alive: a fresh connection still round-trips.
    const good = await connect(pipePath, token)
    const names = await good.list()
    expect(names.length).toBeGreaterThan(0)
  })

  it('a connection that never authenticates is dropped, and a bad token is rejected', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { pipePath } = bindSession(bridge, store, 'coordinator')

    const client = new BridgeClient(pipePath)
    await expect(client.hello('not-a-real-token')).rejects.toThrow()
    expect(client.closed).toBe(true)
  })
})

// === happy path ==============================================================

describe('a benign tool round-trips end to end', () => {
  it('list_agent_sessions succeeds for a model-facing coordinator', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.call('list_agent_sessions', {})
    expect(result.ok).toBe(true)
    expect(Array.isArray(result.sessions)).toBe(true)
  })
})
