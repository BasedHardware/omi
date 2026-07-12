import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { DatabaseSync, type SQLInputValue, type SQLOutputValue } from "node:sqlite";
import type {
  AdapterBinding,
  AgentArtifact,
  AgentGrant,
  DesktopArtifactDelivery,
  DesktopAttentionOverride,
  DesktopContextAccessLog,
  DesktopContextPacket,
  DesktopCoordinatorDispatch,
  DesktopMemoryCandidate,
  DesktopTaskCandidate,
  AgentEvent,
  AgentIdKind,
  AgentRun,
  AgentSession,
  AgentStore,
  NewAdapterBinding,
  NewAgentEvent,
  NewAgentArtifact,
  NewAgentGrant,
  ConversationTurn,
  NewAgentRun,
  NewAgentSession,
  NewConversationTurn,
  NewSurfaceConversation,
  SurfaceConversation,
  NewDesktopArtifactDelivery,
  NewDesktopAttentionOverride,
  NewDesktopContextAccessLog,
  NewDesktopContextPacket,
  NewDesktopCoordinatorDispatch,
  NewDesktopMemoryCandidate,
  NewDesktopTaskCandidate,
  NewRunAttempt,
  RunAttempt,
  StartupReconciliationResult,
} from "./types.js";
import { providerBoundaryForAdapter } from "./execution-policy.js";

const DATABASE_FILENAME = "omi-agentd.sqlite3";
const PHASE_1_MIGRATION_VERSION = 1;
const ARTIFACT_LIFECYCLE_MIGRATION_VERSION = 2;
const DESKTOP_CONTEXT_PACKETS_MIGRATION_VERSION = 3;
const DESKTOP_DISPATCHES_MIGRATION_VERSION = 4;
const DESKTOP_ARTIFACT_DELIVERIES_MIGRATION_VERSION = 5;
const DESKTOP_CANDIDATES_MIGRATION_VERSION = 6;
const DESKTOP_CONTEXT_ACCESS_LOG_MIGRATION_VERSION = 7;
const DESKTOP_ATTENTION_OVERRIDES_MIGRATION_VERSION = 8;
const ACTIVE_ATTEMPT_AUTHORITY_MIGRATION_VERSION = 9;
const SURFACE_CONVERSATIONS_MIGRATION_VERSION = 10;
const CONVERSATION_TURNS_MIGRATION_VERSION = 11;
const BINDING_TURN_DELIVERY_MIGRATION_VERSION = 12;
const WORKSTREAM_CONTINUITY_MIGRATION_VERSION = 13;
const SESSION_EXECUTION_POLICY_MIGRATION_VERSION = 14;
const CONVERSATION_JOURNAL_MIGRATION_VERSION = 15;
const SESSION_EXECUTION_PROFILE_MIGRATION_VERSION = 16;
const CONVERSATION_JOURNAL_SEQUENCE_MIGRATION_VERSION = 17;
const TOOL_INVOCATION_LEDGER_MIGRATION_VERSION = 18;
const KERNEL_CONTEXT_AUTHORITY_MIGRATION_VERSION = 19;
const JOURNAL_GENERATION_BASE_MIGRATION_VERSION = 20;
const OWNER_CONTEXT_SNAPSHOT_MIGRATION_VERSION = 21;
const BACKEND_CONVERSATION_DELETE_OUTBOX_MIGRATION_VERSION = 22;
const BACKEND_RECONCILE_STATE_MIGRATION_VERSION = 23;
const CLEARED_BACKEND_TURN_CLAIMS_MIGRATION_VERSION = 24;
const CONTEXT_SOURCE_SURFACE_SCOPE_MIGRATION_VERSION = 25;
const BACKEND_RECONCILE_CURSOR_MIGRATION_VERSION = 26;

const ACTIVE_ATTEMPT_STATUSES = ["queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling"] as const;
const TERMINAL_ATTEMPT_STATUSES = ["succeeded", "failed", "cancelled", "timed_out", "orphaned"] as const;

type DatabaseFactory = new (path: string) => Pick<DatabaseSync, "exec" | "prepare" | "close" | "isTransaction">;
type Row = Record<string, SQLOutputValue>;

export interface SqliteAgentStoreOptions {
  stateDir?: string;
  databasePath?: string;
  reconcileOnOpen?: boolean;
  nowMs?: () => number;
  databaseFactory?: DatabaseFactory;
}

export interface NodeSqliteProbeOptions {
  databaseFactory?: DatabaseFactory;
}

const phase1SchemaSql = `
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  agent_definition_id TEXT NOT NULL DEFAULT 'omi.generalist@1',
  title TEXT,
  status TEXT NOT NULL CHECK (status IN ('open', 'archived', 'closed')),
  surface_kind TEXT NOT NULL,
  external_ref_kind TEXT,
  external_ref_id TEXT,
  -- TODO(desktop-agent-platonic-gap-closure G6): drop legacy_client_scope + legacy_session_key two desktop releases after platonic ships.
  legacy_client_scope TEXT,
  legacy_session_key TEXT,
  default_adapter_id TEXT NOT NULL,
  default_cwd TEXT,
  model_profile TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  last_activity_at_ms INTEGER NOT NULL,
  CHECK ((external_ref_kind IS NULL) = (external_ref_id IS NULL)),
  CHECK ((legacy_client_scope IS NULL) = (legacy_session_key IS NULL))
) STRICT;

CREATE UNIQUE INDEX sessions_external_ref_uq
  ON sessions(owner_id, external_ref_kind, external_ref_id)
  WHERE external_ref_kind IS NOT NULL;

CREATE UNIQUE INDEX sessions_legacy_alias_uq
  ON sessions(owner_id, legacy_client_scope, legacy_session_key)
  WHERE legacy_client_scope IS NOT NULL;

CREATE INDEX sessions_recent_idx
  ON sessions(owner_id, last_activity_at_ms DESC);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  parent_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
  client_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  idempotency_key TEXT,
  status TEXT NOT NULL CHECK (status IN (
    'queued', 'starting', 'running', 'waiting_input', 'waiting_approval',
    'cancelling', 'succeeded', 'failed', 'cancelled', 'timed_out', 'orphaned'
  )),
  mode TEXT NOT NULL CHECK (mode IN ('ask', 'act')),
  input_json TEXT NOT NULL CHECK (json_valid(input_json)),
  system_prompt_hash TEXT,
  model_profile TEXT,
  requested_model_id TEXT,
  cwd TEXT,
  final_text TEXT,
  result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
  error_code TEXT,
  error_message TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cache_read_tokens INTEGER,
  cache_write_tokens INTEGER,
  cost_usd REAL,
  created_at_ms INTEGER NOT NULL,
  started_at_ms INTEGER,
  completed_at_ms INTEGER,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(client_id, request_id)
) STRICT;

CREATE UNIQUE INDEX runs_idempotency_uq
  ON runs(session_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX runs_session_recent_idx
  ON runs(session_id, created_at_ms DESC);

CREATE INDEX runs_status_idx
  ON runs(status, created_at_ms);

CREATE TABLE adapter_bindings (
  binding_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  adapter_id TEXT NOT NULL,
  binding_generation INTEGER NOT NULL CHECK (binding_generation > 0),
  adapter_native_session_id TEXT,
  adapter_instance_id TEXT,
  resume_fidelity TEXT NOT NULL CHECK (resume_fidelity IN ('native', 'reconstructed', 'none')),
  status TEXT NOT NULL CHECK (status IN ('active', 'stale', 'invalid', 'closed')),
  cwd TEXT,
  model_id TEXT,
  system_prompt_hash TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  last_used_at_ms INTEGER,
  invalidated_at_ms INTEGER,
  UNIQUE(session_id, adapter_id, binding_generation)
) STRICT;

CREATE UNIQUE INDEX adapter_bindings_one_active_uq
  ON adapter_bindings(session_id, adapter_id)
  WHERE status = 'active';

CREATE UNIQUE INDEX adapter_bindings_native_uq
  ON adapter_bindings(adapter_id, adapter_native_session_id)
  WHERE adapter_native_session_id IS NOT NULL AND status != 'closed';

CREATE INDEX adapter_bindings_session_idx
  ON adapter_bindings(session_id, adapter_id, binding_generation DESC);

CREATE TABLE run_attempts (
  attempt_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
  status TEXT NOT NULL CHECK (status IN (
    'queued', 'starting', 'running', 'waiting_input', 'waiting_approval',
    'cancelling', 'succeeded', 'failed', 'cancelled', 'timed_out', 'orphaned'
  )),
  adapter_id TEXT NOT NULL,
  adapter_instance_id TEXT NOT NULL,
  runtime_node_id TEXT NOT NULL DEFAULT 'desktop-local',
  binding_id TEXT REFERENCES adapter_bindings(binding_id) ON DELETE SET NULL,
  adapter_native_run_id TEXT,
  resume_from_attempt_id TEXT REFERENCES run_attempts(attempt_id) ON DELETE SET NULL,
  checkpoint_artifact_id TEXT,
  retry_reason TEXT,
  retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0, 1)),
  cancellation_requested_at_ms INTEGER,
  cancellation_dispatched_at_ms INTEGER,
  cancellation_acknowledged_at_ms INTEGER,
  started_at_ms INTEGER,
  completed_at_ms INTEGER,
  error_code TEXT,
  error_message TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
  created_at_ms INTEGER NOT NULL,
  updated_at_ms INTEGER NOT NULL,
  UNIQUE(run_id, attempt_no)
) STRICT;

CREATE INDEX run_attempts_run_idx
  ON run_attempts(run_id, attempt_no DESC);

CREATE INDEX run_attempts_active_idx
  ON run_attempts(status, created_at_ms);

CREATE UNIQUE INDEX run_attempts_one_active_per_run_uq
  ON run_attempts(run_id)
  WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling');

CREATE TABLE events (
  event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
  attempt_id TEXT REFERENCES run_attempts(attempt_id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  retention_class TEXT NOT NULL DEFAULT 'core' CHECK (retention_class IN ('core', 'transient')),
  visibility TEXT NOT NULL DEFAULT 'ui' CHECK (visibility IN ('ui', 'internal')),
  payload_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json)),
  created_at_ms INTEGER NOT NULL
) STRICT;

CREATE INDEX events_session_cursor_idx
  ON events(session_id, event_seq);

CREATE INDEX events_run_cursor_idx
  ON events(run_id, event_seq)
  WHERE run_id IS NOT NULL;

CREATE INDEX events_attempt_cursor_idx
  ON events(attempt_id, event_seq)
  WHERE attempt_id IS NOT NULL;

CREATE TABLE artifacts (
  artifact_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
  attempt_id TEXT REFERENCES run_attempts(attempt_id) ON DELETE SET NULL,
  kind TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('input', 'result', 'checkpoint', 'tool_output', 'log', 'other')),
  uri TEXT NOT NULL,
  display_name TEXT,
  mime_type TEXT,
  content_hash TEXT,
  size_bytes INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
  created_at_ms INTEGER NOT NULL
) STRICT;

CREATE INDEX artifacts_run_idx
  ON artifacts(run_id, created_at_ms)
  WHERE run_id IS NOT NULL;

CREATE TABLE delegations (
  delegation_id TEXT PRIMARY KEY,
  parent_session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  parent_run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  child_session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  child_run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  mode TEXT NOT NULL CHECK (mode IN ('call', 'spawn', 'continue')),
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
  objective TEXT NOT NULL,
  request_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(request_json)),
  result_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
  created_at_ms INTEGER NOT NULL,
  completed_at_ms INTEGER,
  UNIQUE(child_run_id)
) STRICT;

CREATE INDEX delegations_parent_idx
  ON delegations(parent_run_id, created_at_ms);

CREATE TABLE grants (
  grant_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
  capability TEXT NOT NULL,
  operation TEXT NOT NULL,
  resource_pattern TEXT NOT NULL,
  effect TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
  -- TODO(desktop-agent-platonic-gap-closure G6): drop legacy_default from CHECK after ship+2 releases post-platonic.
  source TEXT NOT NULL CHECK (source IN ('legacy_default', 'policy', 'user', 'system')),
  constraints_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(constraints_json)),
  created_at_ms INTEGER NOT NULL,
  expires_at_ms INTEGER,
  revoked_at_ms INTEGER
) STRICT;

CREATE INDEX grants_lookup_idx
  ON grants(session_id, run_id, capability, operation, created_at_ms DESC);
`;

export function generateAgentId(kind: AgentIdKind): string {
  const prefixByKind: Record<AgentIdKind, string> = {
    session: "ses",
    conversation: "conv",
    run: "run",
    attempt: "att",
    event: "evt",
    binding: "bind",
    artifact: "art",
    delegation: "del",
    grant: "grant",
    contextPacket: "ctx",
    dispatch: "disp",
    artifactDelivery: "delivery",
    memoryCandidate: "memcand",
    taskCandidate: "taskcand",
    contextAccess: "access",
    turn: "turn",
  };
  return `${prefixByKind[kind]}_${randomUUID().replaceAll("-", "")}`;
}

export function databasePathForStateDir(stateDir: string): string {
  return join(stateDir, DATABASE_FILENAME);
}

export function probeNodeSqliteRuntime(options: NodeSqliteProbeOptions = {}): void {
  const Database = options.databaseFactory ?? DatabaseSync;
  let db: Pick<DatabaseSync, "exec" | "prepare" | "close" | "isTransaction"> | undefined;
  try {
    db = new Database(":memory:");
    applyConnectionPragmas(db);
    createSchemaMigrationsTable(db);
    runPhase1Migration(db, Date.now());
    runArtifactLifecycleMigration(db, Date.now());
    runDesktopContextPacketsMigration(db, Date.now());
    runDesktopDispatchesMigration(db, Date.now());
    runDesktopArtifactDeliveriesMigration(db, Date.now());
    runDesktopCandidatesMigration(db, Date.now());
    runDesktopContextAccessLogMigration(db, Date.now());
    runDesktopAttentionOverridesMigration(db, Date.now());
    runActiveAttemptAuthorityMigration(db, Date.now());
    runSurfaceConversationsMigration(db, Date.now());
    runConversationTurnsMigration(db, Date.now());
    runBindingTurnDeliveryMigration(db, Date.now());
    runWorkstreamContinuityMigration(db, Date.now());
    runSessionExecutionPolicyMigration(db, Date.now());
    runConversationJournalMigration(db, Date.now());
    runSessionExecutionProfileMigration(db, Date.now());
    runConversationJournalSequenceMigration(db, Date.now());
    runToolInvocationLedgerMigration(db, Date.now());
    runKernelContextAuthorityMigration(db, Date.now());
    runJournalGenerationBaseMigration(db, Date.now());
    runContextSourceSurfaceScopeMigration(db, Date.now());
    runTransaction(db, () => {
      db?.prepare("INSERT INTO sessions (session_id, owner_id, status, surface_kind, default_adapter_id, created_at_ms, updated_at_ms, last_activity_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)").run(
        "ses_probe",
        "owner_probe",
        "open",
        "probe",
        "acp",
        1,
        1,
        1,
      );
      db?.prepare("INSERT INTO events (event_id, session_id, type, payload_json, created_at_ms) VALUES (?, ?, ?, ?, ?)").run(
        "evt_probe",
        "ses_probe",
        "probe.ok",
        "{}",
        1,
      );
    });
  } catch (error) {
    throw new Error(`Bundled Node runtime does not support required node:sqlite AgentStore features: ${messageFrom(error)}`);
  } finally {
    db?.close();
  }
}

export class SqliteAgentStore implements AgentStore {
  private readonly db: DatabaseSync;
  private readonly nowMs: () => number;
  private transactionDepth = 0;

  constructor(options: SqliteAgentStoreOptions = {}) {
    const databasePath = options.databasePath ?? databasePathForStateDir(requiredStateDir(options.stateDir));
    mkdirSync(dirname(databasePath), { recursive: true });
    const Database = options.databaseFactory ?? DatabaseSync;
    this.db = new Database(databasePath) as DatabaseSync;
    this.nowMs = options.nowMs ?? Date.now;

    applyConnectionPragmas(this.db);
    this.migrate();
    if (options.reconcileOnOpen ?? true) {
      this.reconcileStartup();
    }
  }

  close(): void {
    this.db.close();
  }

  migrate(): void {
    createSchemaMigrationsTable(this.db);
    if (!this.hasMigration(PHASE_1_MIGRATION_VERSION)) {
      runPhase1Migration(this.db, this.nowMs());
    }
    if (!this.hasMigration(ARTIFACT_LIFECYCLE_MIGRATION_VERSION)) {
      runArtifactLifecycleMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(DESKTOP_CONTEXT_PACKETS_MIGRATION_VERSION)) {
      runDesktopContextPacketsMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(DESKTOP_DISPATCHES_MIGRATION_VERSION)) {
      runDesktopDispatchesMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(DESKTOP_ARTIFACT_DELIVERIES_MIGRATION_VERSION)) {
      runDesktopArtifactDeliveriesMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(DESKTOP_CANDIDATES_MIGRATION_VERSION)) {
      runDesktopCandidatesMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(DESKTOP_CONTEXT_ACCESS_LOG_MIGRATION_VERSION)) {
      runDesktopContextAccessLogMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(DESKTOP_ATTENTION_OVERRIDES_MIGRATION_VERSION)) {
      runDesktopAttentionOverridesMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(ACTIVE_ATTEMPT_AUTHORITY_MIGRATION_VERSION)) {
      runActiveAttemptAuthorityMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(SURFACE_CONVERSATIONS_MIGRATION_VERSION)) {
      runSurfaceConversationsMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(CONVERSATION_TURNS_MIGRATION_VERSION)) {
      runConversationTurnsMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(BINDING_TURN_DELIVERY_MIGRATION_VERSION)) {
      runBindingTurnDeliveryMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(WORKSTREAM_CONTINUITY_MIGRATION_VERSION)) {
      runWorkstreamContinuityMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(SESSION_EXECUTION_POLICY_MIGRATION_VERSION)) {
      runSessionExecutionPolicyMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(CONVERSATION_JOURNAL_MIGRATION_VERSION)) {
      runConversationJournalMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(SESSION_EXECUTION_PROFILE_MIGRATION_VERSION)) {
      runSessionExecutionProfileMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(CONVERSATION_JOURNAL_SEQUENCE_MIGRATION_VERSION)) {
      runConversationJournalSequenceMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(TOOL_INVOCATION_LEDGER_MIGRATION_VERSION)) {
      runToolInvocationLedgerMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(KERNEL_CONTEXT_AUTHORITY_MIGRATION_VERSION)) {
      runKernelContextAuthorityMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(JOURNAL_GENERATION_BASE_MIGRATION_VERSION)) {
      runJournalGenerationBaseMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(OWNER_CONTEXT_SNAPSHOT_MIGRATION_VERSION)) {
      runOwnerContextSnapshotMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(BACKEND_CONVERSATION_DELETE_OUTBOX_MIGRATION_VERSION)) {
      runBackendConversationDeleteOutboxMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(BACKEND_RECONCILE_STATE_MIGRATION_VERSION)) {
      runBackendReconcileStateMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(CLEARED_BACKEND_TURN_CLAIMS_MIGRATION_VERSION)) {
      runClearedBackendTurnClaimsMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(CONTEXT_SOURCE_SURFACE_SCOPE_MIGRATION_VERSION)) {
      runContextSourceSurfaceScopeMigration(this.db, this.nowMs());
    }
    if (!this.hasMigration(BACKEND_RECONCILE_CURSOR_MIGRATION_VERSION)) {
      runBackendReconcileCursorMigration(this.db, this.nowMs());
    }
  }

  withTransaction<T>(work: () => T): T {
    // Track nesting depth ourselves rather than trusting db.isTransaction: the
    // bundled agent runtime does not reliably report an open transaction, so a
    // nested call that issued its own BEGIN would fail with "cannot start a
    // transaction within a transaction" and break every agent operation.
    if (this.transactionDepth > 0) {
      this.transactionDepth += 1;
      try {
        return work();
      } finally {
        this.transactionDepth -= 1;
      }
    }
    this.transactionDepth += 1;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const result = work();
      this.db.exec("COMMIT");
      return result;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    } finally {
      this.transactionDepth -= 1;
    }
  }

  reconcileStartup(): StartupReconciliationResult {
    return this.withTransaction(() => {
      const now = this.nowMs();
      const repairedSessionProfileIds = repairMissingSessionExecutionProfiles(this.db, now);
      const repairedLegacyJournalTurnIds = repairDowngradeWindowJournalRows(this.db, now);
      const activeAttempts = this.allRows(
        `SELECT attempt_id, run_id FROM run_attempts WHERE status IN (${placeholders(ACTIVE_ATTEMPT_STATUSES.length)})`,
        [...ACTIVE_ATTEMPT_STATUSES],
      );
      const staleBindings = this.allRows(
        "SELECT binding_id, session_id FROM adapter_bindings WHERE status = ? AND resume_fidelity = ?",
        ["active", "none"],
      );
      const failedPreparedToolInvocationIds = this.allRows(
        "SELECT invocation_id FROM tool_invocation_ledger WHERE status = 'prepared'",
      ).map((row) => text(row.invocation_id));
      const outcomeUnknownToolInvocationIds = this.allRows(
        "SELECT invocation_id FROM tool_invocation_ledger WHERE status = 'dispatched'",
      ).map((row) => text(row.invocation_id));
      this.db.prepare(
        `UPDATE tool_invocation_ledger
         SET status = 'failed', error_code = 'daemon_restart_before_dispatch',
             completed_at_ms = ?, updated_at_ms = ?
         WHERE status = 'prepared'`,
      ).run(now, now);
      this.db.prepare(
        `UPDATE tool_invocation_ledger
         SET status = 'outcome_unknown', error_code = 'daemon_restart_after_dispatch',
             completed_at_ms = ?, updated_at_ms = ?
         WHERE status = 'dispatched'`,
      ).run(now, now);

      // The Phase 1 schema keeps run_attempts.adapter_instance_id NOT NULL;
      // an empty string is the cleared process-local worker marker after restart.
      this.db.prepare(`UPDATE run_attempts SET status = ?, adapter_instance_id = ?, completed_at_ms = COALESCE(completed_at_ms, ?), updated_at_ms = ? WHERE status IN (${placeholders(ACTIVE_ATTEMPT_STATUSES.length)})`).run(
        "orphaned",
        "",
        now,
        now,
        ...ACTIVE_ATTEMPT_STATUSES,
      );

      const orphanedRunIds = this.allRows(
        `SELECT r.run_id
         FROM runs r
         WHERE r.status IN (${placeholders(ACTIVE_ATTEMPT_STATUSES.length)})
           AND NOT EXISTS (
             SELECT 1 FROM run_attempts a
             WHERE a.run_id = r.run_id
               AND a.status NOT IN (${placeholders(TERMINAL_ATTEMPT_STATUSES.length)})
           )`,
        [...ACTIVE_ATTEMPT_STATUSES, ...TERMINAL_ATTEMPT_STATUSES],
      ).map((row) => text(row.run_id));

      for (const runId of orphanedRunIds) {
        this.db.prepare("UPDATE runs SET status = ?, completed_at_ms = COALESCE(completed_at_ms, ?), updated_at_ms = ? WHERE run_id = ?").run(
          "orphaned",
          now,
          now,
          runId,
        );
      }

      const clearedAttemptInstanceIds = Number(this.db.prepare("UPDATE run_attempts SET adapter_instance_id = ? WHERE adapter_instance_id != ?").run("", "").changes);
      const clearedBindingInstanceIds = Number(this.db.prepare("UPDATE adapter_bindings SET adapter_instance_id = NULL WHERE adapter_instance_id IS NOT NULL").run().changes);

      for (const binding of staleBindings) {
        this.db.prepare("UPDATE adapter_bindings SET status = ?, adapter_instance_id = NULL, invalidated_at_ms = COALESCE(invalidated_at_ms, ?), updated_at_ms = ? WHERE binding_id = ?").run(
          "stale",
          now,
          now,
          binding.binding_id,
        );
      }

      const eventIds: string[] = [];
      for (const attempt of activeAttempts) {
        eventIds.push(this.appendReconciliationEvent({
          sessionId: sessionIdForRun(this.db, text(attempt.run_id)),
          runId: text(attempt.run_id),
          attemptId: text(attempt.attempt_id),
          type: "attempt.orphaned",
          payload: { attemptId: attempt.attempt_id, reason: "daemon_startup_reconciliation" },
          createdAtMs: now,
        }));
      }
      for (const runId of orphanedRunIds) {
        eventIds.push(this.appendReconciliationEvent({
          sessionId: sessionIdForRun(this.db, runId),
          runId,
          attemptId: null,
          type: "run.orphaned",
          payload: { runId, reason: "daemon_startup_reconciliation" },
          createdAtMs: now,
        }));
      }
      for (const binding of staleBindings) {
        eventIds.push(this.appendReconciliationEvent({
          sessionId: text(binding.session_id),
          runId: null,
          attemptId: null,
          type: "binding.stale",
          payload: { bindingId: binding.binding_id, reason: "non_resumable_binding_after_restart" },
          createdAtMs: now,
        }));
      }

      const reconciledJournalTurns = reconcileNonterminalJournalRows(this.db, now);
      for (const repair of reconciledJournalTurns) {
        const surface = this.getOptionalRow(
          `SELECT agent_session_id FROM surface_conversations
           WHERE conversation_id = ? ORDER BY last_active_at_ms DESC LIMIT 1`,
          [repair.conversationId],
        );
        if (!surface) continue;
        eventIds.push(this.appendReconciliationEvent({
          sessionId: text(surface.agent_session_id),
          runId: repair.producingRunId,
          attemptId: null,
          type: "journal.turn_reconciled",
          payload: { turnId: repair.turnId, code: repair.code },
          createdAtMs: now,
        }));
      }

      const expiredContextPacketIds = this.allRows(
        "SELECT packet_id FROM desktop_context_packets WHERE expires_at_ms IS NOT NULL AND expires_at_ms <= ?",
        [now],
      ).map((row) => text(row.packet_id));
      if (expiredContextPacketIds.length > 0) {
        this.db.prepare(
          "DELETE FROM desktop_context_packets WHERE expires_at_ms IS NOT NULL AND expires_at_ms <= ?",
        ).run(now);
      }

      const expiredContinuationCheckpointIds = this.allRows(
        "SELECT checkpoint_id FROM workstream_continuation_checkpoints WHERE expires_at_ms <= ?",
        [now],
      ).map((row) => text(row.checkpoint_id));
      if (expiredContinuationCheckpointIds.length > 0) {
        this.db.prepare("DELETE FROM workstream_continuation_checkpoints WHERE expires_at_ms <= ?").run(now);
      }

      this.db.prepare(
        `UPDATE desktop_dispatches
         SET status = ?, resolved_at_ms = COALESCE(resolved_at_ms, ?), resolved_by = COALESCE(resolved_by, ?), resolution_json = COALESCE(resolution_json, ?)
         WHERE status = ?
           AND expires_at_ms IS NOT NULL
           AND expires_at_ms <= ?`,
      ).run("expired", now, "daemon_startup_reconciliation", JSON.stringify({ reason: "daemon_startup_reconciliation" }), "pending", now);

      const failedArtifactDeliveryIds = this.allRows(
        "SELECT delivery_id FROM desktop_artifact_deliveries WHERE delivery_status = ?",
        ["retrying"],
      ).map((row) => text(row.delivery_id));
      if (failedArtifactDeliveryIds.length > 0) {
        this.db.prepare(
          `UPDATE desktop_artifact_deliveries
           SET delivery_status = ?, updated_at_ms = ?, error_json = json_set(COALESCE(error_json, '{}'), '$.reason', ?)
           WHERE delivery_status = ?`,
        ).run("failed", now, "daemon_startup_reconciliation", "retrying");
      }

      const failedTaskCandidateDeliveryIds = this.allRows(
        "SELECT candidate_id FROM desktop_task_candidates WHERE delivery_status = ?",
        ["delivering"],
      ).map((row) => text(row.candidate_id));
      if (failedTaskCandidateDeliveryIds.length > 0) {
        this.db.prepare(
          `UPDATE desktop_task_candidates
           SET delivery_status = 'failed', updated_at_ms = ?,
               last_delivery_error_json = json_object('reason', 'daemon_startup_reconciliation')
           WHERE delivery_status = 'delivering'`,
        ).run(now);
      }

      const requeuedBackendTurnOutboxIds = this.allRows(
        "SELECT turn_id FROM backend_turn_outbox WHERE status = 'delivering'",
      ).map((row) => text(row.turn_id));
      if (requeuedBackendTurnOutboxIds.length > 0) {
        this.db.prepare(
          `UPDATE backend_turn_outbox
           SET status = 'retrying', available_at_ms = ?, lease_expires_at_ms = NULL,
               last_error_code = 'daemon_restart', updated_at_ms = ?
           WHERE status = 'delivering'`,
        ).run(now, now);
      }
      const requeuedBackendConversationDeleteIds = this.allRows(
        "SELECT operation_id FROM backend_conversation_delete_outbox WHERE status = 'delivering'",
      ).map((row) => text(row.operation_id));
      if (requeuedBackendConversationDeleteIds.length > 0) {
        this.db.prepare(
          `UPDATE backend_conversation_delete_outbox
           SET status = 'retrying', available_at_ms = ?, lease_expires_at_ms = NULL,
               last_error_code = 'daemon_restart', updated_at_ms = ?
           WHERE status = 'delivering'`,
        ).run(now, now);
      }
      this.db.prepare(
        `UPDATE backend_reconcile_state
         SET in_flight_id = NULL, page_cursor = NULL, page_count = 0,
             candidate_frontier_remote_id = NULL, status = 'idle',
             last_error_code = CASE WHEN status = 'fetching' THEN 'daemon_restart' ELSE last_error_code END,
             updated_at_ms = ?
         WHERE status = 'fetching'`,
      ).run(now);

      const recoveryDispatchIds: string[] = [];
      const orphanedDelegatedRuns = this.allRows(
        `SELECT r.run_id, r.session_id, s.owner_id
         FROM runs r
         JOIN sessions s ON s.session_id = r.session_id
         WHERE r.status = ?
           AND r.parent_run_id IS NOT NULL
           AND NOT EXISTS (
             SELECT 1 FROM desktop_dispatches d
             WHERE d.kind = 'failure_recovery'
               AND d.status != 'expired'
               AND d.source_run_id = r.run_id
           )`,
        ["orphaned"],
      );
      for (const run of orphanedDelegatedRuns) {
        const dispatch = this.insertDesktopDispatch({
          ownerId: text(run.owner_id),
          kind: "failure_recovery",
          priority: 80,
          status: "pending",
          title: "Agent run needs recovery",
          decisionPrompt: "A delegated local agent run was interrupted by a daemon restart. Choose whether to inspect, retry, or dismiss it.",
          recommendedDefault: "inspect",
          sourceSessionId: text(run.session_id),
          sourceRunId: text(run.run_id),
          payloadJson: JSON.stringify({ reason: "daemon_startup_reconciliation" }),
          createdAtMs: now,
        });
        recoveryDispatchIds.push(dispatch.dispatchId);
        const delegations = this.allRows(
          `SELECT delegation_id, parent_session_id, parent_run_id, status
           FROM delegations
           WHERE child_run_id = ? AND status IN ('pending', 'running')`,
          [text(run.run_id)],
        );
        for (const delegation of delegations) {
          this.db.prepare("UPDATE delegations SET status = ?, completed_at_ms = COALESCE(completed_at_ms, ?) WHERE delegation_id = ?").run(
            "failed",
            now,
            text(delegation.delegation_id),
          );
          eventIds.push(this.appendReconciliationEvent({
            sessionId: text(delegation.parent_session_id),
            runId: text(delegation.parent_run_id),
            attemptId: null,
            type: "delegation.recovery_required",
            payload: {
              delegationId: text(delegation.delegation_id),
              childRunId: text(run.run_id),
              dispatchId: dispatch.dispatchId,
              reason: "child_run_orphaned_after_restart",
            },
            createdAtMs: now,
          }));
        }
      }

      return {
        orphanedAttemptIds: activeAttempts.map((row) => text(row.attempt_id)),
        orphanedRunIds,
        staleBindingIds: staleBindings.map((row) => text(row.binding_id)),
        expiredContextPacketIds,
        expiredContinuationCheckpointIds,
        failedArtifactDeliveryIds,
        failedTaskCandidateDeliveryIds,
        requeuedBackendTurnOutboxIds,
        requeuedBackendConversationDeleteIds,
        failedPreparedToolInvocationIds,
        outcomeUnknownToolInvocationIds,
        repairedSessionProfileIds,
        repairedLegacyJournalTurnIds,
        reconciledJournalTurnIds: reconciledJournalTurns.map((repair) => repair.turnId),
        recoveryDispatchIds,
        clearedAttemptInstanceIds,
        clearedBindingInstanceIds,
        eventIds,
      };
    });
  }

  insertSurfaceConversation(input: NewSurfaceConversation): SurfaceConversation {
    this.db.prepare(
      `INSERT INTO surface_conversations (
        owner_id, surface_kind, external_ref_kind, external_ref_id,
        conversation_id, agent_session_id, created_at_ms, last_active_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      input.ownerId,
      input.surfaceKind,
      input.externalRefKind,
      input.externalRefId,
      input.conversationId,
      input.agentSessionId,
      input.createdAtMs,
      input.lastActiveAtMs,
    );
    return input;
  }

  insertConversationTurn(input: NewConversationTurn): ConversationTurn {
    const turnId = input.turnId ?? generateAgentId("turn");
    const status = input.status ?? "completed";
    const turn: ConversationTurn = {
      conversationId: input.conversationId,
      turnId,
      turnSeq: input.turnSeq ?? 0,
      producerId: input.producerId ?? `legacy:${turnId}`,
      payloadHash: input.payloadHash ?? "legacy",
      role: input.role,
      surfaceKind: input.surfaceKind,
      content: input.content,
      origin: input.origin ?? "legacy",
      status,
      contentBlocks: input.contentBlocks ?? (input.content.length > 0
        ? [{ type: "text", id: `${turnId}:text`, text: input.content }]
        : []),
      resources: input.resources ?? [],
      producingRunId: input.producingRunId ?? null,
      remoteId: input.remoteId ?? null,
      createdAtMs: input.createdAtMs,
      updatedAtMs: input.updatedAtMs ?? input.createdAtMs,
      completedAtMs: input.completedAtMs
        ?? (status === "completed" || status === "failed" ? input.createdAtMs : null),
      metadataJson: input.metadataJson ?? "{}",
    };
    this.db.prepare(
      `INSERT INTO conversation_turns (
        conversation_id, turn_id, turn_seq, producer_id, payload_hash,
        role, surface_kind, content, created_at_ms, metadata_json,
        origin, status, content_blocks_json, resources_json, producing_run_id,
        remote_id, updated_at_ms, completed_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      turn.conversationId,
      turn.turnId,
      turn.turnSeq,
      turn.producerId,
      turn.payloadHash,
      turn.role,
      turn.surfaceKind,
      turn.content,
      turn.createdAtMs,
      turn.metadataJson,
      turn.origin,
      turn.status,
      JSON.stringify(turn.contentBlocks),
      JSON.stringify(turn.resources),
      turn.producingRunId,
      turn.remoteId,
      turn.updatedAtMs,
      turn.completedAtMs,
    );
    return turn;
  }

  insertSession(input: NewAgentSession): AgentSession {
    const now = this.nowMs();
    const session: AgentSession = {
      sessionId: input.sessionId ?? generateAgentId("session"),
      ownerId: input.ownerId,
      agentDefinitionId: input.agentDefinitionId ?? "omi.generalist@1",
      title: input.title ?? null,
      status: input.status ?? "open",
      surfaceKind: input.surfaceKind,
      executionRole: input.executionRole ?? "coordinator",
      providerBoundary: input.providerBoundary ?? providerBoundaryForAdapter(input.defaultAdapterId),
      externalRefKind: input.externalRefKind ?? null,
      externalRefId: input.externalRefId ?? null,
      defaultAdapterId: input.defaultAdapterId,
      defaultCwd: input.defaultCwd ?? null,
      modelProfile: input.modelProfile ?? null,
      executionProfileGeneration: input.executionProfileGeneration ?? 1,
      metadataJson: input.metadataJson ?? "{}",
      createdAtMs: input.createdAtMs ?? now,
      updatedAtMs: input.updatedAtMs ?? now,
      lastActivityAtMs: input.lastActivityAtMs ?? now,
    };
    this.withTransaction(() => {
      this.db.prepare(
        `INSERT INTO sessions (
          session_id, owner_id, agent_definition_id, title, status, surface_kind, execution_role, provider_boundary,
          external_ref_kind, external_ref_id, legacy_client_scope, legacy_session_key,
          default_adapter_id, default_cwd, model_profile, metadata_json,
          created_at_ms, updated_at_ms, last_activity_at_ms, current_profile_generation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).run(...sessionValues(session));
      this.db.prepare(
        `INSERT INTO session_execution_profiles(
          session_id, generation, adapter_id, credential_scope, model_profile,
          working_directory, execution_role, source, audit_json, created_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).run(
        session.sessionId,
        session.executionProfileGeneration,
        session.defaultAdapterId,
        session.providerBoundary === "managed_cloud" ? "managed_cloud" : "local_user",
        session.modelProfile,
        session.defaultCwd ?? "",
        session.executionRole,
        input.executionProfileSource ?? "creation",
        JSON.stringify({
          legacyProjection: {
            readAuthority: false,
            owner: "desktop-kernel",
            removalCondition: "all supported desktop versions write immutable session execution profiles",
            removeBy: "2026-10-01",
          },
        }),
        session.createdAtMs,
      );
    });
    return session;
  }

  insertRun(input: NewAgentRun): AgentRun {
    const now = this.nowMs();
    const run: AgentRun = {
      runId: input.runId ?? generateAgentId("run"),
      sessionId: input.sessionId,
      parentRunId: input.parentRunId ?? null,
      clientId: input.clientId,
      requestId: input.requestId,
      idempotencyKey: input.idempotencyKey ?? null,
      status: input.status,
      mode: input.mode,
      profileGeneration: input.profileGeneration ?? 1,
      inputJson: input.inputJson ?? "{}",
      systemPromptHash: input.systemPromptHash ?? null,
      modelProfile: input.modelProfile ?? null,
      requestedModelId: input.requestedModelId ?? null,
      cwd: input.cwd ?? null,
      finalText: input.finalText ?? null,
      resultJson: input.resultJson ?? null,
      errorCode: input.errorCode ?? null,
      errorMessage: input.errorMessage ?? null,
      inputTokens: input.inputTokens ?? null,
      outputTokens: input.outputTokens ?? null,
      cacheReadTokens: input.cacheReadTokens ?? null,
      cacheWriteTokens: input.cacheWriteTokens ?? null,
      costUsd: input.costUsd ?? null,
      createdAtMs: input.createdAtMs ?? now,
      startedAtMs: input.startedAtMs ?? null,
      completedAtMs: input.completedAtMs ?? null,
      updatedAtMs: input.updatedAtMs ?? now,
    };
    this.db.prepare(
      `INSERT INTO runs (
        run_id, session_id, parent_run_id, client_id, request_id, idempotency_key,
        status, mode, profile_generation, input_json, system_prompt_hash, model_profile, requested_model_id,
        cwd, final_text, result_json, error_code, error_message, input_tokens,
        output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
        created_at_ms, started_at_ms, completed_at_ms, updated_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...runValues(run));
    return run;
  }

  insertAttempt(input: NewRunAttempt): RunAttempt {
    const now = this.nowMs();
    const attempt: RunAttempt = {
      attemptId: input.attemptId ?? generateAgentId("attempt"),
      runId: input.runId,
      attemptNo: input.attemptNo,
      profileGeneration: input.profileGeneration ?? 1,
      status: input.status,
      adapterId: input.adapterId,
      adapterInstanceId: input.adapterInstanceId,
      runtimeNodeId: input.runtimeNodeId ?? "desktop-local",
      bindingId: input.bindingId ?? null,
      adapterNativeRunId: input.adapterNativeRunId ?? null,
      resumeFromAttemptId: input.resumeFromAttemptId ?? null,
      checkpointArtifactId: input.checkpointArtifactId ?? null,
      retryReason: input.retryReason ?? null,
      retryable: input.retryable ?? 0,
      cancellationRequestedAtMs: input.cancellationRequestedAtMs ?? null,
      cancellationDispatchedAtMs: input.cancellationDispatchedAtMs ?? null,
      cancellationAcknowledgedAtMs: input.cancellationAcknowledgedAtMs ?? null,
      startedAtMs: input.startedAtMs ?? null,
      completedAtMs: input.completedAtMs ?? null,
      errorCode: input.errorCode ?? null,
      errorMessage: input.errorMessage ?? null,
      metadataJson: input.metadataJson ?? "{}",
      createdAtMs: input.createdAtMs ?? now,
      updatedAtMs: input.updatedAtMs ?? now,
    };
    this.db.prepare(
      `INSERT INTO run_attempts (
        attempt_id, run_id, attempt_no, profile_generation, status, adapter_id, adapter_instance_id,
        runtime_node_id, binding_id, adapter_native_run_id, resume_from_attempt_id,
        checkpoint_artifact_id, retry_reason, retryable, cancellation_requested_at_ms,
        cancellation_dispatched_at_ms, cancellation_acknowledged_at_ms, started_at_ms,
        completed_at_ms, error_code, error_message, metadata_json, created_at_ms, updated_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...attemptValues(attempt));
    return attempt;
  }

  insertAdapterBinding(input: NewAdapterBinding): AdapterBinding {
    const now = this.nowMs();
    const binding: AdapterBinding = {
      bindingId: input.bindingId ?? generateAgentId("binding"),
      sessionId: input.sessionId,
      adapterId: input.adapterId,
      bindingGeneration: input.bindingGeneration,
      profileGeneration: input.profileGeneration ?? 1,
      adapterNativeSessionId: input.adapterNativeSessionId ?? null,
      adapterInstanceId: input.adapterInstanceId ?? null,
      resumeFidelity: input.resumeFidelity,
      status: input.status,
      cwd: input.cwd ?? null,
      modelId: input.modelId ?? null,
      systemPromptHash: input.systemPromptHash ?? null,
      metadataJson: input.metadataJson ?? "{}",
      createdAtMs: input.createdAtMs ?? now,
      updatedAtMs: input.updatedAtMs ?? now,
      lastUsedAtMs: input.lastUsedAtMs ?? null,
      invalidatedAtMs: input.invalidatedAtMs ?? null,
    };
    this.withTransaction(() => {
      if (binding.adapterNativeSessionId) {
        this.db.prepare(
          `UPDATE adapter_bindings
           SET status = ?, adapter_instance_id = NULL, invalidated_at_ms = COALESCE(invalidated_at_ms, ?), updated_at_ms = ?
           WHERE adapter_id = ? AND adapter_native_session_id = ? AND status != ?`,
        ).run("closed", now, now, binding.adapterId, binding.adapterNativeSessionId, "closed");
      }
      this.db.prepare(
        `INSERT INTO adapter_bindings (
          binding_id, session_id, adapter_id, binding_generation, profile_generation, adapter_native_session_id,
          adapter_instance_id, resume_fidelity, status, cwd, model_id, system_prompt_hash,
          metadata_json, created_at_ms, updated_at_ms, last_used_at_ms, invalidated_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).run(...bindingValues(binding));
    });
    return binding;
  }

  insertArtifact(input: NewAgentArtifact): AgentArtifact {
    const artifact: AgentArtifact = {
      artifactId: input.artifactId ?? generateAgentId("artifact"),
      sessionId: input.sessionId,
      runId: input.runId ?? null,
      attemptId: input.attemptId ?? null,
      kind: input.kind,
      role: input.role,
      uri: input.uri,
      displayName: input.displayName ?? null,
      mimeType: input.mimeType ?? null,
      contentHash: input.contentHash ?? null,
      sizeBytes: input.sizeBytes ?? null,
      lifecycleState: input.lifecycleState ?? "retained",
      lifecycleUpdatedAtMs: input.lifecycleUpdatedAtMs ?? null,
      metadataJson: input.metadataJson ?? "{}",
      createdAtMs: input.createdAtMs ?? this.nowMs(),
    };
    this.db.prepare(
      `INSERT INTO artifacts (
        artifact_id, session_id, run_id, attempt_id, kind, role, uri,
        display_name, mime_type, content_hash, size_bytes, lifecycle_state,
        lifecycle_updated_at_ms, metadata_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...artifactValues(artifact));
    return artifact;
  }

  appendEvent(input: NewAgentEvent): AgentEvent {
    const event = this.buildEvent(input);
    this.db.prepare(
      `INSERT INTO events (
        event_id, session_id, run_id, attempt_id, type, retention_class,
        visibility, payload_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...eventValues(event));
    const row = this.getRow("SELECT event_seq FROM events WHERE event_id = ?", [event.eventId]);
    return { ...event, eventSeq: Number(row.event_seq) };
  }

  insertGrant(input: NewAgentGrant): AgentGrant {
    const grant: AgentGrant = {
      grantId: input.grantId ?? generateAgentId("grant"),
      sessionId: input.sessionId,
      runId: input.runId ?? null,
      capability: input.capability,
      operation: input.operation,
      resourcePattern: input.resourcePattern,
      effect: input.effect,
      source: input.source,
      constraintsJson: input.constraintsJson ?? "{}",
      createdAtMs: input.createdAtMs ?? this.nowMs(),
      expiresAtMs: input.expiresAtMs ?? null,
      revokedAtMs: input.revokedAtMs ?? null,
    };
    this.db.prepare(
      `INSERT INTO grants (
        grant_id, session_id, run_id, capability, operation, resource_pattern,
        effect, source, constraints_json, created_at_ms, expires_at_ms, revoked_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...grantValues(grant));
    return grant;
  }

  insertDesktopContextPacket(input: NewDesktopContextPacket): DesktopContextPacket {
    const now = this.nowMs();
    const createdAtMs = input.createdAtMs ?? now;
    if (
      typeof input.expiresAtMs !== "number" ||
      !Number.isFinite(input.expiresAtMs) ||
      input.expiresAtMs <= now ||
      input.expiresAtMs <= createdAtMs
    ) {
      throw new Error("Desktop context packet expiresAtMs must be in the future");
    }
    this.assertCoordinatorScope({
      ownerId: input.ownerId,
      sessionId: input.sessionId ?? null,
      runId: input.runId ?? null,
    });
    const packet: DesktopContextPacket = {
      packetId: input.packetId ?? generateAgentId("contextPacket"),
      ownerId: input.ownerId,
      sessionId: input.sessionId ?? null,
      runId: input.runId ?? null,
      surfaceKind: input.surfaceKind,
      objective: input.objective,
      packetJson: input.packetJson,
      redactedPreviewJson: input.redactedPreviewJson,
      contextHash: input.contextHash,
      tokenEstimate: input.tokenEstimate ?? null,
      retentionClass: input.retentionClass,
      expiresAtMs: input.expiresAtMs,
      createdAtMs,
    };
    this.db.prepare(
      `INSERT INTO desktop_context_packets (
        packet_id, owner_id, session_id, run_id, surface_kind, objective,
        packet_json, redacted_preview_json, context_hash, token_estimate,
        retention_class, expires_at_ms, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...desktopContextPacketValues(packet));
    return packet;
  }

  insertDesktopDispatch(input: NewDesktopCoordinatorDispatch): DesktopCoordinatorDispatch {
    this.assertCoordinatorScope({
      ownerId: input.ownerId,
      sessionId: input.sourceSessionId ?? null,
      runId: input.sourceRunId ?? null,
      attemptId: input.sourceAttemptId ?? null,
      artifactId: input.sourceArtifactId ?? null,
    });
    const createdAtMs = input.createdAtMs ?? this.nowMs();
    if (
      typeof input.expiresAtMs === "number" &&
      Number.isFinite(input.expiresAtMs) &&
      input.expiresAtMs <= createdAtMs
    ) {
      throw new Error("Desktop dispatch expiresAtMs must be a future timestamp");
    }
    const dispatch: DesktopCoordinatorDispatch = {
      dispatchId: input.dispatchId ?? generateAgentId("dispatch"),
      ownerId: input.ownerId,
      kind: input.kind,
      priority: input.priority,
      status: input.status ?? "pending",
      title: input.title,
      decisionPrompt: input.decisionPrompt,
      recommendedDefault: input.recommendedDefault ?? null,
      sourceSessionId: input.sourceSessionId ?? null,
      sourceRunId: input.sourceRunId ?? null,
      sourceAttemptId: input.sourceAttemptId ?? null,
      sourceArtifactId: input.sourceArtifactId ?? null,
      capability: input.capability ?? null,
      operation: input.operation ?? null,
      resourceRef: input.resourceRef ?? null,
      payloadJson: input.payloadJson ?? "{}",
      createdAtMs,
      expiresAtMs: input.expiresAtMs ?? null,
      resolvedAtMs: input.resolvedAtMs ?? null,
      resolvedBy: input.resolvedBy ?? null,
      resolutionJson: input.resolutionJson ?? null,
    };
    this.db.prepare(
      `INSERT INTO desktop_dispatches (
        dispatch_id, owner_id, kind, priority, status, title, decision_prompt,
        recommended_default, source_session_id, source_run_id, source_attempt_id,
        source_artifact_id, capability, operation, resource_ref, payload_json,
        created_at_ms, expires_at_ms, resolved_at_ms, resolved_by, resolution_json
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...desktopDispatchValues(dispatch));
    return dispatch;
  }

  resolveDesktopDispatch(dispatchId: string, input: { ownerId: string; status: "resolved" | "cancelled"; resolvedBy?: string | null; resolutionJson?: string | null; resolvedAtMs?: number }): DesktopCoordinatorDispatch {
    const resolvedAtMs = input.resolvedAtMs ?? this.nowMs();
    const result = this.db.prepare(
      `UPDATE desktop_dispatches
       SET status = ?, resolved_at_ms = ?, resolved_by = ?, resolution_json = ?
       WHERE dispatch_id = ?
         AND owner_id = ?
         AND status = 'pending'
         AND (expires_at_ms IS NULL OR expires_at_ms > ?)`,
    ).run(input.status, resolvedAtMs, input.resolvedBy ?? null, input.resolutionJson ?? null, dispatchId, input.ownerId, resolvedAtMs);
    if (Number(result.changes) === 0) {
      throw new Error(`Desktop dispatch ${dispatchId} is not pending for owner or has expired`);
    }
    return desktopDispatchFromRow(this.getRow("SELECT * FROM desktop_dispatches WHERE dispatch_id = ?", [dispatchId]));
  }

  insertDesktopArtifactDelivery(input: NewDesktopArtifactDelivery): DesktopArtifactDelivery {
    const now = this.nowMs();
    this.assertCoordinatorScope({
      ownerId: input.ownerId,
      sessionId: input.sourceSessionId,
      runId: input.sourceRunId ?? null,
      attemptId: input.sourceAttemptId ?? null,
      artifactId: input.artifactId,
    });
    const delivery: DesktopArtifactDelivery = {
      deliveryId: input.deliveryId ?? generateAgentId("artifactDelivery"),
      artifactId: input.artifactId,
      ownerId: input.ownerId,
      sourceSessionId: input.sourceSessionId,
      sourceRunId: input.sourceRunId ?? null,
      sourceAttemptId: input.sourceAttemptId ?? null,
      intendedSurface: input.intendedSurface,
      targetKind: input.targetKind,
      targetRef: input.targetRef ?? null,
      contentHash: input.contentHash ?? null,
      reviewStatus: input.reviewStatus ?? "not_required",
      deliveryStatus: input.deliveryStatus ?? "pending",
      attemptCount: input.attemptCount ?? 0,
      receiptJson: input.receiptJson ?? null,
      errorJson: input.errorJson ?? null,
      createdAtMs: input.createdAtMs ?? now,
      updatedAtMs: input.updatedAtMs ?? now,
      deliveredAtMs: input.deliveredAtMs ?? null,
    };
    this.db.prepare(
      `INSERT INTO desktop_artifact_deliveries (
        delivery_id, artifact_id, owner_id, source_session_id, source_run_id,
        source_attempt_id, intended_surface, target_kind, target_ref, content_hash,
        review_status, delivery_status, attempt_count, receipt_json, error_json,
        created_at_ms, updated_at_ms, delivered_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...desktopArtifactDeliveryValues(delivery));
    return delivery;
  }

  updateDesktopArtifactDelivery(deliveryId: string, input: { ownerId: string } & Partial<Pick<DesktopArtifactDelivery, "reviewStatus" | "deliveryStatus" | "attemptCount" | "receiptJson" | "errorJson" | "deliveredAtMs">>): DesktopArtifactDelivery {
    const current = desktopArtifactDeliveryFromRow(this.getRow("SELECT * FROM desktop_artifact_deliveries WHERE delivery_id = ? AND owner_id = ?", [deliveryId, input.ownerId]));
    const updated: DesktopArtifactDelivery = {
      ...current,
      reviewStatus: input.reviewStatus ?? current.reviewStatus,
      deliveryStatus: input.deliveryStatus ?? current.deliveryStatus,
      attemptCount: input.attemptCount ?? current.attemptCount,
      receiptJson: input.receiptJson ?? current.receiptJson,
      errorJson: input.errorJson ?? current.errorJson,
      deliveredAtMs: input.deliveredAtMs ?? current.deliveredAtMs,
      updatedAtMs: this.nowMs(),
    };
    this.db.prepare(
      `UPDATE desktop_artifact_deliveries
       SET review_status = ?, delivery_status = ?, attempt_count = ?, receipt_json = ?,
           error_json = ?, updated_at_ms = ?, delivered_at_ms = ?
       WHERE delivery_id = ? AND owner_id = ?`,
    ).run(updated.reviewStatus, updated.deliveryStatus, updated.attemptCount, updated.receiptJson, updated.errorJson, updated.updatedAtMs, updated.deliveredAtMs, deliveryId, input.ownerId);
    return updated;
  }

  insertDesktopMemoryCandidate(input: NewDesktopMemoryCandidate): DesktopMemoryCandidate {
    this.assertCoordinatorScope({
      ownerId: input.ownerId,
      sessionId: input.sourceSessionId,
      runId: input.sourceRunId ?? null,
      artifactId: input.sourceArtifactId ?? null,
    });
    const candidate: DesktopMemoryCandidate = {
      candidateId: input.candidateId ?? generateAgentId("memoryCandidate"),
      ownerId: input.ownerId,
      sourceSessionId: input.sourceSessionId,
      sourceRunId: input.sourceRunId ?? null,
      sourceArtifactId: input.sourceArtifactId ?? null,
      proposedFact: input.proposedFact,
      evidenceRefsJson: input.evidenceRefsJson,
      confidence: input.confidence,
      sensitivityTier: input.sensitivityTier,
      status: input.status ?? "pending",
      createdAtMs: input.createdAtMs ?? this.nowMs(),
      resolvedAtMs: input.resolvedAtMs ?? null,
    };
    this.db.prepare(
      `INSERT INTO desktop_memory_candidates (
        candidate_id, owner_id, source_session_id, source_run_id, source_artifact_id,
        proposed_fact, evidence_refs_json, confidence, sensitivity_tier, status,
        created_at_ms, resolved_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...desktopMemoryCandidateValues(candidate));
    return candidate;
  }

  insertDesktopTaskCandidate(input: NewDesktopTaskCandidate): DesktopTaskCandidate {
    this.assertCoordinatorScope({
      ownerId: input.ownerId,
      sessionId: input.sourceSessionId ?? null,
      runId: input.sourceRunId ?? null,
    });
    const candidate: DesktopTaskCandidate = {
      candidateId: input.candidateId ?? generateAgentId("taskCandidate"),
      ownerId: input.ownerId,
      sourceSessionId: input.sourceSessionId ?? null,
      sourceRunId: input.sourceRunId ?? null,
      action: input.action,
      taskRef: input.taskRef ?? null,
      proposedChangeJson: input.proposedChangeJson,
      evidenceRefsJson: input.evidenceRefsJson,
      confidence: input.confidence,
      ownershipConfidence: input.ownershipConfidence ?? input.confidence,
      requiresApproval: input.requiresApproval,
      goalRef: input.goalRef ?? null,
      workstreamRef: input.workstreamRef ?? null,
      sourceSurface: input.sourceSurface ?? "desktop_agent",
      accountGeneration: input.accountGeneration ?? 0,
      generationReconciled: input.generationReconciled ?? (input.accountGeneration === undefined ? 0 : 1),
      status: input.status ?? "pending",
      deliveryStatus: input.deliveryStatus ?? "pending",
      deliveryAttemptCount: input.deliveryAttemptCount ?? 0,
      deliveryKey: input.deliveryKey ?? input.candidateId ?? "",
      backendCandidateId: input.backendCandidateId ?? null,
      backendReceiptJson: input.backendReceiptJson ?? null,
      backendResolutionReceiptJson: input.backendResolutionReceiptJson ?? null,
      backendResolutionStatus: input.backendResolutionStatus ?? null,
      lastDeliveryErrorJson: input.lastDeliveryErrorJson ?? null,
      createdAtMs: input.createdAtMs ?? this.nowMs(),
      updatedAtMs: input.updatedAtMs ?? input.createdAtMs ?? this.nowMs(),
      deliveredAtMs: input.deliveredAtMs ?? null,
      resolvedAtMs: input.resolvedAtMs ?? null,
    };
    if (!candidate.deliveryKey) candidate.deliveryKey = candidate.candidateId;
    this.db.prepare(
      `INSERT INTO desktop_task_candidates (
        candidate_id, owner_id, source_session_id, source_run_id, action,
        task_ref, proposed_change_json, evidence_refs_json, confidence,
        ownership_confidence, requires_approval, goal_ref, workstream_ref,
        source_surface, account_generation, generation_reconciled, status, delivery_status, delivery_attempt_count,
        delivery_key, backend_candidate_id, backend_receipt_json,
        backend_resolution_receipt_json, backend_resolution_status, last_delivery_error_json, created_at_ms,
        updated_at_ms, delivered_at_ms, resolved_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...desktopTaskCandidateValues(candidate));
    return candidate;
  }

  insertDesktopContextAccessLog(input: NewDesktopContextAccessLog): DesktopContextAccessLog {
    this.assertCoordinatorScope({
      ownerId: input.ownerId,
      packetId: input.packetId ?? null,
      runId: input.runId ?? null,
      dispatchId: input.dispatchId ?? null,
    });
    const access: DesktopContextAccessLog = {
      accessId: input.accessId ?? generateAgentId("contextAccess"),
      ownerId: input.ownerId,
      packetId: input.packetId ?? null,
      runId: input.runId ?? null,
      sourceKind: input.sourceKind,
      operation: input.operation,
      scopeJson: input.scopeJson,
      sensitivityTier: input.sensitivityTier,
      policyDecision: input.policyDecision,
      dispatchId: input.dispatchId ?? null,
      redactionSummaryJson: input.redactionSummaryJson ?? "{}",
      createdAtMs: input.createdAtMs ?? this.nowMs(),
    };
    this.db.prepare(
      `INSERT INTO desktop_context_access_log (
        access_id, owner_id, packet_id, run_id, source_kind, operation, scope_json,
        sensitivity_tier, policy_decision, dispatch_id, redaction_summary_json,
        created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...desktopContextAccessLogValues(access));
    return access;
  }

  upsertDesktopAttentionOverride(input: NewDesktopAttentionOverride): DesktopAttentionOverride {
    const override: DesktopAttentionOverride = {
      ownerId: input.ownerId,
      subjectKind: input.subjectKind,
      subjectId: input.subjectId,
      hiddenUntilMs: input.hiddenUntilMs ?? null,
      dismissedAtMs: input.dismissedAtMs ?? null,
      reason: input.reason ?? null,
      createdAtMs: input.createdAtMs ?? this.nowMs(),
    };
    this.db.prepare(
      `INSERT INTO desktop_attention_overrides (
        owner_id, subject_kind, subject_id, hidden_until_ms, dismissed_at_ms, reason, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(owner_id, subject_kind, subject_id) DO UPDATE SET
        hidden_until_ms = excluded.hidden_until_ms,
        dismissed_at_ms = excluded.dismissed_at_ms,
        reason = excluded.reason`,
    ).run(...desktopAttentionOverrideValues(override));
    return desktopAttentionOverrideFromRow(this.getRow(
      "SELECT * FROM desktop_attention_overrides WHERE owner_id = ? AND subject_kind = ? AND subject_id = ?",
      [override.ownerId, override.subjectKind, override.subjectId],
    ));
  }

  private assertCoordinatorScope(input: {
    ownerId: string;
    sessionId?: string | null;
    runId?: string | null;
    attemptId?: string | null;
    artifactId?: string | null;
    packetId?: string | null;
    dispatchId?: string | null;
  }): void {
    if (input.sessionId) {
      const session = this.getOptionalRow("SELECT owner_id FROM sessions WHERE session_id = ?", [input.sessionId]);
      if (!session || text(session.owner_id) !== input.ownerId) {
        throw new Error("Coordinator session reference is outside owner scope");
      }
    }
    if (input.runId) {
      const run = this.getOptionalRow(
        `SELECT r.session_id, s.owner_id
         FROM runs r
         JOIN sessions s ON s.session_id = r.session_id
         WHERE r.run_id = ?`,
        [input.runId],
      );
      if (!run || text(run.owner_id) !== input.ownerId) {
        throw new Error("Coordinator run reference is outside owner scope");
      }
      if (input.sessionId && text(run.session_id) !== input.sessionId) {
        throw new Error("Coordinator run reference does not belong to session");
      }
    }
    if (input.attemptId) {
      const attempt = this.getOptionalRow(
        `SELECT a.run_id, r.session_id, s.owner_id
         FROM run_attempts a
         JOIN runs r ON r.run_id = a.run_id
         JOIN sessions s ON s.session_id = r.session_id
         WHERE a.attempt_id = ?`,
        [input.attemptId],
      );
      if (!attempt || text(attempt.owner_id) !== input.ownerId) {
        throw new Error("Coordinator attempt reference is outside owner scope");
      }
      if (input.runId && text(attempt.run_id) !== input.runId) {
        throw new Error("Coordinator attempt reference does not belong to run");
      }
      if (input.sessionId && text(attempt.session_id) !== input.sessionId) {
        throw new Error("Coordinator attempt reference does not belong to session");
      }
    }
    if (input.artifactId) {
      const artifact = this.getOptionalRow(
        `SELECT a.session_id, a.run_id, a.attempt_id, s.owner_id
         FROM artifacts a
         JOIN sessions s ON s.session_id = a.session_id
         WHERE a.artifact_id = ?`,
        [input.artifactId],
      );
      if (!artifact || text(artifact.owner_id) !== input.ownerId) {
        throw new Error("Coordinator artifact reference is outside owner scope");
      }
      if (input.sessionId && text(artifact.session_id) !== input.sessionId) {
        throw new Error("Coordinator artifact reference does not belong to session");
      }
      if (input.runId && nullableText(artifact.run_id) !== input.runId) {
        throw new Error("Coordinator artifact reference does not belong to run");
      }
      if (input.attemptId && nullableText(artifact.attempt_id) !== input.attemptId) {
        throw new Error("Coordinator artifact reference does not belong to attempt");
      }
    }
    if (input.packetId) {
      const packet = this.getOptionalRow("SELECT owner_id FROM desktop_context_packets WHERE packet_id = ?", [input.packetId]);
      if (!packet || text(packet.owner_id) !== input.ownerId) {
        throw new Error("Coordinator packet reference is outside owner scope");
      }
    }
    if (input.dispatchId) {
      const dispatch = this.getOptionalRow("SELECT owner_id FROM desktop_dispatches WHERE dispatch_id = ?", [input.dispatchId]);
      if (!dispatch || text(dispatch.owner_id) !== input.ownerId) {
        throw new Error("Coordinator dispatch reference is outside owner scope");
      }
    }
  }

  execute(sql: string, values: SQLInputValue[] = []): number {
    return Number(this.db.prepare(sql).run(...values).changes);
  }

  getPragma(name: string): SQLOutputValue | undefined {
    return Object.values(this.getRow(`PRAGMA ${name}`))[0];
  }

  getRow(sql: string, values: SQLInputValue[] = []): Row {
    const row = this.db.prepare(sql).get(...values);
    if (!row) {
      throw new Error(`Expected row for query: ${sql}`);
    }
    return row;
  }

  getOptionalRow(sql: string, values: SQLInputValue[] = []): Row | undefined {
    const row = this.db.prepare(sql).get(...values);
    return row;
  }

  allRows(sql: string, values: SQLInputValue[] = []): Row[] {
    return Array.from(this.db.prepare(sql).iterate(...values));
  }

  private hasMigration(version: number): boolean {
    return this.db.prepare("SELECT 1 FROM schema_migrations WHERE version = ?").get(version) !== undefined;
  }

  private appendReconciliationEvent(input: {
    sessionId: string;
    runId: string | null;
    attemptId: string | null;
    type: string;
    payload: Record<string, unknown>;
    createdAtMs: number;
  }): string {
    const eventId = generateAgentId("event");
    this.db.prepare(
      `INSERT INTO events (
        event_id, session_id, run_id, attempt_id, type, retention_class,
        visibility, payload_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      eventId,
      input.sessionId,
      input.runId,
      input.attemptId,
      input.type,
      "core",
      "internal",
      JSON.stringify(input.payload),
      input.createdAtMs,
    );
    return eventId;
  }

  private buildEvent(input: NewAgentEvent): AgentEvent {
    return {
      eventId: input.eventId ?? generateAgentId("event"),
      sessionId: input.sessionId,
      runId: input.runId ?? null,
      attemptId: input.attemptId ?? null,
      type: input.type,
      retentionClass: input.retentionClass ?? "core",
      visibility: input.visibility ?? "ui",
      payloadJson: input.payloadJson ?? "{}",
      createdAtMs: input.createdAtMs ?? this.nowMs(),
    };
  }
}

function requiredStateDir(stateDir: string | undefined): string {
  if (!stateDir) {
    throw new Error("SqliteAgentStore requires stateDir or databasePath");
  }
  return stateDir;
}

function applyConnectionPragmas(db: Pick<DatabaseSync, "exec">): void {
  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;
    PRAGMA synchronous = NORMAL;
    PRAGMA busy_timeout = 5000;
  `);
}

function createSchemaMigrationsTable(db: Pick<DatabaseSync, "exec">): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      applied_at_ms INTEGER NOT NULL
    ) STRICT;
  `);
}

function repairMissingSessionExecutionProfiles(
  db: Pick<DatabaseSync, "prepare">,
  nowMs: number,
): string[] {
  const rows = db.prepare(
    `SELECT s.* FROM sessions s
     WHERE NOT EXISTS (
       SELECT 1 FROM session_execution_profiles p
       WHERE p.session_id = s.session_id AND p.generation = s.current_profile_generation
     )
     ORDER BY s.created_at_ms ASC, s.session_id ASC`,
  ).all() as Row[];
  for (const row of rows) {
    db.prepare(
      `INSERT INTO session_execution_profiles(
         session_id, generation, adapter_id, credential_scope, model_profile,
         working_directory, execution_role, source, audit_json, created_at_ms
       ) VALUES (?, ?, ?, ?, ?, ?, ?, 'legacy_backfill', ?, ?)`,
    ).run(
      row.session_id,
      row.current_profile_generation,
      row.default_adapter_id,
      String(row.provider_boundary) === "managed_cloud" ? "managed_cloud" : "local_user",
      row.model_profile,
      row.default_cwd ?? "",
      row.execution_role,
      JSON.stringify({
        reason: "downgrade_window_missing_profile_repair",
        legacyProjection: {
          readAuthority: false,
          owner: "desktop-kernel",
          removalCondition: "all supported desktop versions write immutable session execution profiles",
          removeBy: "2026-10-01",
        },
      }),
      row.created_at_ms ?? nowMs,
    );
  }
  return rows.map((row) => text(row.session_id));
}

function repairDowngradeWindowJournalRows(
  db: Pick<DatabaseSync, "prepare">,
  nowMs: number,
): string[] {
  const rows = db.prepare(
    `SELECT ct.* FROM conversation_turns ct
     WHERE ct.turn_seq <= 0
        OR ct.producer_id IS NULL OR ct.producer_id = ''
        OR ct.payload_hash IS NULL OR ct.payload_hash IN ('', 'legacy', 'uncomputed')
        OR NOT EXISTS (
          SELECT 1 FROM conversation_turn_revisions revision
          WHERE revision.conversation_id = ct.conversation_id
            AND revision.turn_id = ct.turn_id
        )
     ORDER BY ct.created_at_ms ASC, ct.turn_id ASC`,
  ).all() as Row[];
  for (const row of rows) {
    const metadata = repairMetadata(row.metadata_json, {
      code: "downgrade_window_journal_repair",
      owner: "desktop-kernel",
      removalCondition: "all supported desktop versions write sequenced journal revisions",
      removeBy: "2026-10-01",
    });
    rewriteJournalRow(db, row, {
      status: text(row.status),
      metadataJson: metadata,
      completedAtMs: row.completed_at_ms == null ? null : Number(row.completed_at_ms),
      nowMs,
    });
  }
  return rows.map((row) => text(row.turn_id));
}

interface StartupJournalRepair {
  turnId: string;
  conversationId: string;
  producingRunId: string | null;
  code: string;
}

function reconcileNonterminalJournalRows(
  db: Pick<DatabaseSync, "prepare">,
  nowMs: number,
): StartupJournalRepair[] {
  const rows = db.prepare(
    `SELECT ct.*, r.status AS producing_run_status
     FROM conversation_turns ct
     LEFT JOIN runs r ON r.run_id = ct.producing_run_id
     WHERE ct.status IN ('pending', 'streaming')
     ORDER BY ct.created_at_ms ASC, ct.turn_id ASC`,
  ).all() as Row[];
  return rows.map((row) => {
    const succeeded = String(row.producing_run_status ?? "") === "succeeded";
    const status = succeeded ? "completed" : "failed";
    const code = succeeded ? "daemon_restart_completed_turn_repair" : "daemon_restart_orphaned_turn";
    const metadata = repairMetadata(row.metadata_json, {
      code,
      owner: "desktop-kernel",
      observedStatus: String(row.status),
    });
    rewriteJournalRow(db, row, {
      status,
      metadataJson: metadata,
      completedAtMs: nowMs,
      nowMs,
    });
    const blocks = parseJsonArray(row.content_blocks_json);
    const resources = parseJsonArray(row.resources_json);
    if (status === "failed" && !String(row.content).trim() && blocks.length === 0 && resources.length === 0) {
      db.prepare("DELETE FROM backend_turn_outbox WHERE turn_id = ?").run(row.turn_id);
    }
    return {
      turnId: text(row.turn_id),
      conversationId: text(row.conversation_id),
      producingRunId: row.producing_run_id == null ? null : text(row.producing_run_id),
      code,
    };
  });
}

function rewriteJournalRow(
  db: Pick<DatabaseSync, "prepare">,
  row: Row,
  input: { status: string; metadataJson: string; completedAtMs: number | null; nowMs: number },
): void {
  const conversationId = text(row.conversation_id);
  db.prepare(
    `INSERT INTO conversation_journal_state(
       conversation_id, generation, high_water_turn_seq, updated_at_ms
     ) SELECT ?, 1, COALESCE(MAX(turn_seq), 0), ?
       FROM conversation_turns WHERE conversation_id = ?
     ON CONFLICT(conversation_id) DO NOTHING`,
  ).run(conversationId, input.nowMs, conversationId);
  const state = db.prepare(
    "SELECT generation, high_water_turn_seq FROM conversation_journal_state WHERE conversation_id = ?",
  ).get(conversationId) as Row;
  const maximum = db.prepare(
    "SELECT COALESCE(MAX(turn_seq), 0) AS maximum FROM conversation_turns WHERE conversation_id = ?",
  ).get(conversationId) as Row;
  const turnSeq = Math.max(Number(state.high_water_turn_seq), Number(maximum.maximum)) + 1;
  const producerId = row.producer_id == null || !String(row.producer_id).trim()
    ? `legacy:${text(row.turn_id)}`
    : text(row.producer_id);
  const contentBlocks = parseJsonArray(row.content_blocks_json);
  const resources = parseJsonArray(row.resources_json);
  const payloadMaterial = {
    turnId: text(row.turn_id),
    role: text(row.role),
    surfaceKind: text(row.surface_kind),
    content: String(row.content),
    origin: text(row.origin),
    status: input.status,
    contentBlocks,
    resources,
    producingRunId: row.producing_run_id == null ? null : text(row.producing_run_id),
    remoteId: row.remote_id == null ? null : text(row.remote_id),
    metadataJson: input.metadataJson,
  };
  const payloadHash = `sha256:${createHash("sha256").update(stableRepairJson(payloadMaterial)).digest("hex")}`;
  db.prepare(
    `UPDATE conversation_turns
     SET turn_seq = ?, producer_id = ?, payload_hash = ?, status = ?, metadata_json = ?,
         updated_at_ms = ?, completed_at_ms = ?
     WHERE conversation_id = ? AND turn_id = ?`,
  ).run(
    turnSeq,
    producerId,
    payloadHash,
    input.status,
    input.metadataJson,
    input.nowMs,
    input.completedAtMs,
    conversationId,
    row.turn_id,
  );
  db.prepare(
    `UPDATE conversation_journal_state
     SET high_water_turn_seq = ?, updated_at_ms = ? WHERE conversation_id = ?`,
  ).run(turnSeq, input.nowMs, conversationId);
  const turnJson = JSON.stringify({
    conversationId,
    turnId: text(row.turn_id),
    turnSeq,
    producerId,
    payloadHash,
    role: text(row.role),
    surfaceKind: text(row.surface_kind),
    content: String(row.content),
    origin: text(row.origin),
    status: input.status,
    contentBlocks,
    resources,
    producingRunId: row.producing_run_id == null ? null : text(row.producing_run_id),
    remoteId: row.remote_id == null ? null : text(row.remote_id),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: input.nowMs,
    completedAtMs: input.completedAtMs,
    metadataJson: input.metadataJson,
  });
  db.prepare(
    `INSERT INTO conversation_turn_revisions(
       conversation_id, turn_seq, generation, turn_id, producer_id,
       mutation_kind, turn_json, payload_hash, created_at_ms
     ) VALUES (?, ?, ?, ?, ?, 'updated', ?, ?, ?)`,
  ).run(
    conversationId,
    turnSeq,
    Number(state.generation),
    row.turn_id,
    producerId,
    turnJson,
    payloadHash,
    input.nowMs,
  );
}

function repairMetadata(raw: unknown, repair: Record<string, unknown>): string {
  let metadata: Record<string, unknown> = {};
  try {
    const parsed = JSON.parse(String(raw ?? "{}")) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) metadata = parsed as Record<string, unknown>;
  } catch {
    // Existing SQLite constraints normally prevent this; repair still fails closed to an object.
  }
  return JSON.stringify({ ...metadata, startupRepair: repair });
}

function parseJsonArray(raw: unknown): unknown[] {
  try {
    const parsed = JSON.parse(String(raw ?? "[]")) as unknown;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function stableRepairJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableRepairJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stableRepairJson(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function runPhase1Migration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(phase1SchemaSql);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      PHASE_1_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runArtifactLifecycleMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    if (!tableHasColumn(db, "artifacts", "lifecycle_state")) {
      db.exec(`
        ALTER TABLE artifacts
          ADD COLUMN lifecycle_state TEXT NOT NULL DEFAULT 'retained' CHECK (lifecycle_state IN ('retained', 'dismissed', 'opened'));
      `);
    }
    if (!tableHasColumn(db, "artifacts", "lifecycle_updated_at_ms")) {
      db.exec(`
        ALTER TABLE artifacts
          ADD COLUMN lifecycle_updated_at_ms INTEGER;
      `);
    }
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      ARTIFACT_LIFECYCLE_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function tableHasColumn(db: Pick<DatabaseSync, "prepare">, tableName: string, columnName: string): boolean {
  const statement = db.prepare(`PRAGMA table_info(${tableName})`) as unknown as {
    all?: () => unknown[];
    iterate?: () => Iterable<unknown>;
  };
  const rows = statement.iterate ? Array.from(statement.iterate()) : (statement.all?.() ?? []);
  return rows
    .some((row) => String((row as Row).name) === columnName);
}

function runDesktopContextPacketsMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS desktop_context_packets(
        packet_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
        run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        surface_kind TEXT NOT NULL,
        objective TEXT NOT NULL,
        packet_json TEXT NOT NULL CHECK (json_valid(packet_json)),
        redacted_preview_json TEXT NOT NULL CHECK (json_valid(redacted_preview_json)),
        context_hash TEXT NOT NULL,
        token_estimate INTEGER,
        retention_class TEXT NOT NULL CHECK (retention_class IN ('ephemeral','debug','core')),
        expires_at_ms INTEGER,
        created_at_ms INTEGER NOT NULL
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_context_packets_owner_created_idx
        ON desktop_context_packets(owner_id, created_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_context_packets_session_created_idx
        ON desktop_context_packets(session_id, created_at_ms DESC)
        WHERE session_id IS NOT NULL;

      CREATE INDEX IF NOT EXISTS desktop_context_packets_expiry_idx
        ON desktop_context_packets(expires_at_ms)
        WHERE expires_at_ms IS NOT NULL;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      DESKTOP_CONTEXT_PACKETS_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runDesktopDispatchesMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS desktop_dispatches(
        dispatch_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN (
          'approval','routing_choice','failure_recovery','artifact_review',
          'memory_candidate','task_candidate','external_draft','screen_context'
        )),
        priority INTEGER NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending','resolved','expired','cancelled')),
        title TEXT NOT NULL,
        decision_prompt TEXT NOT NULL,
        recommended_default TEXT,
        source_session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
        source_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        source_attempt_id TEXT REFERENCES run_attempts(attempt_id) ON DELETE SET NULL,
        source_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
        capability TEXT,
        operation TEXT,
        resource_ref TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json)),
        created_at_ms INTEGER NOT NULL,
        expires_at_ms INTEGER,
        resolved_at_ms INTEGER,
        resolved_by TEXT,
        resolution_json TEXT CHECK (resolution_json IS NULL OR json_valid(resolution_json))
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_dispatches_owner_status_priority_idx
        ON desktop_dispatches(owner_id, status, priority DESC, created_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_dispatches_source_run_idx
        ON desktop_dispatches(source_run_id, status, created_at_ms DESC)
        WHERE source_run_id IS NOT NULL;

      CREATE INDEX IF NOT EXISTS desktop_dispatches_expiry_idx
        ON desktop_dispatches(status, expires_at_ms)
        WHERE expires_at_ms IS NOT NULL;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      DESKTOP_DISPATCHES_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runDesktopArtifactDeliveriesMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS desktop_artifact_deliveries(
        delivery_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
        owner_id TEXT NOT NULL,
        source_session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        source_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        source_attempt_id TEXT REFERENCES run_attempts(attempt_id) ON DELETE SET NULL,
        intended_surface TEXT NOT NULL,
        target_kind TEXT NOT NULL CHECK (target_kind IN ('ask_omi','task_chat','local_file','external_draft')),
        target_ref TEXT,
        content_hash TEXT,
        review_status TEXT NOT NULL CHECK (review_status IN ('not_required','pending','approved','rejected')),
        delivery_status TEXT NOT NULL CHECK (delivery_status IN ('pending','delivered','failed','retrying','cancelled')),
        attempt_count INTEGER NOT NULL DEFAULT 0,
        receipt_json TEXT CHECK (receipt_json IS NULL OR json_valid(receipt_json)),
        error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        delivered_at_ms INTEGER
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_artifact_deliveries_owner_status_idx
        ON desktop_artifact_deliveries(owner_id, delivery_status, updated_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_artifact_deliveries_artifact_idx
        ON desktop_artifact_deliveries(artifact_id, created_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_artifact_deliveries_source_idx
        ON desktop_artifact_deliveries(source_session_id, source_run_id, updated_at_ms DESC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      DESKTOP_ARTIFACT_DELIVERIES_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runDesktopCandidatesMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS desktop_memory_candidates(
        candidate_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        source_session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        source_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        source_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
        proposed_fact TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL CHECK (json_valid(evidence_refs_json)),
        confidence REAL NOT NULL,
        sensitivity_tier TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected','expired')),
        created_at_ms INTEGER NOT NULL,
        resolved_at_ms INTEGER
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_memory_candidates_owner_status_idx
        ON desktop_memory_candidates(owner_id, status, created_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_memory_candidates_source_idx
        ON desktop_memory_candidates(source_session_id, source_run_id, created_at_ms DESC);

      CREATE TABLE IF NOT EXISTS desktop_task_candidates(
        candidate_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        source_session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
        source_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        action TEXT NOT NULL CHECK (action IN ('create','update','complete','delete')),
        task_ref TEXT,
        proposed_change_json TEXT NOT NULL CHECK (json_valid(proposed_change_json)),
        evidence_refs_json TEXT NOT NULL CHECK (json_valid(evidence_refs_json)),
        confidence REAL NOT NULL,
        requires_approval INTEGER NOT NULL CHECK (requires_approval IN (0,1)),
        status TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected','expired')),
        created_at_ms INTEGER NOT NULL,
        resolved_at_ms INTEGER
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_task_candidates_owner_status_idx
        ON desktop_task_candidates(owner_id, status, created_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_task_candidates_task_idx
        ON desktop_task_candidates(task_ref, status, created_at_ms DESC)
        WHERE task_ref IS NOT NULL;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      DESKTOP_CANDIDATES_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runDesktopContextAccessLogMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS desktop_context_access_log(
        access_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        packet_id TEXT REFERENCES desktop_context_packets(packet_id) ON DELETE SET NULL,
        run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        source_kind TEXT NOT NULL CHECK (source_kind IN (
          'omi_db','rewind_timeline','screen_current','screenshot_image',
          'local_agent_api','automation_bridge','chat_surface','task_chat'
        )),
        operation TEXT NOT NULL,
        scope_json TEXT NOT NULL CHECK (json_valid(scope_json)),
        sensitivity_tier TEXT NOT NULL,
        policy_decision TEXT NOT NULL CHECK (policy_decision IN ('allowed','denied','dispatch_created')),
        dispatch_id TEXT REFERENCES desktop_dispatches(dispatch_id) ON DELETE SET NULL,
        redaction_summary_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(redaction_summary_json)),
        created_at_ms INTEGER NOT NULL
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_context_access_owner_created_idx
        ON desktop_context_access_log(owner_id, created_at_ms DESC);

      CREATE INDEX IF NOT EXISTS desktop_context_access_packet_idx
        ON desktop_context_access_log(packet_id, created_at_ms DESC)
        WHERE packet_id IS NOT NULL;

      CREATE INDEX IF NOT EXISTS desktop_context_access_run_idx
        ON desktop_context_access_log(run_id, created_at_ms DESC)
        WHERE run_id IS NOT NULL;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      DESKTOP_CONTEXT_ACCESS_LOG_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runDesktopAttentionOverridesMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS desktop_attention_overrides(
        owner_id TEXT NOT NULL,
        subject_kind TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        hidden_until_ms INTEGER,
        dismissed_at_ms INTEGER,
        reason TEXT,
        created_at_ms INTEGER NOT NULL,
        PRIMARY KEY(owner_id, subject_kind, subject_id)
      ) STRICT;

      CREATE INDEX IF NOT EXISTS desktop_attention_overrides_owner_hidden_idx
        ON desktop_attention_overrides(owner_id, hidden_until_ms);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      DESKTOP_ATTENTION_OVERRIDES_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runSurfaceConversationsMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS surface_conversations(
        owner_id TEXT NOT NULL,
        surface_kind TEXT NOT NULL,
        external_ref_kind TEXT NOT NULL,
        external_ref_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        agent_session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        created_at_ms INTEGER NOT NULL,
        last_active_at_ms INTEGER NOT NULL,
        PRIMARY KEY (owner_id, surface_kind, external_ref_kind, external_ref_id)
      ) STRICT;

      CREATE INDEX IF NOT EXISTS surface_conversations_session_idx
        ON surface_conversations(agent_session_id, last_active_at_ms DESC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      SURFACE_CONVERSATIONS_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runConversationTurnsMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE IF NOT EXISTS conversation_turns(
        conversation_id TEXT NOT NULL,
        turn_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        surface_kind TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (conversation_id, turn_id)
      ) STRICT;

      CREATE INDEX IF NOT EXISTS conversation_turns_recent_idx
        ON conversation_turns(conversation_id, created_at_ms DESC);

      CREATE TABLE IF NOT EXISTS completion_delta_checkpoints(
        owner_id TEXT NOT NULL,
        surface_key TEXT NOT NULL,
        seen_ids_json TEXT NOT NULL DEFAULT '[]',
        high_water_ms INTEGER NOT NULL DEFAULT 0,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY (owner_id, surface_key)
      ) STRICT;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      CONVERSATION_TURNS_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runBindingTurnDeliveryMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      BINDING_TURN_DELIVERY_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runWorkstreamContinuityMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      DROP INDEX IF EXISTS desktop_task_candidates_owner_status_idx;
      DROP INDEX IF EXISTS desktop_task_candidates_task_idx;
      ALTER TABLE desktop_task_candidates RENAME TO desktop_task_candidates_legacy;

      CREATE TABLE desktop_task_candidates(
        candidate_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        source_session_id TEXT REFERENCES sessions(session_id) ON DELETE SET NULL,
        source_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
        action TEXT NOT NULL CHECK (action IN ('create','update','complete','delete','supersede')),
        task_ref TEXT,
        proposed_change_json TEXT NOT NULL CHECK (json_valid(proposed_change_json)),
        evidence_refs_json TEXT NOT NULL CHECK (json_valid(evidence_refs_json)),
        confidence REAL NOT NULL,
        ownership_confidence REAL NOT NULL,
        requires_approval INTEGER NOT NULL CHECK (requires_approval IN (0,1)),
        goal_ref TEXT,
        workstream_ref TEXT,
        source_surface TEXT NOT NULL,
        account_generation INTEGER NOT NULL CHECK (account_generation >= 0),
        generation_reconciled INTEGER NOT NULL CHECK (generation_reconciled IN (0,1)),
        status TEXT NOT NULL CHECK (status IN ('pending','forwarded','accepted','rejected','expired')),
        delivery_status TEXT NOT NULL CHECK (delivery_status IN ('pending','delivering','delivered','failed','blocked')),
        delivery_attempt_count INTEGER NOT NULL DEFAULT 0,
        delivery_key TEXT NOT NULL UNIQUE,
        backend_candidate_id TEXT UNIQUE,
        backend_receipt_json TEXT CHECK (backend_receipt_json IS NULL OR json_valid(backend_receipt_json)),
        backend_resolution_receipt_json TEXT CHECK (backend_resolution_receipt_json IS NULL OR json_valid(backend_resolution_receipt_json)),
        backend_resolution_status TEXT,
        last_delivery_error_json TEXT CHECK (last_delivery_error_json IS NULL OR json_valid(last_delivery_error_json)),
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        delivered_at_ms INTEGER,
        resolved_at_ms INTEGER
      ) STRICT;

      INSERT INTO desktop_task_candidates (
        candidate_id, owner_id, source_session_id, source_run_id, action,
        task_ref, proposed_change_json, evidence_refs_json, confidence,
        ownership_confidence, requires_approval, goal_ref, workstream_ref,
        source_surface, account_generation, generation_reconciled, status, delivery_status, delivery_attempt_count,
        delivery_key, created_at_ms, updated_at_ms, resolved_at_ms
      )
      SELECT candidate_id, owner_id, source_session_id, source_run_id, action,
             task_ref, proposed_change_json, evidence_refs_json, confidence,
             confidence, requires_approval, NULL, NULL, 'desktop_agent', 0, 0,
             status, 'blocked', 0, candidate_id,
             created_at_ms, created_at_ms, resolved_at_ms
      FROM desktop_task_candidates_legacy;

      DROP TABLE desktop_task_candidates_legacy;

      CREATE INDEX desktop_task_candidates_owner_status_idx
        ON desktop_task_candidates(owner_id, status, created_at_ms DESC);
      CREATE INDEX desktop_task_candidates_delivery_idx
        ON desktop_task_candidates(owner_id, delivery_status, updated_at_ms ASC);
      CREATE INDEX desktop_task_candidates_task_idx
        ON desktop_task_candidates(task_ref, status, created_at_ms DESC)
        WHERE task_ref IS NOT NULL;

      CREATE TABLE workstream_artifact_versions(
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        logical_key TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        artifact_id TEXT NOT NULL UNIQUE REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
        supersedes_artifact_id TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
        evidence_refs_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(evidence_refs_json)),
        created_at_ms INTEGER NOT NULL,
        PRIMARY KEY(session_id, logical_key, version)
      ) STRICT;

      CREATE TABLE workstream_artifact_heads(
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        logical_key TEXT NOT NULL,
        artifact_id TEXT NOT NULL UNIQUE REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
        version INTEGER NOT NULL CHECK (version > 0),
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY(session_id, logical_key),
        FOREIGN KEY(session_id, logical_key, version)
          REFERENCES workstream_artifact_versions(session_id, logical_key, version)
          ON DELETE CASCADE
      ) STRICT;

      CREATE TABLE workstream_continuation_checkpoints(
        owner_id TEXT NOT NULL,
        workstream_id TEXT NOT NULL,
        source_runtime_id TEXT NOT NULL,
        checkpoint_id TEXT NOT NULL,
        checkpoint_json TEXT NOT NULL CHECK (json_valid(checkpoint_json)),
        last_event_sequence INTEGER NOT NULL CHECK (last_event_sequence >= 0),
        expires_at_ms INTEGER NOT NULL,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY(owner_id, workstream_id, source_runtime_id)
      ) STRICT;

      CREATE INDEX workstream_continuation_expiry_idx
        ON workstream_continuation_checkpoints(expires_at_ms);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      WORKSTREAM_CONTINUITY_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runActiveAttemptAuthorityMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    const repairedAttempts = db.prepare(`
      SELECT a.attempt_id, a.run_id, r.session_id
      FROM run_attempts a
      JOIN runs r ON r.run_id = a.run_id
      WHERE a.status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')
        AND EXISTS (
          SELECT 1
          FROM run_attempts newer
          WHERE newer.run_id = a.run_id
            AND newer.status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')
            AND newer.attempt_no > a.attempt_no
        )
      ORDER BY a.run_id ASC, a.attempt_no ASC
    `).all() as Row[];
    db.prepare(`
      UPDATE run_attempts
      SET status = ?,
          completed_at_ms = COALESCE(completed_at_ms, ?),
          updated_at_ms = ?
      WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')
        AND EXISTS (
          SELECT 1
          FROM run_attempts newer
          WHERE newer.run_id = run_attempts.run_id
            AND newer.status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling')
            AND newer.attempt_no > run_attempts.attempt_no
        );
    `).run("orphaned", appliedAtMs, appliedAtMs);
    for (const attempt of repairedAttempts) {
      db.prepare(
        `INSERT INTO events (
          event_id, session_id, run_id, attempt_id, type, retention_class,
          visibility, payload_json, created_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).run(
        generateAgentId("event"),
        text(attempt.session_id),
        text(attempt.run_id),
        text(attempt.attempt_id),
        "attempt.orphaned",
        "core",
        "internal",
        JSON.stringify({
          attemptId: text(attempt.attempt_id),
          reason: "active_attempt_authority_migration",
        }),
        appliedAtMs,
      );
    }
    db.exec(`
      CREATE UNIQUE INDEX IF NOT EXISTS run_attempts_one_active_per_run_uq
        ON run_attempts(run_id)
        WHERE status IN ('queued', 'starting', 'running', 'waiting_input', 'waiting_approval', 'cancelling');
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      ACTIVE_ATTEMPT_AUTHORITY_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runSessionExecutionPolicyMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    db.exec(`
      ALTER TABLE sessions
        ADD COLUMN execution_role TEXT NOT NULL DEFAULT 'coordinator'
        CHECK (execution_role IN ('coordinator', 'leaf'));
      ALTER TABLE sessions
        ADD COLUMN provider_boundary TEXT NOT NULL DEFAULT 'local_user:acp';
      UPDATE sessions
      SET execution_role = CASE
        WHEN surface_kind IN ('delegated_agent', 'background_agent')
          OR (surface_kind = 'floating_bar' AND external_ref_kind = 'pill')
        THEN 'leaf'
        ELSE 'coordinator'
      END,
      provider_boundary = CASE
        WHEN default_adapter_id = 'pi-mono' THEN 'managed_cloud'
        ELSE 'local_user:' || default_adapter_id
      END;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      SESSION_EXECUTION_POLICY_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runConversationJournalMigration(db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">, appliedAtMs: number): void {
  runTransaction(db, () => {
    if (!tableHasColumn(db, "conversation_turns", "origin")) {
      db.exec(`
        ALTER TABLE conversation_turns
          ADD COLUMN origin TEXT NOT NULL DEFAULT 'legacy';
        ALTER TABLE conversation_turns
          ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'
          CHECK (status IN ('pending', 'streaming', 'completed', 'failed'));
        ALTER TABLE conversation_turns
          ADD COLUMN content_blocks_json TEXT NOT NULL DEFAULT '[]'
          CHECK (json_valid(content_blocks_json));
        ALTER TABLE conversation_turns
          ADD COLUMN resources_json TEXT NOT NULL DEFAULT '[]'
          CHECK (json_valid(resources_json));
        ALTER TABLE conversation_turns
          ADD COLUMN producing_run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL;
        ALTER TABLE conversation_turns
          ADD COLUMN remote_id TEXT;
        ALTER TABLE conversation_turns
          ADD COLUMN updated_at_ms INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE conversation_turns
          ADD COLUMN completed_at_ms INTEGER;
      `);
    }

    db.exec(`
      UPDATE conversation_turns
      SET origin = CASE
            WHEN origin != 'legacy' THEN origin
            WHEN json_extract(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.origin') = 'realtime_voice'
              THEN 'realtime_voice'
            WHEN json_extract(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.origin') IN ('floating_spawn', 'pill_completion')
              THEN 'agent_runtime'
            WHEN json_extract(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.source') = 'swift_backfill'
              THEN 'swift_backfill'
            ELSE origin
          END,
          content_blocks_json = CASE
            WHEN content_blocks_json != '[]' THEN content_blocks_json
            WHEN json_type(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.content_blocks') = 'array'
              THEN json_extract(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.content_blocks')
            WHEN content != ''
              THEN json_array(json_object('type', 'text', 'id', turn_id || ':text', 'text', content))
            ELSE '[]'
          END,
          resources_json = CASE
            WHEN resources_json != '[]' THEN resources_json
            WHEN json_type(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.resources') = 'array'
              THEN json_extract(CASE WHEN json_valid(metadata_json) THEN metadata_json ELSE '{}' END, '$.resources')
            ELSE '[]'
          END,
          updated_at_ms = CASE WHEN updated_at_ms = 0 THEN created_at_ms ELSE updated_at_ms END,
          completed_at_ms = CASE
            WHEN status IN ('completed', 'failed') THEN COALESCE(completed_at_ms, created_at_ms)
            ELSE completed_at_ms
          END;

      CREATE INDEX IF NOT EXISTS conversation_turns_status_recent_idx
        ON conversation_turns(conversation_id, status, created_at_ms ASC);
      CREATE INDEX IF NOT EXISTS conversation_turns_producing_run_idx
        ON conversation_turns(producing_run_id, created_at_ms ASC)
        WHERE producing_run_id IS NOT NULL;
      CREATE UNIQUE INDEX IF NOT EXISTS conversation_turns_remote_id_uq
        ON conversation_turns(conversation_id, remote_id)
        WHERE remote_id IS NOT NULL;

      CREATE TABLE IF NOT EXISTS backend_turn_outbox(
        turn_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        client_message_id TEXT NOT NULL UNIQUE CHECK (client_message_id = turn_id),
        status TEXT NOT NULL CHECK (status IN ('pending', 'delivering', 'retrying', 'delivered', 'failed')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        available_at_ms INTEGER NOT NULL,
        lease_expires_at_ms INTEGER,
        remote_id TEXT,
        last_error_code TEXT CHECK (last_error_code IS NULL OR length(last_error_code) <= 128),
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        delivered_at_ms INTEGER,
        FOREIGN KEY(conversation_id, turn_id)
          REFERENCES conversation_turns(conversation_id, turn_id) ON DELETE CASCADE
      ) STRICT;

      CREATE INDEX IF NOT EXISTS backend_turn_outbox_drain_idx
        ON backend_turn_outbox(status, available_at_ms ASC, created_at_ms ASC);
      CREATE INDEX IF NOT EXISTS backend_turn_outbox_owner_status_idx
        ON backend_turn_outbox(owner_id, status, updated_at_ms DESC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      CONVERSATION_JOURNAL_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runSessionExecutionProfileMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE session_execution_profiles(
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        generation INTEGER NOT NULL CHECK (generation > 0),
        adapter_id TEXT NOT NULL,
        credential_scope TEXT NOT NULL CHECK (credential_scope IN ('managed_cloud', 'local_user')),
        model_profile TEXT,
        execution_role TEXT NOT NULL CHECK (execution_role IN ('coordinator', 'leaf')),
        source TEXT NOT NULL CHECK (source IN ('creation', 'migration', 'child_derivation', 'legacy_backfill')),
        audit_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(audit_json)),
        created_at_ms INTEGER NOT NULL,
        PRIMARY KEY(session_id, generation)
      ) STRICT;

      CREATE TRIGGER session_execution_profiles_immutable_update
      BEFORE UPDATE ON session_execution_profiles
      BEGIN
        SELECT RAISE(ABORT, 'session execution profiles are immutable');
      END;

      ALTER TABLE sessions
        ADD COLUMN current_profile_generation INTEGER NOT NULL DEFAULT 1 CHECK (current_profile_generation > 0);
      ALTER TABLE runs
        ADD COLUMN profile_generation INTEGER NOT NULL DEFAULT 1 CHECK (profile_generation > 0);
      ALTER TABLE run_attempts
        ADD COLUMN profile_generation INTEGER NOT NULL DEFAULT 1 CHECK (profile_generation > 0);
      ALTER TABLE adapter_bindings
        ADD COLUMN profile_generation INTEGER NOT NULL DEFAULT 1 CHECK (profile_generation > 0);

      INSERT INTO session_execution_profiles(
        session_id, generation, adapter_id, credential_scope, model_profile,
        execution_role, source, audit_json, created_at_ms
      )
      SELECT session_id,
             1,
             default_adapter_id,
             CASE WHEN provider_boundary = 'managed_cloud' THEN 'managed_cloud' ELSE 'local_user' END,
             model_profile,
             execution_role,
             'legacy_backfill',
             json_object(
               'legacyProjection', json_object(
                 'readAuthority', 0,
                 'owner', 'desktop-kernel',
                 'removalCondition', 'all supported desktop versions write immutable session execution profiles',
                 'removeBy', '2026-10-01'
               )
             ),
             created_at_ms
      FROM sessions;

      CREATE INDEX session_execution_profiles_current_idx
        ON session_execution_profiles(session_id, generation DESC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      SESSION_EXECUTION_PROFILE_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runConversationJournalSequenceMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      ALTER TABLE conversation_turns
        ADD COLUMN turn_seq INTEGER NOT NULL DEFAULT 0 CHECK (turn_seq >= 0);
      ALTER TABLE conversation_turns
        ADD COLUMN producer_id TEXT;
      ALTER TABLE conversation_turns
        ADD COLUMN payload_hash TEXT;

      WITH ranked AS (
        SELECT conversation_id, turn_id,
               ROW_NUMBER() OVER (
                 PARTITION BY conversation_id
                 ORDER BY created_at_ms ASC, turn_id ASC
               ) AS seq
        FROM conversation_turns
      )
      UPDATE conversation_turns
      SET turn_seq = (
            SELECT seq FROM ranked
            WHERE ranked.conversation_id = conversation_turns.conversation_id
              AND ranked.turn_id = conversation_turns.turn_id
          ),
          producer_id = COALESCE(producer_id, 'legacy:' || turn_id),
          payload_hash = COALESCE(payload_hash, 'legacy');

      CREATE UNIQUE INDEX conversation_turns_sequence_uq
        ON conversation_turns(conversation_id, turn_seq)
        WHERE turn_seq > 0;
      CREATE UNIQUE INDEX conversation_turns_producer_uq
        ON conversation_turns(conversation_id, producer_id)
        WHERE producer_id IS NOT NULL;

      CREATE TABLE conversation_journal_state(
        conversation_id TEXT PRIMARY KEY,
        generation INTEGER NOT NULL DEFAULT 1 CHECK (generation > 0),
        high_water_turn_seq INTEGER NOT NULL DEFAULT 0 CHECK (high_water_turn_seq >= 0),
        cleared_at_ms INTEGER,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;

      INSERT INTO conversation_journal_state(
        conversation_id, generation, high_water_turn_seq, updated_at_ms
      )
      SELECT sc.conversation_id, 1, COALESCE(MAX(ct.turn_seq), 0), ${Math.floor(appliedAtMs)}
      FROM surface_conversations sc
      LEFT JOIN conversation_turns ct ON ct.conversation_id = sc.conversation_id
      GROUP BY sc.conversation_id;

      CREATE TABLE conversation_turn_revisions(
        conversation_id TEXT NOT NULL,
        turn_seq INTEGER NOT NULL CHECK (turn_seq > 0),
        generation INTEGER NOT NULL CHECK (generation > 0),
        turn_id TEXT NOT NULL,
        producer_id TEXT NOT NULL,
        mutation_kind TEXT NOT NULL CHECK (mutation_kind IN ('recorded', 'updated', 'imported')),
        turn_json TEXT NOT NULL CHECK (json_valid(turn_json)),
        payload_hash TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL,
        PRIMARY KEY(conversation_id, turn_seq)
      ) STRICT;

      INSERT INTO conversation_turn_revisions(
        conversation_id, turn_seq, generation, turn_id, producer_id,
        mutation_kind, turn_json, payload_hash, created_at_ms
      )
      SELECT conversation_id,
             turn_seq,
             1,
             turn_id,
             producer_id,
             'imported',
             json_object(
               'conversationId', conversation_id,
               'turnId', turn_id,
               'turnSeq', turn_seq,
               'producerId', producer_id,
               'role', role,
               'surfaceKind', surface_kind,
               'content', content,
               'origin', origin,
               'status', status,
               'contentBlocks', json(content_blocks_json),
               'resources', json(resources_json),
               'producingRunId', producing_run_id,
               'remoteId', remote_id,
               'createdAtMs', created_at_ms,
               'updatedAtMs', updated_at_ms,
               'completedAtMs', completed_at_ms,
               'metadataJson', metadata_json
             ),
             payload_hash,
             updated_at_ms
      FROM conversation_turns;

      ALTER TABLE backend_turn_outbox
        ADD COLUMN payload_hash TEXT NOT NULL DEFAULT 'uncomputed';
      ALTER TABLE backend_turn_outbox
        ADD COLUMN delivery_generation INTEGER NOT NULL DEFAULT 0 CHECK (delivery_generation >= 0);
      ALTER TABLE backend_turn_outbox
        ADD COLUMN conversation_generation INTEGER NOT NULL DEFAULT 1 CHECK (conversation_generation > 0);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      CONVERSATION_JOURNAL_SEQUENCE_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runToolInvocationLedgerMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE tool_invocation_ledger(
        invocation_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
        attempt_id TEXT NOT NULL REFERENCES run_attempts(attempt_id) ON DELETE CASCADE,
        profile_generation INTEGER NOT NULL CHECK (profile_generation > 0),
        manifest_version INTEGER NOT NULL CHECK (manifest_version > 0),
        daemon_boot_epoch TEXT NOT NULL,
        execution_generation INTEGER NOT NULL CHECK (execution_generation > 0),
        tool_name TEXT NOT NULL,
        input_hash TEXT NOT NULL,
        effect_class TEXT NOT NULL CHECK (effect_class IN ('read_only', 'idempotent_write', 'non_idempotent_write')),
        retry_policy TEXT NOT NULL CHECK (retry_policy IN ('safe_retry', 'never_auto_retry')),
        status TEXT NOT NULL CHECK (status IN ('prepared', 'dispatched', 'succeeded', 'failed', 'outcome_unknown')),
        result_hash TEXT,
        error_code TEXT CHECK (error_code IS NULL OR length(error_code) <= 128),
        prepared_at_ms INTEGER NOT NULL,
        dispatched_at_ms INTEGER,
        completed_at_ms INTEGER,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;

      CREATE INDEX tool_invocation_ledger_attempt_idx
        ON tool_invocation_ledger(attempt_id, status, prepared_at_ms ASC);
      CREATE INDEX tool_invocation_ledger_status_idx
        ON tool_invocation_ledger(status, updated_at_ms ASC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      TOOL_INVOCATION_LEDGER_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runKernelContextAuthorityMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      ALTER TABLE session_execution_profiles
        ADD COLUMN working_directory TEXT NOT NULL DEFAULT '';
      ALTER TABLE tool_invocation_ledger
        ADD COLUMN manifest_digest TEXT NOT NULL DEFAULT 'legacy';

      CREATE TABLE default_execution_profile_preferences(
        owner_id TEXT PRIMARY KEY,
        generation INTEGER NOT NULL CHECK (generation > 0),
        adapter_id TEXT NOT NULL,
        credential_scope TEXT NOT NULL CHECK (credential_scope IN ('managed_cloud', 'local_user')),
        model_profile TEXT,
        working_directory TEXT NOT NULL,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;

      CREATE TABLE context_source_state(
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        source TEXT NOT NULL CHECK (source IN ('identity', 'memories', 'goals', 'tasks', 'screen', 'workspace', 'surface')),
        source_revision TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('available', 'empty', 'unavailable', 'redacted')),
        captured_at_ms INTEGER NOT NULL,
        expires_at_ms INTEGER,
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_hash TEXT NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY(session_id, source)
      ) STRICT;

      CREATE TABLE context_snapshot_state(
        session_id TEXT PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
        snapshot_generation INTEGER NOT NULL CHECK (snapshot_generation > 0),
        snapshot_version TEXT NOT NULL,
        renderer_fingerprint TEXT NOT NULL,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      KERNEL_CONTEXT_AUTHORITY_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runJournalGenerationBaseMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      ALTER TABLE conversation_journal_state
        ADD COLUMN generation_base_turn_seq INTEGER NOT NULL DEFAULT 0
        CHECK (generation_base_turn_seq >= 0);
      UPDATE conversation_journal_state
      SET generation_base_turn_seq = CASE
        WHEN generation = 1 THEN 0
        ELSE COALESCE(
          (SELECT MIN(r.turn_seq) - 1
           FROM conversation_turn_revisions r
           WHERE r.conversation_id = conversation_journal_state.conversation_id
             AND r.generation = conversation_journal_state.generation),
          high_water_turn_seq
        )
      END;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      JOURNAL_GENERATION_BASE_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runOwnerContextSnapshotMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE context_owner_snapshot_state(
        owner_id TEXT PRIMARY KEY,
        snapshot_generation INTEGER NOT NULL CHECK (snapshot_generation > 0),
        snapshot_version TEXT NOT NULL,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      OWNER_CONTEXT_SNAPSHOT_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runBackendConversationDeleteOutboxMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE backend_conversation_delete_outbox(
        operation_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        target_kind TEXT NOT NULL CHECK (target_kind IN ('messages', 'chat_session')),
        target_id TEXT,
        conversation_generation INTEGER NOT NULL CHECK (conversation_generation > 0),
        status TEXT NOT NULL CHECK (status IN ('pending', 'delivering', 'retrying', 'delivered', 'failed')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        delivery_generation INTEGER NOT NULL DEFAULT 0 CHECK (delivery_generation >= 0),
        payload_hash TEXT NOT NULL,
        available_at_ms INTEGER NOT NULL,
        lease_expires_at_ms INTEGER,
        last_error_code TEXT,
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        delivered_at_ms INTEGER,
        UNIQUE(conversation_id, conversation_generation)
      ) STRICT;
      CREATE INDEX backend_conversation_delete_outbox_drain_idx
        ON backend_conversation_delete_outbox(owner_id, status, available_at_ms ASC, created_at_ms ASC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      BACKEND_CONVERSATION_DELETE_OUTBOX_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runBackendReconcileStateMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      CREATE TABLE backend_reconcile_state(
        conversation_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        conversation_generation INTEGER NOT NULL DEFAULT 1 CHECK (conversation_generation > 0),
        frontier_remote_id TEXT,
        candidate_frontier_remote_id TEXT,
        in_flight_id TEXT,
        page_cursor TEXT,
        page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
        status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'fetching', 'failed')),
        last_error_code TEXT,
        last_requested_at_ms INTEGER,
        last_completed_at_ms INTEGER,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;
      CREATE INDEX backend_reconcile_state_owner_status_idx
        ON backend_reconcile_state(owner_id, status, updated_at_ms ASC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      BACKEND_RECONCILE_STATE_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runClearedBackendTurnClaimsMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    if (!tableHasColumn(db, "backend_reconcile_state", "conversation_generation")) {
      db.exec(
        "ALTER TABLE backend_reconcile_state ADD COLUMN conversation_generation INTEGER NOT NULL DEFAULT 1 CHECK (conversation_generation > 0)",
      );
    }
    db.exec(`
      CREATE TABLE cleared_backend_turn_claims(
        turn_id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
        delivery_generation INTEGER NOT NULL CHECK (delivery_generation > 0),
        conversation_generation INTEGER NOT NULL CHECK (conversation_generation > 0),
        payload_hash TEXT NOT NULL,
        lease_expires_at_ms INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting', 'settled')),
        result_outcome TEXT CHECK (result_outcome IS NULL OR result_outcome IN ('succeeded', 'failed', 'expired')),
        created_at_ms INTEGER NOT NULL,
        settled_at_ms INTEGER
      ) STRICT;
      CREATE INDEX cleared_backend_turn_claims_conversation_status_idx
        ON cleared_backend_turn_claims(conversation_id, status, lease_expires_at_ms ASC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      CLEARED_BACKEND_TURN_CLAIMS_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runContextSourceSurfaceScopeMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      ALTER TABLE context_source_state RENAME TO context_source_state_legacy;
      CREATE TABLE context_source_state(
        session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        source TEXT NOT NULL CHECK (source IN ('identity', 'memories', 'goals', 'tasks', 'screen', 'workspace', 'surface')),
        surface_kind TEXT NOT NULL DEFAULT '',
        source_revision TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('available', 'empty', 'unavailable', 'redacted')),
        captured_at_ms INTEGER NOT NULL,
        expires_at_ms INTEGER,
        payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
        payload_hash TEXT NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        PRIMARY KEY(session_id, source, surface_kind),
        CHECK ((source = 'surface' AND surface_kind != '') OR (source != 'surface' AND surface_kind = ''))
      ) STRICT;
      INSERT INTO context_source_state(
        session_id, source, surface_kind, source_revision, outcome, captured_at_ms,
        expires_at_ms, payload_json, payload_hash, updated_at_ms
      )
      SELECT legacy.session_id, legacy.source,
             CASE WHEN legacy.source = 'surface' THEN sessions.surface_kind ELSE '' END,
             legacy.source_revision, legacy.outcome, legacy.captured_at_ms,
             legacy.expires_at_ms, legacy.payload_json, legacy.payload_hash, legacy.updated_at_ms
      FROM context_source_state_legacy legacy
      JOIN sessions ON sessions.session_id = legacy.session_id;
      DROP TABLE context_source_state_legacy;
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      CONTEXT_SOURCE_SURFACE_SCOPE_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runBackendReconcileCursorMigration(
  db: Pick<DatabaseSync, "exec" | "prepare" | "isTransaction">,
  appliedAtMs: number,
): void {
  runTransaction(db, () => {
    db.exec(`
      ALTER TABLE backend_reconcile_state RENAME TO backend_reconcile_state_legacy;
      CREATE TABLE backend_reconcile_state(
        conversation_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        conversation_generation INTEGER NOT NULL DEFAULT 1 CHECK (conversation_generation > 0),
        frontier_remote_id TEXT,
        candidate_frontier_remote_id TEXT,
        in_flight_id TEXT,
        page_cursor TEXT,
        page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
        status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'fetching', 'failed')),
        last_error_code TEXT,
        last_requested_at_ms INTEGER,
        last_completed_at_ms INTEGER,
        updated_at_ms INTEGER NOT NULL
      ) STRICT;
      INSERT INTO backend_reconcile_state(
        conversation_id, owner_id, conversation_generation, frontier_remote_id,
        candidate_frontier_remote_id, in_flight_id, page_cursor, page_count, status,
        last_error_code, last_requested_at_ms, last_completed_at_ms, updated_at_ms
      )
      SELECT conversation_id, owner_id, conversation_generation, frontier_remote_id,
             NULL, NULL, NULL, 0,
             CASE WHEN status = 'fetching' THEN 'idle' ELSE status END,
             CASE WHEN status = 'fetching' THEN 'cursor_migration' ELSE last_error_code END,
             last_requested_at_ms, last_completed_at_ms, updated_at_ms
      FROM backend_reconcile_state_legacy;
      DROP TABLE backend_reconcile_state_legacy;
      CREATE INDEX backend_reconcile_state_owner_status_idx
        ON backend_reconcile_state(owner_id, status, updated_at_ms ASC);
    `);
    db.prepare("INSERT INTO schema_migrations (version, applied_at_ms) VALUES (?, ?)").run(
      BACKEND_RECONCILE_CURSOR_MIGRATION_VERSION,
      appliedAtMs,
    );
  });
}

function runTransaction<T>(db: Pick<DatabaseSync, "exec" | "isTransaction">, work: () => T): T {
  if (db.isTransaction) {
    return work();
  }
  db.exec("BEGIN IMMEDIATE");
  try {
    const result = work();
    db.exec("COMMIT");
    return result;
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }
}

function sessionIdForRun(db: Pick<DatabaseSync, "prepare">, runId: string): string {
  const row = db.prepare("SELECT session_id FROM runs WHERE run_id = ?").get(runId);
  if (!row) {
    throw new Error(`Run ${runId} has no session`);
  }
  return text(row.session_id);
}

function placeholders(count: number): string {
  return Array.from({ length: count }, () => "?").join(", ");
}

function text(value: SQLOutputValue): string {
  if (typeof value !== "string") {
    throw new Error(`Expected SQLite text value, got ${typeof value}`);
  }
  return value;
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function sessionValues(session: AgentSession): SQLInputValue[] {
  return [
    session.sessionId,
    session.ownerId,
    session.agentDefinitionId,
    session.title,
    session.status,
    session.surfaceKind,
    session.executionRole,
    session.providerBoundary,
    session.externalRefKind,
    session.externalRefId,
    null,
    null,
    session.defaultAdapterId,
    session.defaultCwd,
    session.modelProfile,
    session.metadataJson,
    session.createdAtMs,
    session.updatedAtMs,
    session.lastActivityAtMs,
    session.executionProfileGeneration,
  ];
}

function runValues(run: AgentRun): SQLInputValue[] {
  return [
    run.runId,
    run.sessionId,
    run.parentRunId,
    run.clientId,
    run.requestId,
    run.idempotencyKey,
    run.status,
    run.mode,
    run.profileGeneration,
    run.inputJson,
    run.systemPromptHash,
    run.modelProfile,
    run.requestedModelId,
    run.cwd,
    run.finalText,
    run.resultJson,
    run.errorCode,
    run.errorMessage,
    run.inputTokens,
    run.outputTokens,
    run.cacheReadTokens,
    run.cacheWriteTokens,
    run.costUsd,
    run.createdAtMs,
    run.startedAtMs,
    run.completedAtMs,
    run.updatedAtMs,
  ];
}

function attemptValues(attempt: RunAttempt): SQLInputValue[] {
  return [
    attempt.attemptId,
    attempt.runId,
    attempt.attemptNo,
    attempt.profileGeneration,
    attempt.status,
    attempt.adapterId,
    attempt.adapterInstanceId,
    attempt.runtimeNodeId,
    attempt.bindingId,
    attempt.adapterNativeRunId,
    attempt.resumeFromAttemptId,
    attempt.checkpointArtifactId,
    attempt.retryReason,
    attempt.retryable,
    attempt.cancellationRequestedAtMs,
    attempt.cancellationDispatchedAtMs,
    attempt.cancellationAcknowledgedAtMs,
    attempt.startedAtMs,
    attempt.completedAtMs,
    attempt.errorCode,
    attempt.errorMessage,
    attempt.metadataJson,
    attempt.createdAtMs,
    attempt.updatedAtMs,
  ];
}

function bindingValues(binding: AdapterBinding): SQLInputValue[] {
  return [
    binding.bindingId,
    binding.sessionId,
    binding.adapterId,
    binding.bindingGeneration,
    binding.profileGeneration,
    binding.adapterNativeSessionId,
    binding.adapterInstanceId,
    binding.resumeFidelity,
    binding.status,
    binding.cwd,
    binding.modelId,
    binding.systemPromptHash,
    binding.metadataJson,
    binding.createdAtMs,
    binding.updatedAtMs,
    binding.lastUsedAtMs,
    binding.invalidatedAtMs,
  ];
}

function eventValues(event: AgentEvent): SQLInputValue[] {
  return [
    event.eventId,
    event.sessionId,
    event.runId,
    event.attemptId,
    event.type,
    event.retentionClass,
    event.visibility,
    event.payloadJson,
    event.createdAtMs,
  ];
}

function artifactValues(artifact: AgentArtifact): SQLInputValue[] {
  return [
    artifact.artifactId,
    artifact.sessionId,
    artifact.runId,
    artifact.attemptId,
    artifact.kind,
    artifact.role,
    artifact.uri,
    artifact.displayName,
    artifact.mimeType,
    artifact.contentHash,
    artifact.sizeBytes,
    artifact.lifecycleState,
    artifact.lifecycleUpdatedAtMs,
    artifact.metadataJson,
    artifact.createdAtMs,
  ];
}

function grantValues(grant: AgentGrant): SQLInputValue[] {
  return [
    grant.grantId,
    grant.sessionId,
    grant.runId,
    grant.capability,
    grant.operation,
    grant.resourcePattern,
    grant.effect,
    grant.source,
    grant.constraintsJson,
    grant.createdAtMs,
    grant.expiresAtMs,
    grant.revokedAtMs,
  ];
}

function desktopContextPacketValues(packet: DesktopContextPacket): SQLInputValue[] {
  return [
    packet.packetId,
    packet.ownerId,
    packet.sessionId,
    packet.runId,
    packet.surfaceKind,
    packet.objective,
    packet.packetJson,
    packet.redactedPreviewJson,
    packet.contextHash,
    packet.tokenEstimate,
    packet.retentionClass,
    packet.expiresAtMs,
    packet.createdAtMs,
  ];
}

function desktopDispatchValues(dispatch: DesktopCoordinatorDispatch): SQLInputValue[] {
  return [
    dispatch.dispatchId,
    dispatch.ownerId,
    dispatch.kind,
    dispatch.priority,
    dispatch.status,
    dispatch.title,
    dispatch.decisionPrompt,
    dispatch.recommendedDefault,
    dispatch.sourceSessionId,
    dispatch.sourceRunId,
    dispatch.sourceAttemptId,
    dispatch.sourceArtifactId,
    dispatch.capability,
    dispatch.operation,
    dispatch.resourceRef,
    dispatch.payloadJson,
    dispatch.createdAtMs,
    dispatch.expiresAtMs,
    dispatch.resolvedAtMs,
    dispatch.resolvedBy,
    dispatch.resolutionJson,
  ];
}

function desktopArtifactDeliveryValues(delivery: DesktopArtifactDelivery): SQLInputValue[] {
  return [
    delivery.deliveryId,
    delivery.artifactId,
    delivery.ownerId,
    delivery.sourceSessionId,
    delivery.sourceRunId,
    delivery.sourceAttemptId,
    delivery.intendedSurface,
    delivery.targetKind,
    delivery.targetRef,
    delivery.contentHash,
    delivery.reviewStatus,
    delivery.deliveryStatus,
    delivery.attemptCount,
    delivery.receiptJson,
    delivery.errorJson,
    delivery.createdAtMs,
    delivery.updatedAtMs,
    delivery.deliveredAtMs,
  ];
}

function desktopMemoryCandidateValues(candidate: DesktopMemoryCandidate): SQLInputValue[] {
  return [
    candidate.candidateId,
    candidate.ownerId,
    candidate.sourceSessionId,
    candidate.sourceRunId,
    candidate.sourceArtifactId,
    candidate.proposedFact,
    candidate.evidenceRefsJson,
    candidate.confidence,
    candidate.sensitivityTier,
    candidate.status,
    candidate.createdAtMs,
    candidate.resolvedAtMs,
  ];
}

function desktopTaskCandidateValues(candidate: DesktopTaskCandidate): SQLInputValue[] {
  return [
    candidate.candidateId,
    candidate.ownerId,
    candidate.sourceSessionId,
    candidate.sourceRunId,
    candidate.action,
    candidate.taskRef,
    candidate.proposedChangeJson,
    candidate.evidenceRefsJson,
    candidate.confidence,
    candidate.ownershipConfidence,
    candidate.requiresApproval,
    candidate.goalRef,
    candidate.workstreamRef,
    candidate.sourceSurface,
    candidate.accountGeneration,
    candidate.generationReconciled,
    candidate.status,
    candidate.deliveryStatus,
    candidate.deliveryAttemptCount,
    candidate.deliveryKey,
    candidate.backendCandidateId,
    candidate.backendReceiptJson,
    candidate.backendResolutionReceiptJson,
    candidate.backendResolutionStatus,
    candidate.lastDeliveryErrorJson,
    candidate.createdAtMs,
    candidate.updatedAtMs,
    candidate.deliveredAtMs,
    candidate.resolvedAtMs,
  ];
}

function desktopContextAccessLogValues(access: DesktopContextAccessLog): SQLInputValue[] {
  return [
    access.accessId,
    access.ownerId,
    access.packetId,
    access.runId,
    access.sourceKind,
    access.operation,
    access.scopeJson,
    access.sensitivityTier,
    access.policyDecision,
    access.dispatchId,
    access.redactionSummaryJson,
    access.createdAtMs,
  ];
}

function desktopAttentionOverrideValues(override: DesktopAttentionOverride): SQLInputValue[] {
  return [
    override.ownerId,
    override.subjectKind,
    override.subjectId,
    override.hiddenUntilMs,
    override.dismissedAtMs,
    override.reason,
    override.createdAtMs,
  ];
}

function desktopAttentionOverrideFromRow(row: Row): DesktopAttentionOverride {
  return {
    ownerId: text(row.owner_id),
    subjectKind: text(row.subject_kind) as DesktopAttentionOverride["subjectKind"],
    subjectId: text(row.subject_id),
    hiddenUntilMs: nullableNumber(row.hidden_until_ms),
    dismissedAtMs: nullableNumber(row.dismissed_at_ms),
    reason: nullableText(row.reason),
    createdAtMs: Number(row.created_at_ms),
  };
}

function desktopDispatchFromRow(row: Row): DesktopCoordinatorDispatch {
  return {
    dispatchId: text(row.dispatch_id),
    ownerId: text(row.owner_id),
    kind: text(row.kind) as DesktopCoordinatorDispatch["kind"],
    priority: Number(row.priority),
    status: text(row.status) as DesktopCoordinatorDispatch["status"],
    title: text(row.title),
    decisionPrompt: text(row.decision_prompt),
    recommendedDefault: nullableText(row.recommended_default),
    sourceSessionId: nullableText(row.source_session_id),
    sourceRunId: nullableText(row.source_run_id),
    sourceAttemptId: nullableText(row.source_attempt_id),
    sourceArtifactId: nullableText(row.source_artifact_id),
    capability: nullableText(row.capability),
    operation: nullableText(row.operation),
    resourceRef: nullableText(row.resource_ref),
    payloadJson: text(row.payload_json),
    createdAtMs: Number(row.created_at_ms),
    expiresAtMs: nullableNumber(row.expires_at_ms),
    resolvedAtMs: nullableNumber(row.resolved_at_ms),
    resolvedBy: nullableText(row.resolved_by),
    resolutionJson: nullableText(row.resolution_json),
  };
}

function desktopArtifactDeliveryFromRow(row: Row): DesktopArtifactDelivery {
  return {
    deliveryId: text(row.delivery_id),
    artifactId: text(row.artifact_id),
    ownerId: text(row.owner_id),
    sourceSessionId: text(row.source_session_id),
    sourceRunId: nullableText(row.source_run_id),
    sourceAttemptId: nullableText(row.source_attempt_id),
    intendedSurface: text(row.intended_surface),
    targetKind: text(row.target_kind) as DesktopArtifactDelivery["targetKind"],
    targetRef: nullableText(row.target_ref),
    contentHash: nullableText(row.content_hash),
    reviewStatus: text(row.review_status) as DesktopArtifactDelivery["reviewStatus"],
    deliveryStatus: text(row.delivery_status) as DesktopArtifactDelivery["deliveryStatus"],
    attemptCount: Number(row.attempt_count),
    receiptJson: nullableText(row.receipt_json),
    errorJson: nullableText(row.error_json),
    createdAtMs: Number(row.created_at_ms),
    updatedAtMs: Number(row.updated_at_ms),
    deliveredAtMs: nullableNumber(row.delivered_at_ms),
  };
}

function nullableText(value: SQLOutputValue): string | null {
  if (value === null) return null;
  return text(value);
}

function nullableNumber(value: SQLOutputValue): number | null {
  if (value === null) return null;
  if (typeof value !== "number") {
    throw new Error(`Expected SQLite number value, got ${typeof value}`);
  }
  return value;
}
