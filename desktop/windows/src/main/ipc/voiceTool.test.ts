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
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentRuntimeKernel } from '../agentKernel/kernel'
import { AdapterRegistry } from '../agentKernel/adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from '../agentKernel/store'
import { executeHostTool } from '../agentKernel/toolRelayBridge'
import { createUpdateActionItemExecutor } from '../agentKernel/productToolExecutors'
import type { ActionItemRecord } from '../../shared/types'
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
    // A voice-surfaced serviceable product tool (see the VT1 gate test below).
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

  it('gates product tools by the realtime_voice surface (VT1) — raw/admin stay off voice', () => {
    const n = names('coordinator')
    // VT1: serviceable-but-desktop_chat-only product tools must NEVER reach voice.
    // execute_sql is a raw SQL door and save_knowledge_graph is a graph-admin write;
    // Mac does not voice-expose either. They remain available to the TYPED chat path
    // (WINDOWS_SERVICEABLE_PRODUCT_TOOLS) — this only narrows the voice catalog.
    expect(n).not.toContain('execute_sql')
    expect(n).not.toContain('save_knowledge_graph')
    // The voice-appropriate product tools (natural spoken requests) ARE advertised.
    for (const name of [
      'get_action_items',
      'create_action_item',
      'update_action_item',
      'search_tasks',
      'complete_task',
      'delete_task',
      'get_memories',
      'search_memories',
      'get_conversations',
      'search_conversations',
      'get_goals',
      'semantic_search',
      'get_daily_recap',
      'get_work_context',
      'capture_screen'
    ]) {
      expect(n).toContain(name)
    }
  })

  // Regression (2026-07-18): the assistant answered goal questions from MEMORIES
  // and TASKS because no goals tool existed anywhere in the catalog. get_goals
  // must stay advertised on the voice surface for BOTH roles (goal reads are
  // role-neutral) and be NAMED in the voice instruction so the model reaches for
  // it (the instruction-coverage guard is still 'pending' and would not fail).
  it('get_goals is voice-advertised for both roles and named in the voice instruction', async () => {
    expect(names('coordinator')).toContain('get_goals')
    expect(names('leaf')).toContain('get_goals')
    const { buildVoiceSystemInstruction } =
      await import('../../renderer/src/lib/voice/systemInstruction')
    expect(buildVoiceSystemInstruction()).toMatch(/\bget_goals\b/)
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

describe('advertised voice schema ↔ executor param contract (regression)', () => {
  // A voice tool's schemaOverride is what the model fills, and executeHostTool passes
  // those args to the executor with NO remap — so the advertised required param name
  // MUST be the one the executor reads. Regression: update_action_item advertised its
  // required id as `id` while the executor reads `action_item_id` (findByBackendId),
  // so every voice-driven update bounced on "action_item_id is required". Drive the
  // REAL executor through the REAL dispatch with the advertised required param.
  it('a voice update_action_item using the advertised required param actually updates', async () => {
    const decl = buildVoiceHubToolCatalog('coordinator').find(
      (t) => t.name === 'update_action_item'
    )
    expect(decl).toBeDefined()
    const required = (decl!.parameters as { required?: string[] }).required ?? []
    // The advertised required id param must be the one the executor consumes.
    expect(required).toEqual(['action_item_id'])

    const updateTask = vi.fn(async () => {})
    const task = { backendId: 'b1', description: 'old' } as unknown as ActionItemRecord
    const executor = createUpdateActionItemExecutor({
      findByBackendId: vi.fn(async (id: string) => (id === 'b1' ? task : null)),
      toggleTask: vi.fn(async () => {}),
      updateTask,
      deleteTask: vi.fn(async () => {})
    })

    const out = await executeHostTool(
      'update_action_item',
      { [required[0]]: 'b1', description: 'new' },
      {
        kernel: newKernel(),
        sessionId: 'sess-1',
        adapterId: 'pi-mono',
        productExecutors: new Map([['update_action_item', executor]])
      }
    )

    // It must reach the executor and apply the change — not bounce on the arg-name guard.
    expect(out).not.toMatch(/action_item_id is required/)
    expect(out).toBe("OK: task 'old' updated")
    expect(updateTask).toHaveBeenCalledWith('b1', { description: 'new' })
  })
})
