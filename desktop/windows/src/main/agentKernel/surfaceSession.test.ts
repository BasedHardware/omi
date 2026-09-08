// Tests for surfaceSession.ts (macOS surface-session.ts). Exercises the real
// SqliteAgentStore (node:sqlite driver, the store's test seam) so the surface
// resolution + floating->main merge run against actual SQL and partial-unique
// indexes.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import {
  clearOwnerSurfaceState,
  mergeFloatingChatIntoMainChat,
  resolveSurfaceSession,
  type SurfaceRef
} from './surfaceSession'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []

// Close stores before rmSync: on Windows an open SQLite handle blocks the temp
// dir delete (EPERM), which would otherwise mask the real assertion on failure.
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
  const dir = mkdtempSync(join(tmpdir(), 'omi-surface-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3'),
    reconcileOnOpen: false
  })
  openStores.push(store)
  return store
}

const mainRef: SurfaceRef = {
  surfaceKind: 'main_chat',
  externalRefKind: 'chat',
  externalRefId: 'default'
}

describe('resolveSurfaceSession', () => {
  it('creates a session + conversation on first resolve and is idempotent', () => {
    const store = newStore()
    const first = resolveSurfaceSession(
      store,
      { ownerId: 'owner', surfaceRef: mainRef },
      () => 1000
    )
    expect(first.agentSessionId).toBeTruthy()
    expect(first.conversationId).toBeTruthy()

    const second = resolveSurfaceSession(
      store,
      { ownerId: 'owner', surfaceRef: mainRef },
      () => 2000
    )
    expect(second).toEqual(first)

    // Exactly one session + one surface mapping exist.
    expect(Number(store.getRow('SELECT COUNT(*) AS c FROM sessions').c)).toBe(1)
    expect(Number(store.getRow('SELECT COUNT(*) AS c FROM surface_conversations').c)).toBe(1)
    store.close()
  })

  it('shares a session across surfaces with the same external ref but scopes by owner', () => {
    const store = newStore()
    const main = resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: mainRef }, () => 1000)
    const floating = resolveSurfaceSession(
      store,
      {
        ownerId: 'owner',
        surfaceRef: {
          surfaceKind: 'floating_chat',
          externalRefKind: 'chat',
          externalRefId: 'default'
        }
      },
      () => 1000
    )
    const otherOwner = resolveSurfaceSession(
      store,
      { ownerId: 'other', surfaceRef: mainRef },
      () => 1000
    )

    // Same owner + external ref (chat/default) => one shared agent session, but a
    // distinct conversation per surface_kind. A different owner is fully isolated.
    expect(floating.agentSessionId).toBe(main.agentSessionId)
    expect(floating.conversationId).not.toBe(main.conversationId)
    expect(otherOwner.agentSessionId).not.toBe(main.agentSessionId)
    expect(Number(store.getRow('SELECT COUNT(*) AS c FROM sessions').c)).toBe(2)
    expect(Number(store.getRow('SELECT COUNT(*) AS c FROM surface_conversations').c)).toBe(3)
    store.close()
  })

  it('pins the provider boundary from the requested adapter for a fresh main chat', () => {
    const store = newStore()
    const resolved = resolveSurfaceSession(
      store,
      { ownerId: 'owner', surfaceRef: mainRef, defaultAdapterId: 'openclaw' },
      () => 1000
    )
    const row = store.getRow(
      'SELECT default_adapter_id, provider_boundary FROM sessions WHERE session_id = ?',
      [resolved.agentSessionId]
    )
    expect(row.default_adapter_id).toBe('openclaw')
    expect(row.provider_boundary).toBe('local_user:openclaw')
    store.close()
  })
})

describe('mergeFloatingChatIntoMainChat', () => {
  it('folds the floating transcript into main chat and removes the floating mapping', () => {
    const store = newStore()
    const floatingRef: SurfaceRef = {
      surfaceKind: 'floating_chat',
      externalRefKind: 'chat',
      externalRefId: 'default'
    }
    const floating = resolveSurfaceSession(
      store,
      { ownerId: 'owner', surfaceRef: floatingRef },
      () => 1000
    )
    store.insertConversationTurn({
      conversationId: floating.conversationId,
      role: 'user',
      surfaceKind: 'floating_chat',
      content: 'hello from floating',
      createdAtMs: 1001,
      metadataJson: '{}'
    })
    store.insertConversationTurn({
      conversationId: floating.conversationId,
      role: 'assistant',
      surfaceKind: 'floating_chat',
      content: 'reply from floating',
      createdAtMs: 1002,
      metadataJson: '{}'
    })

    const result = mergeFloatingChatIntoMainChat(store, { ownerId: 'owner' }, () => 2000)
    expect(result.mergedTurns).toBe(2)
    expect(result.removedFloatingMapping).toBe(true)

    // Floating mapping is gone; main chat now holds the two turns.
    const floatingCount = Number(
      store.getRow(
        "SELECT COUNT(*) AS c FROM surface_conversations WHERE surface_kind = 'floating_chat'"
      ).c
    )
    expect(floatingCount).toBe(0)
    const main = resolveSurfaceSession(store, { ownerId: 'owner', surfaceRef: mainRef }, () => 3000)
    const mainTurns = store.allRows(
      'SELECT surface_kind, content FROM conversation_turns WHERE conversation_id = ? ORDER BY created_at_ms ASC',
      [main.conversationId]
    )
    expect(mainTurns.map((t) => t.content)).toEqual(['hello from floating', 'reply from floating'])
    expect(mainTurns.every((t) => t.surface_kind === 'main_chat')).toBe(true)
    store.close()
  })

  it('is a no-op when there is no floating chat', () => {
    const store = newStore()
    const result = mergeFloatingChatIntoMainChat(store, { ownerId: 'owner' }, () => 2000)
    expect(result).toEqual({ mergedTurns: 0, removedFloatingMapping: false })
    store.close()
  })
})

describe('clearOwnerSurfaceState', () => {
  it('invalidates active bindings for the owner', () => {
    const store = newStore()
    const resolved = resolveSurfaceSession(
      store,
      { ownerId: 'owner', surfaceRef: mainRef },
      () => 1000
    )
    const b = store.insertAdapterBinding({
      sessionId: resolved.agentSessionId,
      adapterId: 'acp',
      bindingGeneration: 1,
      adapterNativeSessionId: 'native-1',
      adapterInstanceId: 'node',
      resumeFidelity: 'native',
      status: 'active'
    })

    const cleared = clearOwnerSurfaceState(store, 'owner', () => 5000)
    expect(cleared.invalidatedBindingIds).toEqual([b.bindingId])
    expect(
      store.getRow('SELECT status FROM adapter_bindings WHERE binding_id = ?', [b.bindingId]).status
    ).toBe('invalid')
    store.close()
  })
})
