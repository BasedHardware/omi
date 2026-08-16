// Tests for conversationTurns.ts (macOS conversation-turns.ts): idempotent
// surface-turn recording, transcript tail ordering, and binding delivery
// high-water tracking. Runs against the real store (node:sqlite seam).

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import { resolveSurfaceSession, type SurfaceRef } from './surfaceSession'
import {
  advanceBindingTurnDelivery,
  listRecentConversationTurns,
  recordSurfaceTurn
} from './conversationTurns'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []

// Close stores before rmSync so a failed test can't leave an open SQLite handle
// blocking the Windows temp-dir delete (EPERM).
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

function newStore(): SqliteAgentStore {
  const dir = mkdtempSync(join(tmpdir(), 'omi-turns-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3'),
    reconcileOnOpen: false
  })
  openStores.push(store)
  return store
}

const ref: SurfaceRef = {
  surfaceKind: 'main_chat',
  externalRefKind: 'chat',
  externalRefId: 'default'
}

describe('recordSurfaceTurn', () => {
  it('records a user + assistant turn and dedups on idempotency key', () => {
    const store = newStore()
    const first = recordSurfaceTurn(store, {
      ownerId: 'owner',
      surfaceRef: ref,
      userText: 'hi',
      assistantText: 'hello',
      origin: 'test',
      idempotencyKey: 'turn-1',
      nowMs: 1000
    })
    expect(first.recorded).toBe(true)
    expect(first.duplicate).toBe(false)
    expect(first.userTurn?.content).toBe('hi')
    expect(first.assistantTurn?.content).toBe('hello')

    const replay = recordSurfaceTurn(store, {
      ownerId: 'owner',
      surfaceRef: ref,
      userText: 'hi',
      assistantText: 'hello',
      origin: 'test',
      idempotencyKey: 'turn-1',
      nowMs: 1000
    })
    expect(replay.recorded).toBe(false)
    expect(replay.duplicate).toBe(true)

    const turns = listRecentConversationTurns(store, first.conversationId)
    expect(turns.map((t) => t.content)).toEqual(['hi', 'hello'])
    store.close()
  })

  it('skips empty turns', () => {
    const store = newStore()
    const result = recordSurfaceTurn(store, {
      ownerId: 'owner',
      surfaceRef: ref,
      userText: '   ',
      assistantText: '',
      origin: 'test',
      nowMs: 1000
    })
    expect(result.recorded).toBe(false)
    expect(result.duplicate).toBe(false)
    store.close()
  })
})

describe('advanceBindingTurnDelivery', () => {
  it('advances the binding high-water mark to the latest turn', () => {
    const store = newStore()
    const resolved = resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: ref }, () => 1000)
    store.insertConversationTurn({
      conversationId: resolved.conversationId,
      role: 'user',
      surfaceKind: 'main_chat',
      content: 'first',
      createdAtMs: 1500,
      metadataJson: '{}'
    })
    const b = store.insertAdapterBinding({
      sessionId: resolved.agentSessionId,
      adapterId: 'acp',
      bindingGeneration: 1,
      adapterNativeSessionId: 'native-1',
      adapterInstanceId: 'node',
      resumeFidelity: 'native',
      status: 'active'
    })

    advanceBindingTurnDelivery(store, b.bindingId, resolved.conversationId, 9999)
    const row = store.getRow(
      'SELECT last_delivered_turn_created_at_ms FROM adapter_bindings WHERE binding_id = ?',
      [b.bindingId]
    )
    expect(Number(row.last_delivered_turn_created_at_ms)).toBe(1500)
    store.close()
  })
})
