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
import { WINDOWS_SERVICEABLE_PRODUCT_TOOLS } from './toolRelayBridge'
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

  /** The raw `result` string from a tool call. Product tools return an opaque string
   *  (their formatted output or an `"Error: …"`), not the control tools' JSON envelope,
   *  so those must be read without JSON.parse. */
  async callRawResult(name: string, input: Record<string, unknown> = {}): Promise<string> {
    const frame = await this.send({ type: 'call', name, input })
    return frame.type === 'error' ? `relay_error: ${String(frame.message)}` : String(frame.result)
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
  it('a model-facing coordinator sees every control tool EXCEPT the trusted-only two, plus product tools', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const names = await client.list()

    // 16 of 18: never spawn_background_agent, never resolve_desktop_dispatch.
    for (const trustedOnly of TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES) {
      expect(names).not.toContain(trustedOnly)
    }
    const expectedControl = AGENT_CONTROL_TOOL_NAMES.filter(
      (n) => !TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES.has(n)
    )
    for (const control of expectedControl) {
      expect(names).toContain(control)
    }

    // This bridge IS the omi-tools-stdio surface: it must ALSO advertise the
    // serviceable product tools. Regression guard for the coding agent seeing zero
    // product tools (get_goals / get_memories / execute_sql / … were invisible).
    for (const product of [
      'get_goals',
      'get_memories',
      'execute_sql',
      'semantic_search',
      'get_conversations',
      'get_work_context'
    ]) {
      expect(names).toContain(product)
    }
    // Every advertised name is either a control tool or a Windows-serviceable
    // product tool — never a tool the bridge cannot dispatch (e.g. load_skill).
    const controlSet = new Set<string>(AGENT_CONTROL_TOOL_NAMES)
    for (const name of names) {
      expect(controlSet.has(name) || WINDOWS_SERVICEABLE_PRODUCT_TOOLS.has(name)).toBe(true)
    }
    expect(names).not.toContain('load_skill')
  })

  it('a leaf caller is shown none of the four fanout tools, but STILL sees product tools', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'leaf')
    const client = await connect(pipePath, token)

    const names = await client.list()
    for (const fanout of LEAF_AGENT_CONTROL_TOOLS) {
      expect(names).not.toContain(fanout)
    }
    // Product tools carry NO coordinator/leaf restriction — only the fanout control
    // tools are role-gated. A leaf worker must still be able to read the user's data.
    for (const product of ['get_goals', 'get_memories', 'execute_sql']) {
      expect(names).toContain(product)
    }
  })

  it('a leaf caller can DISPATCH a product tool (reaches its executor)', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'leaf')
    const client = await connect(pipePath, token)

    // The leaf role gate rejects the fanout tools; a product tool is NOT gated, so it
    // reaches its executor (returns the not-signed-in string, not a policy denial or
    // the unknown_control_tool envelope).
    const result = await client.callRawResult('get_goals', {})
    expect(result).not.toContain('unknown_control_tool')
    expect(result).not.toContain('policy_denied')
    expect(result).toMatch(/not signed in to Omi/)
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

// === product tools are reachable through the bridge (not just control tools) =

describe('product tools dispatch through the bridge to their executors', () => {
  it('get_goals reaches its product executor, not the unknown_control_tool path', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    // No backend session is configured in the hermetic suite, so the executor
    // returns its own not-signed-in string BEFORE any network call. The point is
    // that it reached the get_goals executor at all: before the fix this returned
    // the control-tool `{ok:false, error:{code:'unknown_control_tool'}}` envelope.
    const result = await client.callRawResult('get_goals', {})
    expect(result).not.toContain('unknown_control_tool')
    expect(result).toMatch(/not signed in to Omi/)
  })

  it('save_knowledge_graph reaches its executor and returns the validation error', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    // Empty nodes → the executor returns its validation error before touching the
    // DB (no native better-sqlite3 in this suite), proving product dispatch works.
    const result = await client.callRawResult('save_knowledge_graph', { nodes: [], edges: [] })
    expect(result).not.toContain('unknown_control_tool')
    expect(result).toMatch(/no valid nodes to save/)
  })

  it('an unknown tool name still degrades cleanly (neither control nor product)', async () => {
    const { kernel, store } = newKernel()
    const bridge = await startBridge(kernel)
    const { token, pipePath } = bindSession(bridge, store, 'coordinator')
    const client = await connect(pipePath, token)

    const result = await client.callRawResult('definitely_not_a_tool', {})
    expect(result).toMatch(/not available on Windows yet/)
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
