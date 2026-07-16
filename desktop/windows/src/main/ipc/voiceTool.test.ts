// voiceTool IPC tests — the realtime-hub TOOL LOOP (PR-C, INV-AGENT).
//
// Two surfaces:
//   * buildVoiceHubToolCatalog — the pure, role-parameterized catalog projection.
//     Coordinator gets the coordinator control tools (spawn_agent, …); a LEAF voice
//     session must NOT (the catalog half of the leaf-escape defense; the dispatch
//     half is executeHostTool's leaf guard).
//   * executeVoiceHubTool / readVoiceHubToolCatalog — driven against a REAL SQLite
//     kernel (as voiceHub.test.ts does) so role/owner are host-derived from the
//     resolved main_chat surface session, never model/renderer-claimed.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from '../agentKernel/kernel'
import { AdapterRegistry } from '../agentKernel/adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from '../agentKernel/store'
import {
  buildVoiceHubToolCatalog,
  executeVoiceHubTool,
  readVoiceHubToolCatalog,
  type VoiceToolDeps
} from './voiceTool'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const OWNER = 'owner-voicetool-1'

afterEach(() => {
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

function newKernel(): AgentRuntimeKernel {
  const dir = mkdtempSync(join(tmpdir(), 'omi-voicetool-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  return new AgentRuntimeKernel({ store, registry: new AdapterRegistry(), runtimeNodeId: 'node-a' })
}

function ready(kernel: AgentRuntimeKernel): VoiceToolDeps {
  return { kernel, ownerId: OWNER, ownerReady: true }
}

const names = (role: 'coordinator' | 'leaf'): string[] =>
  buildVoiceHubToolCatalog(role).map((t) => t.name)

describe('buildVoiceHubToolCatalog — host-derived, role-gated (INV-AGENT)', () => {
  it('coordinator gets the control coordinator tools + a serviceable product tool', () => {
    const catalog = buildVoiceHubToolCatalog('coordinator')
    const n = catalog.map((t) => t.name)
    // The command mechanism + a read control tool.
    expect(n).toContain('spawn_agent')
    expect(n).toContain('list_agent_sessions')
    // The one product tool serviceable on Windows today.
    expect(n).toContain('capture_screen')
    // Every entry is a well-formed provider-neutral declaration.
    for (const t of catalog) {
      expect(typeof t.name).toBe('string')
      expect(typeof t.description).toBe('string')
      expect(t.description.length).toBeGreaterThan(0)
      expect((t.parameters as { type?: string }).type).toBe('object')
    }
  })

  it('a leaf voice session cannot reach coordinator control tools', () => {
    const leaf = names('leaf')
    // Coordinator-only control tools are withheld from a leaf.
    expect(leaf).not.toContain('spawn_agent')
    expect(leaf).not.toContain('run_agent_and_wait')
    // Non-coordinator control tools + serviceable product tools remain.
    expect(leaf).toContain('list_agent_sessions')
    expect(leaf).toContain('capture_screen')
  })

  it('omits non-serviceable product tools (advertise-then-degrade avoided)', () => {
    const n = names('coordinator')
    // execute_sql / get_memories have no Windows executor → never advertised to voice.
    expect(n).not.toContain('execute_sql')
    expect(n).not.toContain('get_memories')
  })

  it('uses the voice realtimeDescription + schemaOverride when present', () => {
    const spawn = buildVoiceHubToolCatalog('coordinator').find((t) => t.name === 'spawn_agent')!
    expect(spawn.description).toMatch(/background/i)
    // The voice schemaOverride requires `objective`.
    expect((spawn.parameters as { required?: string[] }).required).toContain('objective')
  })
})

describe('readVoiceHubToolCatalog — role read from the main_chat session', () => {
  it('returns an empty catalog until a signed-in owner exists', () => {
    const kernel = newKernel()
    expect(readVoiceHubToolCatalog({ kernel, ownerId: OWNER, ownerReady: false })).toEqual([])
  })

  it('resolves the coordinator role from the top-level main_chat surface', () => {
    const kernel = newKernel()
    const catalog = readVoiceHubToolCatalog(ready(kernel))
    // main_chat is a top-level coordinator surface, so spawn_agent is advertised.
    expect(catalog.map((t) => t.name)).toContain('spawn_agent')
  })
})

describe('executeVoiceHubTool — in-process dispatch via executeHostTool', () => {
  it('fails closed when no signed-in owner exists (Mac currentOwnerId parity)', async () => {
    const kernel = newKernel()
    const out = await executeVoiceHubTool(
      { name: 'list_agent_sessions', argumentsJSON: '{}' },
      { kernel, ownerId: OWNER, ownerReady: false }
    )
    expect(out).toMatch(/sign-in has not completed/i)
  })

  it('rejects a missing tool name', async () => {
    const kernel = newKernel()
    const out = await executeVoiceHubTool({ name: '', argumentsJSON: '{}' }, ready(kernel))
    expect(out).toMatch(/missing tool name/i)
  })

  it('routes a control tool through the host with coordinator authority', async () => {
    const kernel = newKernel()
    const out = await executeVoiceHubTool(
      { name: 'list_agent_sessions', argumentsJSON: '{}' },
      ready(kernel)
    )
    const parsed = JSON.parse(out)
    expect(parsed.ok).toBe(true)
    expect(Array.isArray(parsed.sessions)).toBe(true)
  })

  it('tolerates malformed JSON arguments (parsed to {})', async () => {
    const kernel = newKernel()
    const out = await executeVoiceHubTool(
      { name: 'list_agent_sessions', argumentsJSON: 'not json' },
      ready(kernel)
    )
    expect(JSON.parse(out).ok).toBe(true)
  })
})
