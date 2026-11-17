// The pre-cloud local AI-profile history table, kept only long enough to carry
// its newest text up to the backend once (see the salvage step in
// assistants/aiUserProfile/service.ts).
//
// Older builds generated the profile on this machine, committed it (and any user
// edit) to this table, and mirrored it to the backend with a fire-and-forget
// PATCH whose failure only logged. So on upgrade the table may hold the only copy
// of the latest text or of a user correction. It is therefore NOT dropped by a
// migration: the service drops it after the first authenticated read confirms the
// backend already has that text or has accepted it.
//
// Driver-agnostic (no better-sqlite3 import), like dbWipe.ts / dbMigrations.ts, so
// it is unit-tested against node:sqlite. db.ts wraps these with its live handle.
//
// The table is user data: dbWipe.ts still clears its rows on sign-out (so no other
// account can ever upload them), and it is not in the chat agent's read-only SQL
// allowlist (assistants/core/readOnlySql.ts).

export const LEGACY_PROFILE_TABLE = 'ai_user_profiles'
const LEGACY_PROFILE_INDEX = 'idx_ai_user_profiles_generated_at'

/** The newest legacy row. `backendSynced` is the old mirror-PATCH marker: set when
 *  a generation's PATCH succeeded. An edit never cleared it, so a failed edit sync
 *  still reads as synced; the caller also compares text and timestamps. */
export type LegacyProfileRow = {
  profileText: string
  /** Epoch ms (the old INTEGER column). */
  generatedAt: number
  backendSynced: boolean
}

export type LegacyProfileDb = {
  exec(sql: string): unknown
  prepare(sql: string): { get: (...params: never[]) => unknown }
}

function tableExists(d: LegacyProfileDb): boolean {
  return Boolean(
    d
      .prepare(
        `SELECT 1 AS x FROM sqlite_master WHERE type = 'table' AND name = '${LEGACY_PROFILE_TABLE}'`
      )
      .get()
  )
}

/** The newest row (old ordering: generated_at, then id), or null when the table
 *  is absent or empty. */
export function readNewestLegacyProfile(d: LegacyProfileDb): LegacyProfileRow | null {
  if (!tableExists(d)) return null
  const row = d
    .prepare(
      `SELECT profile_text AS profileText, generated_at AS generatedAt, backend_synced AS backendSynced
         FROM ${LEGACY_PROFILE_TABLE} ORDER BY generated_at DESC, id DESC LIMIT 1`
    )
    .get() as { profileText: string; generatedAt: number; backendSynced: number } | undefined
  if (!row) return null
  return {
    profileText: row.profileText,
    generatedAt: Number(row.generatedAt),
    backendSynced: Number(row.backendSynced) !== 0
  }
}

/** Drop the table and its index. Idempotent. */
export function dropLegacyProfile(d: LegacyProfileDb): void {
  d.exec(`DROP INDEX IF EXISTS ${LEGACY_PROFILE_INDEX}`)
  d.exec(`DROP TABLE IF EXISTS ${LEGACY_PROFILE_TABLE}`)
}
