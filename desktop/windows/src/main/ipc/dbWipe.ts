// Sign-out user-data wipe, kept driver-agnostic (no better-sqlite3 import) so it
// is unit-testable under plain-node vitest with node:sqlite — db.ts's native
// better-sqlite3 dep is built for Electron's ABI and can't load there. Same
// pattern as dbMigrations.ts.
//
// Every table in the local database holds user-scoped data (conversations +
// sync outbox, live captions, the local knowledge graph, onboarding brain-map,
// app-usage stats, rewind frames, proactive insights, indexed files). On a
// user-initiated sign-out we DELETE all rows so a different account signing in
// on the same machine starts clean (privacy). Rows only, not schema (DELETE, not
// DROP), so the next session reuses the already-migrated tables.

export const USER_DATA_TABLES = [
  'caption_event',
  'local_conversation',
  'indexed_files',
  'local_kg_nodes',
  'local_kg_edges',
  'onboarding_kg_nodes',
  'onboarding_kg_edges',
  'app_usage',
  'rewind_frames',
  'insights',
  // --- Track 4: user-scoped tables added for Rewind/Conversations/capture ---
  // rewind_frames_fts is deliberately absent: its rows are derived from
  // rewind_frames via AFTER-DELETE triggers, so `DELETE FROM rewind_frames`
  // above already empties the FTS index. app_meta is also absent — it holds
  // app-level flags (clean-exit, launch-at-login migrated) that must survive
  // sign-out.
  'conversation_folders',
  'conversation_speaker_names',
  'live_notes',
  'rescue_segments',
  'rewind_embeddings',
  'file_index_meta'
] as const

// Minimal DB surface the wipe needs — satisfied by both better-sqlite3 (prod)
// and node:sqlite DatabaseSync (test).
export interface WipeableDb {
  exec(sql: string): void
  // The wipe runs each DELETE with no bound params, so a no-arg `run` keeps the
  // interface assignable from both better-sqlite3 and node:sqlite Statements
  // (whose own `run` accept optional/variadic params).
  prepare(sql: string): { run: () => unknown }
}

/** Clear every user-data table in one transaction. Rolls back on any failure so a
 *  partial wipe can't leave one account's data behind while dropping another's. */
export function wipeUserDataOn(d: WipeableDb): void {
  d.exec('BEGIN')
  try {
    for (const table of USER_DATA_TABLES) d.prepare(`DELETE FROM ${table}`).run()
    d.exec('COMMIT')
  } catch (e) {
    d.exec('ROLLBACK')
    throw e
  }
}
