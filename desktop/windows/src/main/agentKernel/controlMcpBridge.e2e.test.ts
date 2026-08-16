// End-to-end exercise of the REAL model-facing path: a spawned subprocess running
// the shipped `omi-mcp-entry.mjs` speaks MCP JSON-RPC on its stdio, relays each
// call back to a REAL AgentControlMcpBridge over a REAL socket, and the bridge
// routes into the REAL handleAgentControlToolCall against a REAL kernel/store.
//
// This is the "exercise it for real" evidence, not a hermetic unit test — it
// SHELLS OUT to a subprocess, which the hermetic suite must not do. So it is
// gated behind OMI_MCP_E2E and skipped by default (in `pnpm test` / CI). Run it
// explicitly for evidence:
//
//   OMI_MCP_E2E=1 npx vitest run src/main/agentKernel/controlMcpBridge.e2e.test.ts
//
// The in-process piped-transport coverage lives in controlMcpBridge.test.ts;
// this file exists only to prove the full stdio↔socket↔dispatch chain works
// against the actual entry binary.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from './kernel'
import { AdapterRegistry } from './adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import { AgentControlMcpBridge } from './controlMcpBridge'

const RUN_E2E = Boolean(process.env.OMI_MCP_E2E)
const ENTRY_PATH = fileURLToPath(new URL('./omi-mcp-entry.mjs', import.meta.url))
const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory

const cleanup: Array<() => void | Promise<void>> = []

afterEach(async () => {
  for (const fn of cleanup.splice(0).reverse()) await fn()
})

/** A tiny MCP client speaking line-delimited JSON-RPC over the child's stdio. */
class StdioMcpClient {
  private buffer = ''
  private id = 0
  private readonly pending = new Map<number, (msg: Record<string, unknown>) => void>()

  constructor(private readonly child: ChildProcessWithoutNullStreams) {
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      this.buffer += chunk
      let nl = this.buffer.indexOf('\n')
      while (nl >= 0) {
        const line = this.buffer.slice(0, nl)
        this.buffer = this.buffer.slice(nl + 1)
        if (line.trim()) {
          const msg = JSON.parse(line) as Record<string, unknown>
          const resolve = typeof msg.id === 'number' ? this.pending.get(msg.id) : undefined
          if (resolve && typeof msg.id === 'number') {
            this.pending.delete(msg.id)
            resolve(msg)
          }
        }
        nl = this.buffer.indexOf('\n')
      }
    })
  }

  request(method: string, params?: Record<string, unknown>): Promise<Record<string, unknown>> {
    const id = ++this.id
    return new Promise((resolve) => {
      this.pending.set(id, resolve)
      this.child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`)
    })
  }
}

describe.skipIf(!RUN_E2E)('real subprocess speaks MCP end to end', () => {
  it('initializes, lists tools, runs a benign tool, and is denied a hidden one', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'omi-mcp-e2e-'))
    cleanup.push(() => rmSync(dir, { recursive: true, force: true }))
    const store = new SqliteAgentStore({
      databaseFactory: nodeSqliteFactory,
      databasePath: join(dir, 'omi-agentd.sqlite3')
    })
    cleanup.push(() => store.close())
    const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() })
    const bridge = new AgentControlMcpBridge({ kernel })
    cleanup.push(() => bridge.close())
    await bridge.start()

    const session = store.insertSession({
      ownerId: 'e2e-owner',
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp',
      executionRole: 'coordinator'
    })
    const { pipePath, token } = bridge.register(session.sessionId, 'acp')

    const child = spawn(process.execPath, [ENTRY_PATH], {
      env: { ...process.env, OMI_BRIDGE_PIPE: pipePath, OMI_BRIDGE_TOKEN: token },
      stdio: ['pipe', 'pipe', 'pipe']
    }) as ChildProcessWithoutNullStreams
    cleanup.push(() => {
      child.kill()
    })
    const client = new StdioMcpClient(child)

    const init = await client.request('initialize')
    expect((init.result as Record<string, unknown>).serverInfo).toMatchObject({ name: 'omi' })

    const list = await client.request('tools/list')
    const tools = (list.result as { tools: Array<{ name: string }> }).tools
    const names = tools.map((t) => t.name)
    expect(names).toContain('list_agent_sessions')
    expect(names).not.toContain('spawn_background_agent')
    expect(names).not.toContain('resolve_desktop_dispatch')
    // Product tools travel the same omi-tools-stdio surface as control tools.
    expect(names).toContain('get_goals')
    expect(names).toContain('get_memories')

    const happy = await client.request('tools/call', {
      name: 'list_agent_sessions',
      arguments: {}
    })
    const happyText = (happy.result as { content: Array<{ text: string }> }).content[0].text
    expect(JSON.parse(happyText).ok).toBe(true)

    // A product tool dispatches to its executor end-to-end through the real
    // subprocess. No backend session in this fixture → the not-signed-in string,
    // which still proves the chain (before the fix this was "unknown_control_tool").
    const goals = await client.request('tools/call', { name: 'get_goals', arguments: {} })
    const goalsText = (goals.result as { content: Array<{ text: string }> }).content[0].text
    expect(goalsText).not.toContain('unknown_control_tool')
    expect(goalsText).toMatch(/not signed in to Omi/)

    const denied = await client.request('tools/call', {
      name: 'spawn_background_agent',
      arguments: { prompt: 'try to escalate' }
    })
    const deniedText = (denied.result as { content: Array<{ text: string }> }).content[0].text
    const deniedEnvelope = JSON.parse(deniedText)
    expect(deniedEnvelope.ok).toBe(false)
    expect(deniedEnvelope.error.code).toBe('policy_denied')
  })
})
