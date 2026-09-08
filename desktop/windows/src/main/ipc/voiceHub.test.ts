// voiceHub IPC handler tests — the realtime-hub → kernel transcript door (PR-A) and
// the read-only continuity seed (PR-B), driven against a REAL SQLite store (via
// node:sqlite's DatabaseSync, as kernel.test.ts / mainChat.test.ts do) so the whole
// resolveSurfaceSession → recordSurfaceTurn → getMainChatTurnTail path is exercised.
//
// The load-bearing case is the INV-CHAT-1 double-record guard: a completed hub turn
// and a cascade `mainChat:send` for the SAME logical press share one turnId, so the
// human turn is recorded EXACTLY ONCE across both paths (the shared-key half of the
// design; the primary guarantee is hub-XOR-cascade route mutual-exclusivity).

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from '../agentKernel/kernel'
import { AdapterRegistry } from '../agentKernel/adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from '../agentKernel/store'
import type { ConversationTurn } from '../agentKernel/types'
import { recordVoiceHubTurn, readVoiceHubSeedContext, type VoiceHubDeps } from './voiceHub'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const OWNER = 'owner-voice-1'

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
  const dir = mkdtempSync(join(tmpdir(), 'omi-voicehub-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  return new AgentRuntimeKernel({ store, registry: new AdapterRegistry(), runtimeNodeId: 'node-a' })
}

function ready(kernel: AgentRuntimeKernel): VoiceHubDeps {
  return { kernel, ownerId: OWNER, ownerReady: true }
}

/** The main_chat/chat/default conversation the typed tail reads. */
function tail(kernel: AgentRuntimeKernel): ConversationTurn[] {
  return kernel.getMainChatTurnTail(OWNER, 50, 'default').turns
}

function userTurns(turns: ConversationTurn[]): ConversationTurn[] {
  return turns.filter((t) => t.role === 'user')
}

describe('recordVoiceHubTurn — hub turns → the one kernel transcript (INV-CHAT-1)', () => {
  it('records the turn into the SAME main_chat conversation the typed tail reads', () => {
    const kernel = newKernel()
    const result = recordVoiceHubTurn(
      { chatId: 'default', userText: 'remember my color is teal', assistantText: 'Got it.' },
      ready(kernel)
    )
    expect(result.recorded).toBe(true)
    expect(result.duplicate).toBe(false)

    const turns = tail(kernel)
    expect(turns.map((t) => [t.role, t.content])).toEqual([
      ['user', 'remember my color is teal'],
      ['assistant', 'Got it.']
    ])
    // Tagged origin realtime_voice (what makes the seed show it as [live:voice]).
    const meta = JSON.parse(turns[0].metadataJson) as { origin?: string }
    expect(meta.origin).toBe('realtime_voice')
  })

  it('dedupes on the per-press turnId (a re-fired record is a no-op)', () => {
    const kernel = newKernel()
    const deps = ready(kernel)
    recordVoiceHubTurn(
      { chatId: 'default', userText: 'hi', assistantText: 'hello', idempotencyKey: 'turn-1' },
      deps
    )
    const second = recordVoiceHubTurn(
      { chatId: 'default', userText: 'hi', assistantText: 'hello', idempotencyKey: 'turn-1' },
      deps
    )
    expect(second.recorded).toBe(false)
    expect(second.duplicate).toBe(true)
    expect(userTurns(tail(kernel))).toHaveLength(1)
  })

  it('INV-CHAT-1 double-record: hub + cascade share the turnId → ONE human turn', () => {
    const kernel = newKernel()
    const deps = ready(kernel)
    const surfaceRef = { surfaceKind: 'main_chat', externalRefKind: 'chat', externalRefId: 'default' }

    // The hub-native record for the press (keyed on the turnId).
    recordVoiceHubTurn(
      { chatId: 'default', userText: 'what is my color', assistantText: 'Teal.', idempotencyKey: 'turn-shared' },
      deps
    )
    // The cascade path (mainChat:send) records the user turn keyed on the SAME turnId
    // (belt-and-suspenders for the warm-wait→cascade handoff edge). It must dedupe.
    const cascade = kernel.recordSurfaceTurn({
      ownerId: OWNER,
      surfaceRef,
      userText: 'what is my color',
      assistantText: '',
      origin: 'main_chat',
      idempotencyKey: 'turn-shared'
    })
    expect(cascade.duplicate).toBe(true)
    // EXACTLY one human turn across both paths.
    expect(userTurns(tail(kernel))).toHaveLength(1)
  })

  it('refuses (records nothing) while the control-plane owner is not ready', () => {
    const kernel = newKernel()
    const result = recordVoiceHubTurn(
      { chatId: 'default', userText: 'u', assistantText: 'a' },
      { kernel, ownerId: 'local-user', ownerReady: false }
    )
    expect(result).toEqual({ recorded: false, duplicate: false, reason: 'owner_not_ready' })
    expect(tail(kernel)).toHaveLength(0)
  })

  it('ignores an empty turn', () => {
    const kernel = newKernel()
    const result = recordVoiceHubTurn(
      { chatId: 'default', userText: '   ', assistantText: '' },
      ready(kernel)
    )
    expect(result).toEqual({ recorded: false, duplicate: false, reason: 'empty' })
    expect(tail(kernel)).toHaveLength(0)
  })
})

describe('readVoiceHubSeedContext — read-only continuity seed (PR-B)', () => {
  it('returns the recent turns source-tagged [live:voice]/[live:typed] with their keys', () => {
    const kernel = newKernel()
    const deps = ready(kernel)
    const surfaceRef = { surfaceKind: 'main_chat', externalRefKind: 'chat', externalRefId: 'default' }
    // A typed turn (origin main_chat) …
    kernel.recordSurfaceTurn({
      ownerId: OWNER,
      surfaceRef,
      userText: 'my dog is Pixel',
      assistantText: 'Noted.',
      origin: 'main_chat',
      idempotencyKey: 'typed-1'
    })
    // … and a voice turn (origin realtime_voice).
    recordVoiceHubTurn(
      { chatId: 'default', userText: 'what is my color', assistantText: 'Teal.', idempotencyKey: 'voice-1' },
      deps
    )

    const seed = readVoiceHubSeedContext({ chatId: 'default' }, deps)
    expect(seed.context).toContain('[live:typed]')
    expect(seed.context).toContain('[live:voice]')
    expect(seed.context).toContain('my dog is Pixel')
    expect(seed.context).toContain('Teal.')
    // The keys let the hub tell whether its warm session already reflects these.
    expect(seed.idempotencyKeys).toEqual(expect.arrayContaining(['typed-1', 'voice-1']))
  })

  it('is READ-ONLY: an absent conversation yields an empty seed and creates nothing', () => {
    const kernel = newKernel()
    const deps = ready(kernel)
    const seed = readVoiceHubSeedContext({ chatId: 'default' }, deps)
    expect(seed).toEqual({ context: '', idempotencyKeys: [] })
    // No conversation was created as a side effect (the tail read still finds none).
    expect(kernel.getMainChatTurnTail(OWNER, 50, 'default').conversationId).toBeNull()
  })

  it('returns an empty seed while the owner is not ready', () => {
    const kernel = newKernel()
    const seed = readVoiceHubSeedContext(
      { chatId: 'default' },
      { kernel, ownerId: 'local-user', ownerReady: false }
    )
    expect(seed).toEqual({ context: '', idempotencyKeys: [] })
  })
})
