// Track 4: Conversation folders / starred — local-mirror CRUD, kept
// driver-agnostic (no better-sqlite3 / electron import) so it is unit-testable
// under plain-node vitest with node:sqlite — db.ts's native better-sqlite3 dep is
// built for Electron's ABI and can't load there. Same pattern as
// voiceTurnOutbox.ts / dbWipe.ts / dbMigrations.ts. The conversation_folders
// table and the local_conversation.starred/folder_id columns themselves are
// created in db.ts's bootstrap; these functions operate on the DB handle passed in.
//
// The folder rows are a LOCAL CACHE of the backend's /v1/folders (for instant
// paint before the network reconcile lands), not a source of truth. The starred/
// folder setters mirror a cloud conversation's fields locally; the backend
// remains authoritative (see lib/conversations/mutations.ts).

import type { ConversationFolder } from '../../shared/types'

// Minimal DB surface these functions need — satisfied structurally by both
// better-sqlite3 (production) and node:sqlite's DatabaseSync (tests). Bind params
// are positional `?` (no named-param dialect differences between the drivers).
export interface ConversationFoldersDb {
  prepare(sql: string): {
    run: (...params: unknown[]) => unknown
    all: (...params: unknown[]) => unknown[]
    get: (...params: unknown[]) => unknown
  }
}

type ConversationFolderRow = {
  id: string
  name: string
  color: string | null
  icon: string | null
  orderIdx: number
  isSystem: number
  conversationCount: number
  updatedAt: number | null
}

const FOLDER_COLUMNS =
  'id, name, color, icon, order_idx AS orderIdx, is_system AS isSystem, ' +
  'conversation_count AS conversationCount, updated_at AS updatedAt'

function mapRow(r: ConversationFolderRow): ConversationFolder {
  return {
    id: r.id,
    name: r.name,
    color: r.color ?? null,
    icon: r.icon ?? null,
    orderIdx: Number(r.orderIdx),
    // SQLite stores the flag as INTEGER 0/1 (no BOOLEAN type — codebase idiom).
    isSystem: Boolean(r.isSystem),
    conversationCount: Number(r.conversationCount),
    updatedAt: r.updatedAt == null ? null : Number(r.updatedAt)
  }
}

/** Cached folders, ordered the way the tab strip renders them: by order_idx then
 *  name (a stable tiebreak so equal orders don't shuffle between reads). */
export function listConversationFoldersOn(d: ConversationFoldersDb): ConversationFolder[] {
  const rows = d
    .prepare(`SELECT ${FOLDER_COLUMNS} FROM conversation_folders ORDER BY order_idx ASC, name ASC`)
    .all() as ConversationFolderRow[]
  return rows.map(mapRow)
}

function upsert(d: ConversationFoldersDb, f: ConversationFolder): void {
  d.prepare(
    `INSERT INTO conversation_folders
       (id, name, color, icon, order_idx, is_system, conversation_count, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       name = excluded.name,
       color = excluded.color,
       icon = excluded.icon,
       order_idx = excluded.order_idx,
       is_system = excluded.is_system,
       conversation_count = excluded.conversation_count,
       updated_at = excluded.updated_at`
  ).run(
    f.id,
    f.name,
    f.color ?? null,
    f.icon ?? null,
    f.orderIdx,
    f.isSystem ? 1 : 0,
    f.conversationCount,
    f.updatedAt ?? null
  )
}

/** Optimistic single-folder upsert (a just-created/edited folder) so the strip
 *  repaints before the backend reconcile lands. */
export function upsertConversationFolderOn(d: ConversationFoldersDb, f: ConversationFolder): void {
  upsert(d, f)
}

/** Reconcile the whole cache from the backend's /v1/folders: replace every row so
 *  a folder deleted on another device disappears here too. Non-transactional
 *  (the interface exposes only prepare, matching voiceTurnOutbox.ts) — this is a
 *  disposable cache, so a crash mid-replace just re-reconciles on next load. */
export function replaceConversationFoldersOn(
  d: ConversationFoldersDb,
  folders: ConversationFolder[]
): void {
  d.prepare('DELETE FROM conversation_folders').run()
  for (const f of folders) upsert(d, f)
}

/** Drop a single folder from the cache (optimistic delete). */
export function deleteConversationFolderOn(d: ConversationFoldersDb, id: string): void {
  d.prepare('DELETE FROM conversation_folders WHERE id = ?').run(id)
}

/** Mirror a conversation's starred flag locally (backend stays authoritative). */
export function setLocalConversationStarredOn(
  d: ConversationFoldersDb,
  id: string,
  starred: boolean
): void {
  d.prepare('UPDATE local_conversation SET starred = ? WHERE id = ?').run(starred ? 1 : 0, id)
}

/** Mirror a conversation's folder assignment locally (null = remove from folder). */
export function setLocalConversationFolderOn(
  d: ConversationFoldersDb,
  id: string,
  folderId: string | null
): void {
  d.prepare('UPDATE local_conversation SET folder_id = ? WHERE id = ?').run(folderId, id)
}
