// conversationFolders.ts CRUD, proven against a REAL SQLite database via
// node:sqlite. db.ts's better-sqlite3 is rebuilt for Electron's ABI and can't
// load under plain-node vitest (same constraint as dbSchema.track4.test.ts), so
// the tables are created from DDL replicated verbatim from db.ts's bootstrap and
// the REAL driver-agnostic helpers are imported and exercised. DatabaseSync
// satisfies the ConversationFoldersDb shape structurally (positional `?` params).
import { DatabaseSync } from 'node:sqlite'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  listConversationFoldersOn,
  replaceConversationFoldersOn,
  upsertConversationFolderOn,
  deleteConversationFolderOn,
  setLocalConversationStarredOn,
  setLocalConversationFolderOn,
  type ConversationFoldersDb
} from './conversationFolders'
import type { ConversationFolder } from '../../shared/types'

// conversation_folders (verbatim from db.ts) + a minimal local_conversation with
// the Track 4 starred/folder_id columns (the starred/folder setters target it).
const SCHEMA = `
  CREATE TABLE conversation_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT,
    icon TEXT,
    order_idx INTEGER NOT NULL DEFAULT 0,
    is_system INTEGER NOT NULL DEFAULT 0,
    conversation_count INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER
  );
  CREATE TABLE local_conversation (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    ended_at INTEGER NOT NULL,
    transcript TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    starred INTEGER NOT NULL DEFAULT 0,
    folder_id TEXT
  );
`

function folder(over: Partial<ConversationFolder> = {}): ConversationFolder {
  return {
    id: 'f1',
    name: 'Work',
    color: '#6B7280',
    icon: 'folder',
    orderIdx: 0,
    isSystem: false,
    conversationCount: 0,
    updatedAt: 1000,
    ...over
  }
}

let db: DatabaseSync
let d: ConversationFoldersDb

beforeEach(() => {
  db = new DatabaseSync(':memory:')
  db.exec(SCHEMA)
  d = db as unknown as ConversationFoldersDb
  db.prepare(
    'INSERT INTO local_conversation (id, started_at, ended_at, transcript, created_at) VALUES (?, 0, 0, ?, 0)'
  ).run('c1', '')
})

describe('conversation folder cache CRUD', () => {
  it('upserts a folder and reads it back with typed fields', () => {
    upsertConversationFolderOn(d, folder({ id: 'f1', name: 'Work', isSystem: true }))
    const list = listConversationFoldersOn(d)
    expect(list).toHaveLength(1)
    expect(list[0]).toMatchObject({
      id: 'f1',
      name: 'Work',
      color: '#6B7280',
      icon: 'folder',
      orderIdx: 0,
      isSystem: true, // INTEGER 1 → boolean
      conversationCount: 0,
      updatedAt: 1000
    })
  })

  it('upsert updates an existing folder in place (no duplicate row)', () => {
    upsertConversationFolderOn(d, folder({ id: 'f1', name: 'Work' }))
    upsertConversationFolderOn(d, folder({ id: 'f1', name: 'Renamed', color: '#EF4444' }))
    const list = listConversationFoldersOn(d)
    expect(list).toHaveLength(1)
    expect(list[0].name).toBe('Renamed')
    expect(list[0].color).toBe('#EF4444')
  })

  it('orders folders by order_idx then name', () => {
    upsertConversationFolderOn(d, folder({ id: 'b', name: 'Beta', orderIdx: 1 }))
    upsertConversationFolderOn(d, folder({ id: 'a', name: 'Alpha', orderIdx: 1 }))
    upsertConversationFolderOn(d, folder({ id: 'z', name: 'Zeta', orderIdx: 0 }))
    expect(listConversationFoldersOn(d).map((f) => f.id)).toEqual(['z', 'a', 'b'])
  })

  it('replace swaps the whole cache (a since-deleted folder disappears)', () => {
    replaceConversationFoldersOn(d, [
      folder({ id: 'f1', orderIdx: 0 }),
      folder({ id: 'f2', name: 'Personal', orderIdx: 1 })
    ])
    expect(listConversationFoldersOn(d).map((f) => f.id)).toEqual(['f1', 'f2'])
    // Reconcile from a backend fetch that no longer has f1.
    replaceConversationFoldersOn(d, [folder({ id: 'f2', name: 'Personal', orderIdx: 1 })])
    expect(listConversationFoldersOn(d).map((f) => f.id)).toEqual(['f2'])
  })

  it('replace with an empty list clears the cache', () => {
    upsertConversationFolderOn(d, folder({ id: 'f1' }))
    replaceConversationFoldersOn(d, [])
    expect(listConversationFoldersOn(d)).toEqual([])
  })

  it('deletes a single folder', () => {
    replaceConversationFoldersOn(d, [folder({ id: 'f1' }), folder({ id: 'f2' })])
    deleteConversationFolderOn(d, 'f1')
    expect(listConversationFoldersOn(d).map((f) => f.id)).toEqual(['f2'])
  })

  it('tolerates null color/icon/updatedAt', () => {
    upsertConversationFolderOn(d, folder({ id: 'f1', color: null, icon: null, updatedAt: null }))
    expect(listConversationFoldersOn(d)[0]).toMatchObject({
      color: null,
      icon: null,
      updatedAt: null
    })
  })
})

describe('local starred / folder mirror', () => {
  function readConv(id: string): { starred: number; folder_id: string | null } {
    return db
      .prepare('SELECT starred, folder_id FROM local_conversation WHERE id = ?')
      .get(id) as { starred: number; folder_id: string | null }
  }

  it('sets and clears the local starred flag', () => {
    setLocalConversationStarredOn(d, 'c1', true)
    expect(readConv('c1').starred).toBe(1)
    setLocalConversationStarredOn(d, 'c1', false)
    expect(readConv('c1').starred).toBe(0)
  })

  it('assigns and removes a local folder', () => {
    setLocalConversationFolderOn(d, 'c1', 'f1')
    expect(readConv('c1').folder_id).toBe('f1')
    setLocalConversationFolderOn(d, 'c1', null)
    expect(readConv('c1').folder_id).toBeNull()
  })
})
