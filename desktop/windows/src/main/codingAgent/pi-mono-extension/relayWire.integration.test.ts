// End-to-end wire proof for the PR-1 tool plane: the REAL pi extension client and
// the REAL host relay + kernel, joined over a real named pipe. Everything the
// production path does is exercised EXCEPT the pi subprocess spawn and the network
// call to api.omi.me — those are the only pieces not reachable from plain-node
// Vitest.
//
// The chain proven here (top → bottom): the host mints a per-binding token via
// AgentToolRelayBridge.register(); the extension resolves that turn's bridge target
// from the per-turn CONTEXT FILE (bridgePipe/bridgeToken — how PR-1 flows identity),
// connects lazily, performs the hello/hello_ok handshake, and forwards a control
// tool_use; the host resolves authority ONLY from the token→binding (never the
// frame) and dispatches list_agent_sessions through handleAgentControlToolCall into
// the real kernel; the ok envelope round-trips back to the extension.
//
// This is the reliable stand-in for the live typed-chat control-tool probe under a
// loaded machine: same wire, same authority model, same executor entry — just no
// subprocess/network. Driver: node:sqlite via the store's databaseFactory seam.

import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from '../../agentKernel/kernel'
import { AdapterRegistry } from '../../agentKernel/adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from '../../agentKernel/store'
import { AgentToolRelayBridge } from '../../agentKernel/toolRelayBridge'
import { __callSwiftToolForTest, __resetOmiPipeForTest } from './index'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const OWNER = 'owner-wire-1'

const dirs: string[] = []
const stores: SqliteAgentStore[] = []
const bridges: AgentToolRelayBridge[] = []
let savedContextFile: string | undefined

beforeEach(() => {
  __resetOmiPipeForTest()
  savedContextFile = process.env.OMI_CONTEXT_FILE
})

afterEach(async () => {
  __resetOmiPipeForTest()
  if (savedContextFile === undefined) delete process.env.OMI_CONTEXT_FILE
  else process.env.OMI_CONTEXT_FILE = savedContextFile
  for (const bridge of bridges.splice(0)) await bridge.close()
  for (const store of stores.splice(0)) {
    try {
      store.close()
    } catch {
      // already closed
    }
  }
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

function newKernel(): { kernel: AgentRuntimeKernel; store: SqliteAgentStore; dir: string } {
  const dir = mkdtempSync(join(tmpdir(), 'omi-wire-'))
  dirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  stores.push(store)
  const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() })
  return { kernel, store, dir }
}

describe('pi extension ⇄ real host relay ⇄ real kernel (control tool round-trip)', () => {
  it('list_agent_sessions round-trips through the per-turn context-file target', async () => {
    const { kernel, store, dir } = newKernel()
    // A real coordinator session owned by OWNER — visible to the host-bound owner.
    const sessionId = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'pi-mono',
      executionRole: 'coordinator'
    }).sessionId

    // Host side: start the real relay and mint this binding's pipe+token, exactly
    // as controlPlane injects via registerToolRelay in production.
    const bridge = new AgentToolRelayBridge({ kernel })
    bridges.push(bridge)
    await bridge.start()
    const { pipePath, token } = bridge.register(sessionId, 'pi-mono')

    // The per-turn context file the host adapter writes (writeRelayContext): this is
    // how PR-1 hands the extension its bridge target for the turn.
    const contextFile = join(dir, 'context.json')
    writeFileSync(
      contextFile,
      JSON.stringify({
        adapterId: 'pi-mono',
        protocolVersion: 2,
        sessionId,
        runId: 'run_wire',
        attemptId: 'att_wire',
        bridgePipe: pipePath,
        bridgeToken: token
      })
    )
    process.env.OMI_CONTEXT_FILE = contextFile

    // Extension side: no pre-connect. The tool call itself resolves the target from
    // the context file, connects+handshakes lazily, and forwards the control frame.
    const raw = await __callSwiftToolForTest('list_agent_sessions', {})
    const envelope = JSON.parse(raw)
    expect(envelope.ok).toBe(true)
    expect(Array.isArray(envelope.sessions)).toBe(true)
    // The kernel returned the owner's real session set — the whole chain executed.
    expect((envelope.sessions as unknown[]).length).toBeGreaterThan(0)
  })

  it('a leaf-bound turn is refused spawn_agent by the host (leaf double-wall over the real wire)', async () => {
    const { kernel, store, dir } = newKernel()
    const sessionId = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'pi-mono',
      executionRole: 'leaf'
    }).sessionId

    const bridge = new AgentToolRelayBridge({ kernel })
    bridges.push(bridge)
    await bridge.start()
    const { pipePath, token } = bridge.register(sessionId, 'pi-mono')

    const contextFile = join(dir, 'context.json')
    writeFileSync(
      contextFile,
      JSON.stringify({ adapterId: 'pi-mono', sessionId, bridgePipe: pipePath, bridgeToken: token })
    )
    process.env.OMI_CONTEXT_FILE = contextFile

    const envelope = JSON.parse(await __callSwiftToolForTest('spawn_agent', { objective: 'x' }))
    expect(envelope.ok).toBe(false)
    expect(envelope.error?.message).toMatch(
      /Background agents are leaf workers and cannot start additional agents\./
    )
  })
})
