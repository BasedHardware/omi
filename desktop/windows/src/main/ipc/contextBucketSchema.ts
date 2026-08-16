/**
 * Context-bucket schema — the durable substrate of the Context Director.
 * Windows mirror of macOS ContextBucketSchema.swift (tables, columns, CHECKs,
 * and all indexes, including the raw COALESCE unique subject index).
 *
 * Driver-agnostic like insightStore/taskStore: DDL is exported and exec'd by
 * db.ts's bootstrap; tests run the identical SQL on node:sqlite.
 *
 * Windows adaptations, deliberate and documented:
 * - Timestamps are epoch-milliseconds INTEGER (repo convention), not DATETIME.
 * - mac's `lastScreenshotID -> screenshots(id)` becomes `lastFrameId` with no
 *   FK: frames live in rewind_frames and are retention-deleted by the rewind
 *   subsystem; evidence refs keep the mac `screenshot:<id>` string format.
 * - mac's `bundleID` column is `processName` (the Windows process identity).
 * - The legacy UserDefaults import inside mac's first migration has no Windows
 *   analog (no pre-database binding storage ever existed here); the
 *   migration-meta table stays for provenance parity.
 */

/** Canonical table set (mac: ContextBucketSchema.tableNames). Every one of
 *  these must also be listed in dbWipe.ts's USER_DATA_TABLES. */
export const CONTEXT_BUCKET_TABLE_NAMES = [
  'context_visits',
  'context_buckets',
  'bucket_versions',
  'bucket_entries',
  'bucket_facts',
  'bucket_workstreams',
  'proactive_candidates',
  'subject_bindings',
  'proactive_deliveries',
  'context_bucket_migration_meta'
] as const

export const CONTEXT_BUCKET_SCHEMA = `
  CREATE TABLE IF NOT EXISTS context_bucket_migration_meta (
    migrationName TEXT NOT NULL PRIMARY KEY,
    ownerID       TEXT NOT NULL,
    sourceOwnerID TEXT,
    importedCount INTEGER NOT NULL,
    createdAt     INTEGER NOT NULL
  );

  CREATE TABLE IF NOT EXISTS context_buckets (
    id               TEXT NOT NULL PRIMARY KEY,
    subjectKind      TEXT NOT NULL,
    subjectID        TEXT NOT NULL,
    workstreamID     TEXT,
    displayLabel     TEXT,
    notifyWorthiness REAL NOT NULL DEFAULT 0,
    visitCount       INTEGER NOT NULL DEFAULT 0,
    lastVisitedAt    INTEGER,
    createdAt        INTEGER NOT NULL,
    updatedAt        INTEGER NOT NULL,
    UNIQUE (subjectKind, subjectID, workstreamID)
  );

  CREATE TABLE IF NOT EXISTS context_visits (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    contextGeneration    INTEGER NOT NULL,
    poolEpoch            INTEGER NOT NULL,
    bucketID             TEXT REFERENCES context_buckets(id) ON DELETE SET NULL,
    appName              TEXT NOT NULL,
    rawContextKey        TEXT NOT NULL,
    normalizedContextKey TEXT NOT NULL,
    referenceHash        TEXT NOT NULL,
    startedAt            INTEGER NOT NULL,
    settledAt            INTEGER,
    endedAt              INTEGER,
    outcome              TEXT NOT NULL DEFAULT 'active',
    exitReason           TEXT,
    lastFrameId          INTEGER,
    createdAt            INTEGER NOT NULL,
    updatedAt            INTEGER NOT NULL,
    primaryHandleType    TEXT,
    primaryHandleValue   TEXT,
    handlesJson          TEXT,
    processName          TEXT,
    CHECK (outcome IN ('active', 'completed', 'interrupted', 'discarded'))
  );

  CREATE TABLE IF NOT EXISTS bucket_versions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bucketID            TEXT NOT NULL REFERENCES context_buckets(id) ON DELETE CASCADE,
    version             INTEGER NOT NULL,
    header              TEXT NOT NULL,
    frozenRankedSegment BLOB NOT NULL,
    rankedTokenCount    INTEGER NOT NULL DEFAULT 0,
    createdAt           INTEGER NOT NULL,
    UNIQUE (bucketID, version)
  );

  CREATE TABLE IF NOT EXISTS bucket_entries (
    id                   TEXT NOT NULL PRIMARY KEY,
    bucketID             TEXT NOT NULL REFERENCES context_buckets(id) ON DELETE CASCADE,
    visitID              INTEGER NOT NULL REFERENCES context_visits(id) ON DELETE CASCADE,
    bucketVersionID      INTEGER REFERENCES bucket_versions(id) ON DELETE SET NULL,
    appName              TEXT NOT NULL,
    rawContextKey        TEXT NOT NULL,
    normalizedContextKey TEXT NOT NULL,
    narrative            TEXT NOT NULL,
    evidenceRefsJson     TEXT NOT NULL,
    tokenCount           INTEGER NOT NULL,
    isCompacted          INTEGER NOT NULL DEFAULT 0,
    createdAt            INTEGER NOT NULL
  );

  CREATE TABLE IF NOT EXISTS bucket_facts (
    id               TEXT NOT NULL PRIMARY KEY,
    bucketID         TEXT NOT NULL REFERENCES context_buckets(id) ON DELETE CASCADE,
    entryID          TEXT NOT NULL REFERENCES bucket_entries(id) ON DELETE CASCADE,
    appName          TEXT NOT NULL,
    statement        TEXT NOT NULL,
    identifiersJson  TEXT NOT NULL,
    evidenceText     TEXT NOT NULL,
    evidenceRefsJson TEXT NOT NULL,
    validityState    TEXT NOT NULL DEFAULT 'proposed',
    dispositionState TEXT NOT NULL DEFAULT 'none',
    confidence       REAL NOT NULL,
    notifyWorthiness REAL NOT NULL DEFAULT 0,
    expiresAt        INTEGER,
    createdAt        INTEGER NOT NULL,
    updatedAt        INTEGER NOT NULL,
    workstreamTag    TEXT,
    CHECK (validityState IN ('proposed', 'validated', 'rejected', 'superseded', 'expired', 'needs_review')),
    CHECK (dispositionState IN ('none', 'candidate_pending', 'task_created', 'update_proposed'))
  );

  CREATE TABLE IF NOT EXISTS subject_bindings (
    referenceHash   TEXT NOT NULL PRIMARY KEY,
    bucketID        TEXT REFERENCES context_buckets(id) ON DELETE SET NULL,
    subjectKind     TEXT NOT NULL,
    subjectID       TEXT NOT NULL,
    workstreamID    TEXT,
    confidence      REAL NOT NULL,
    source          TEXT NOT NULL,
    occurrenceCount INTEGER NOT NULL DEFAULT 1,
    createdAt       INTEGER NOT NULL,
    updatedAt       INTEGER NOT NULL
  );

  CREATE TABLE IF NOT EXISTS proactive_deliveries (
    id               TEXT NOT NULL PRIMARY KEY,
    visitID          INTEGER REFERENCES context_visits(id) ON DELETE SET NULL,
    bucketID         TEXT REFERENCES context_buckets(id) ON DELETE SET NULL,
    bucketVersionID  INTEGER REFERENCES bucket_versions(id) ON DELETE SET NULL,
    decisionType     TEXT NOT NULL,
    lifecycleState   TEXT NOT NULL,
    provenanceJson   TEXT NOT NULL,
    message          TEXT,
    attemptedAt      INTEGER NOT NULL,
    modelCompletedAt INTEGER,
    policyApprovedAt INTEGER,
    deliveredAt      INTEGER,
    expiresAt        INTEGER NOT NULL,
    createdAt        INTEGER NOT NULL,
    CHECK (lifecycleState IN ('attempted', 'model_completed', 'policy_approved', 'delivered', 'suppressed', 'failed'))
  );

  CREATE TABLE IF NOT EXISTS bucket_workstreams (
    id         TEXT NOT NULL PRIMARY KEY,
    bucketID   TEXT NOT NULL REFERENCES context_buckets(id) ON DELETE CASCADE,
    tag        TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'reconciler',
    assignedAt INTEGER NOT NULL,
    UNIQUE (bucketID, tag)
  );

  CREATE TABLE IF NOT EXISTS proactive_candidates (
    id                   TEXT NOT NULL PRIMARY KEY,
    bucketID             TEXT NOT NULL REFERENCES context_buckets(id) ON DELETE CASCADE,
    workstreamTag        TEXT,
    message              TEXT NOT NULL,
    groundingFactIDsJson TEXT NOT NULL,
    triggerNote          TEXT NOT NULL,
    state                TEXT NOT NULL DEFAULT 'armed',
    createdAt            INTEGER NOT NULL,
    expiresAt            INTEGER NOT NULL,
    consumedAt           INTEGER,
    CHECK (state IN ('armed','consumed','expired'))
  );

  CREATE INDEX IF NOT EXISTS idx_context_visits_context ON context_visits(normalizedContextKey);
  CREATE UNIQUE INDEX IF NOT EXISTS idx_context_buckets_subject
    ON context_buckets(subjectKind, subjectID, COALESCE(workstreamID, ''));
  CREATE INDEX IF NOT EXISTS idx_context_visits_open ON context_visits(outcome, endedAt);
  CREATE INDEX IF NOT EXISTS idx_bucket_versions_latest ON bucket_versions(bucketID, version);
  CREATE INDEX IF NOT EXISTS idx_bucket_entries_tail ON bucket_entries(bucketID, createdAt);
  CREATE INDEX IF NOT EXISTS idx_bucket_entries_app ON bucket_entries(appName);
  CREATE INDEX IF NOT EXISTS idx_bucket_facts_valid ON bucket_facts(bucketID, validityState);
  CREATE INDEX IF NOT EXISTS idx_bucket_facts_app ON bucket_facts(appName);
  CREATE INDEX IF NOT EXISTS idx_subject_bindings_bucket ON subject_bindings(bucketID);
  CREATE INDEX IF NOT EXISTS idx_proactive_deliveries_budget ON proactive_deliveries(deliveredAt);
  CREATE INDEX IF NOT EXISTS idx_proactive_deliveries_expiry ON proactive_deliveries(expiresAt);
  CREATE UNIQUE INDEX IF NOT EXISTS idx_proactive_deliveries_dedup ON proactive_deliveries(visitID, bucketVersionID);
  CREATE INDEX IF NOT EXISTS idx_context_visits_handle ON context_visits(primaryHandleType, primaryHandleValue);
  CREATE INDEX IF NOT EXISTS idx_bucket_facts_workstream ON bucket_facts(workstreamTag, createdAt);
  CREATE INDEX IF NOT EXISTS idx_bucket_workstreams_tag ON bucket_workstreams(tag, assignedAt);
  CREATE INDEX IF NOT EXISTS idx_proactive_candidates_lookup ON proactive_candidates(bucketID, state, expiresAt);
  CREATE INDEX IF NOT EXISTS idx_proactive_candidates_workstream ON proactive_candidates(workstreamTag, state, expiresAt);
  CREATE INDEX IF NOT EXISTS idx_proactive_candidates_retention ON proactive_candidates(state, expiresAt);
`
