// Sign-out user-data wipe, kept driver-agnostic (no better-sqlite3 import) so it
// is unit-testable under plain-node vitest with node:sqlite — db.ts's native
// better-sqlite3 dep is built for Electron's ABI and can't load there. Same
// pattern as dbMigrations.ts.
//
// Every table in the local database holds user-scoped data (conversations +
// sync outbox, live captions, the local knowledge graph, onboarding brain-map,
// app-usage stats, rewind frames, proactive insights, indexed files). On a
// user-initiated sign-out we DELETE all rows so a different account signing in
// on the same machine starts clean (privacy). The legacy keyframe cleanup
// tables are intentionally excluded: they are install-scoped retry authority
// and are retired only after their physical image files unlink successfully (or
// return ENOENT). Rows only, not schema (DELETE, not DROP), are changed here.
//
// EXCEPTION -- rewind_frames (INV-AUTH-1 owner boundary): the rewind index is the
// user's local screen history, and macOS implements sign-out as an owner
// TRANSITION that preserves it (per-owner RewindDatabase storage,
// RewindDatabase.retargetEffectiveOwner): the outgoing owner's store is
// retargeted away, never destroyed. The Windows port originally DELETEd the
// rows here, which silently destroyed years of history AND armed the orphan
// JPEG sweep against every frame file (rows gone -> sweep saw ~all files as
// unreferenced and unlinked them). So rewind frames are PARKED instead: the
// live rows move to rewind_frames_parked under the outgoing owner's uid (same
// transaction as the rest of the wipe), still invisible to any other account,
// and restoreRewindFramesOn moves them back when that owner signs in again.
// The physical JPEGs under rewind/ never move; rewindImagePathsBetween's
// keep-set (REWIND_IMAGE_PATHS_SQL below) covers parked rows so the sweep
// cannot touch them. Parking is not immortality: parked rows age out through
// the same retention cutoff as live frames (pruneParkedRewindFramesOn below),
// so an owner who never signs back in still stops consuming disk eventually.
// Derived embeddings stay a plain wipe: they are
// recomputable from the restored rows (OCR text lives in the row; the
// embedding backfill re-embeds any frame whose vector is missing).

export const USER_DATA_TABLES = [
  'caption_event',
  'local_conversation',
  'indexed_files',
  'local_kg_nodes',
  'local_kg_edges',
  'onboarding_kg_nodes',
  'onboarding_kg_edges',
  'app_usage',
  'insights',
  // --- Track 4: user-scoped tables added for Rewind/Conversations/capture ---
  // rewind_frames_fts is deliberately absent: its rows are derived from
  // rewind_frames via AFTER-DELETE triggers, so `DELETE FROM rewind_frames`
  // above already empties the FTS index. app_meta is also absent — it holds
  // app-level flags (clean-exit, launch-at-login migrated) that must survive
  // sign-out.
  'conversation_folders',
  'conversation_speaker_names',
  // PR8: LiveNotes — both the notes and their session anchor are user content.
  'transcription_sessions',
  'live_notes',
  'rescue_segments',
  'rewind_embeddings',
  // The vectors themselves — derived from the user's screen content, so they must
  // go on an account switch just like the frame->content mapping above.
  'rewind_embedding_vectors',
  'file_index_meta',
  // Track 2's voice-turn outbox holds queued user voice-message data; it must be
  // cleared on account switch (drift-guard caught it missing — see dbWipe.test.ts).
  'voice_turn_outbox',
  // --- Track 3 (proactive) ---
  'ai_user_profiles',
  'focus_sessions',
  // Screen-extracted memories — user data derived from the user's screen; must be
  // cleared on account switch just like focus_sessions / the rewind frames above.
  'memories',
  // Local task storage (Track 3). Both are user content; their FTS shadow tables
  // (action_items_fts / staged_tasks_fts) are derived via triggers and emptied by
  // these DELETEs, so they are deliberately absent (like rewind_frames_fts). DDL
  // lives in taskStore.ts, which dbWipe.test.ts's drift guard also scans.
  'action_items',
  'staged_tasks',
  'jit_trigger_mirror',
  'jit_fact_mirror',
  'jit_history_mirror',
  'jit_playbook_mirror',
  'jit_alias_mirror',
  'jit_snapshot_receipt',
  'jit_ledger_snapshot_receipt',
  'jit_wakeup_receipt',
  'jit_ambient_context_state',
  'jit_feedback_outbox',
  'jit_proactivity_reservation_receipt',
  'jit_temporary_frame'
] as const

// Minimal DB surface the wipe needs — satisfied by both better-sqlite3 (prod)
// and node:sqlite DatabaseSync (test).
//
// The param union is deliberately narrow (SQL bind values, not `unknown`): the
// bound params are checked against BOTH drivers' statement types; too wide
// rejects node:sqlite (SQLInputValue), and null/undefined rejects better-sqlite3
// (whose inferred bind type is `{}`). The wipe only ever binds uid strings.
export type SqlBindParam = string | number | bigint

export interface WipeableDb {
  exec(sql: string): void
  // The wipe runs most DELETEs with no bound params, but the rewind park/restore
  // statements bind the owner uid. Method syntax keeps the members assignable
  // from both better-sqlite3 and node:sqlite Statements (whose own `run`/`get`
  // accept optional/variadic params with driver-specific bind unions).
  prepare(sql: string): {
    run(...params: SqlBindParam[]): unknown
    get(...params: SqlBindParam[]): unknown
    // pruneParkedRewindFramesOn reads the doomed rows before deleting them;
    // better-sqlite3 and node:sqlite statements both provide `all`.
    all(...params: SqlBindParam[]): unknown
  }
}

function tableExists(d: WipeableDb, table: string): boolean {
  // Callers pass table names from the compile-time USER_DATA_TABLES allowlist or
  // the rewind_parked literal, so interpolating is safe and keeps this compatible
  // with both SQLite drivers.
  return Boolean(
    d.prepare(`SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '${table}'`).get()
  )
}

/**
 * Keep-set for the orphaned-JPEG sweep and the disk rebuild: image paths the
 * database still owns in [fromMs, toMs): LIVE frames and PARKED rows alike.
 * Parked rows MUST be covered: after a sign-out parks the prior owner's index,
 * their JPEGs sit on disk with no live row, and a keep-set that ignored the
 * parked table would let the sweep delete the very files the park exists to
 * preserve. Parked coverage is bounded by retention in the row domain, not
 * here: pruneParkedRewindFramesOn retires aged parked rows (and their files)
 * at the same cutoff as live frames. Lives here (not db.ts) so the statement
 * is importable (and executable against node:sqlite) by dbWipe.test.ts, the
 * same one-statement source-of-truth pattern as rewindEmbeddingSql.ts.
 */
export const REWIND_IMAGE_PATHS_SQL = `SELECT image_path FROM rewind_frames WHERE ts >= ? AND ts < ?
    UNION
    SELECT image_path FROM rewind_frames_parked WHERE ts >= ? AND ts < ?`

/** Options for {@link wipeUserDataOn}. */
export interface WipeUserDataOptions {
  /**
   * Uid of the account being signed out. When supplied, the owner's rewind
   * frame rows are PARKED (moved to rewind_frames_parked, still bound to this
   * uid) instead of deleted; see the INV-AUTH-1 note at the top of this file.
   * When omitted or empty, rewind frames are deleted like every other
   * user-scoped table: without an owner to park for, leaving another account's
   * screen history visible would be the worse failure, so the fallback is the
   * old destructive wipe (fail-closed toward privacy).
   */
  rewindOwnerUid?: string | null
}

/** Move the live rewind frame rows into the owner's parked slot. The caller has
 *  already verified the parked table exists and runs this inside the wipe
 *  transaction, so the park is all-or-nothing with the rest of the teardown. */
function parkRewindFramesOn(d: WipeableDb, ownerUid: string): void {
  d.prepare(
    `INSERT OR IGNORE INTO rewind_frames_parked
         (owner_uid, ts, app, window_title, process_name, ocr_text, ocr_lines_json,
          image_path, width, height, indexed)
       SELECT ?, ts, app, window_title, process_name, ocr_text, ocr_lines_json,
          image_path, width, height, indexed
         FROM rewind_frames`
  ).run(ownerUid)
  // Fires the AFTER-DELETE FTS triggers in production: a parked owner's frames
  // leave the live full-text index until they are restored.
  d.prepare('DELETE FROM rewind_frames').run()
}

/**
 * Move a returning owner's parked rewind frames back into the live index and
 * clear their parked slot. One transaction: a crash mid-restore rolls back and
 * the next sign-in retries. In production the AFTER-INSERT FTS triggers rebuild
 * the full-text entries and the embedding backfill re-embeds rows whose vectors
 * were wiped at park time. Returns the number of rows restored.
 */
export function restoreRewindFramesOn(d: WipeableDb, ownerUid: string): number {
  if (!ownerUid) return 0
  if (!tableExists(d, 'rewind_frames_parked')) return 0
  d.exec('BEGIN')
  try {
    d.prepare(
      `INSERT INTO rewind_frames
           (ts, app, window_title, process_name, ocr_text, ocr_lines_json,
            image_path, width, height, indexed)
         SELECT ts, app, window_title, process_name, ocr_text, ocr_lines_json,
            image_path, width, height, indexed
           FROM rewind_frames_parked WHERE owner_uid = ?`
    ).run(ownerUid)
    const r = d.prepare('DELETE FROM rewind_frames_parked WHERE owner_uid = ?').run(ownerUid) as {
      changes?: number | bigint
    }
    d.exec('COMMIT')
    const changes = r?.changes
    return typeof changes === 'bigint' ? Number(changes) : (changes ?? 0)
  } catch (e) {
    d.exec('ROLLBACK')
    throw e
  }
}

/**
 * Retention for PARKED rewind rows, sharing the live table's cutoff: parking
 * preserves history across owner transitions, but it is not exempt from the
 * user's retention window. Without this prune, a parked owner who never signs
 * back in would keep their rows forever -- and, via REWIND_IMAGE_PATHS_SQL,
 * their JPEGs with them. Runs regardless of which owner the rows belong to:
 * retention is per-frame age, not per-owner presence. One transaction, and it
 * returns the doomed rows BEFORE deleting them so the caller can unlink the
 * image files after the rows are gone (same ordering as
 * db.ts deleteRewindFramesOlderThan: rows retire first, then files -- an
 * unlink that fails leaves a no-row file past the cutoff, which the orphan
 * sweep already treats as deletable-on-sight). No embedding cleanup needed:
 * the park itself wipes rewind_embeddings in the same transaction, so nothing
 * can reference a parked frame. Lives here (not db.ts) so it is executable
 * against node:sqlite in dbWipe.test.ts. Strict `<`: a row exactly AT the
 * cutoff is still inside retention, mirroring the live table.
 */
export function pruneParkedRewindFramesOn(
  d: WipeableDb,
  cutoffTs: number
): Array<{ ts: number; imagePath: string }> {
  if (!tableExists(d, 'rewind_frames_parked')) return []
  d.exec('BEGIN')
  try {
    const doomed = d
      .prepare('SELECT ts, image_path AS imagePath FROM rewind_frames_parked WHERE ts < ?')
      .all(cutoffTs) as Array<{ ts: number; imagePath: string }>
    d.prepare('DELETE FROM rewind_frames_parked WHERE ts < ?').run(cutoffTs)
    d.exec('COMMIT')
    return doomed
  } catch (e) {
    d.exec('ROLLBACK')
    throw e
  }
}

/** Clear every user-data table in one transaction. Rolls back on any failure so a
 *  partial wipe can't leave one account's data behind while dropping another's.
 *  The rewind frame index is parked for the outgoing owner when
 *  {@link WipeUserDataOptions.rewindOwnerUid} is supplied (see the INV-AUTH-1
 *  note at the top of this file); otherwise it is deleted with the rest. */
export function wipeUserDataOn(d: WipeableDb, options: WipeUserDataOptions = {}): void {
  d.exec('BEGIN')
  try {
    for (const table of USER_DATA_TABLES) {
      // Legacy data bootstrap is additive and deliberately fail-open for the
      // app. If it failed before creating every optional mirror table, account
      // switching must still erase all legacy user data atomically.
      if (table.startsWith('jit_') && !tableExists(d, table)) continue
      d.prepare(`DELETE FROM ${table}`).run()
    }
    if (options.rewindOwnerUid && tableExists(d, 'rewind_frames_parked')) {
      parkRewindFramesOn(d, options.rewindOwnerUid)
    } else if (tableExists(d, 'rewind_frames')) {
      // Fail-closed: no owner to park for, or a schema so old it predates the
      // parked table, means the rows must not survive into another account's
      // session -- fall back to the destructive wipe.
      d.prepare('DELETE FROM rewind_frames').run()
    }
    d.exec('COMMIT')
  } catch (e) {
    d.exec('ROLLBACK')
    throw e
  }
}
