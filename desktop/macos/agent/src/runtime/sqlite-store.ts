import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
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
  NewAgentRun,
  NewAgentSession,
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
      const activeAttempts = this.allRows(
        `SELECT attempt_id, run_id FROM run_attempts WHERE status IN (${placeholders(ACTIVE_ATTEMPT_STATUSES.length)})`,
        [...ACTIVE_ATTEMPT_STATUSES],
      );
      const staleBindings = this.allRows(
        "SELECT binding_id, session_id FROM adapter_bindings WHERE status = ? AND resume_fidelity = ?",
        ["active", "none"],
      );

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

      const expiredContextPacketIds = this.allRows(
        "SELECT packet_id FROM desktop_context_packets WHERE expires_at_ms IS NOT NULL AND expires_at_ms <= ?",
        [now],
      ).map((row) => text(row.packet_id));
      if (expiredContextPacketIds.length > 0) {
        this.db.prepare(
          "DELETE FROM desktop_context_packets WHERE expires_at_ms IS NOT NULL AND expires_at_ms <= ?",
        ).run(now);
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
        failedArtifactDeliveryIds,
        recoveryDispatchIds,
        clearedAttemptInstanceIds,
        clearedBindingInstanceIds,
        eventIds,
      };
    });
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
      externalRefKind: input.externalRefKind ?? null,
      externalRefId: input.externalRefId ?? null,
      legacyClientScope: input.legacyClientScope ?? null,
      legacySessionKey: input.legacySessionKey ?? null,
      defaultAdapterId: input.defaultAdapterId,
      defaultCwd: input.defaultCwd ?? null,
      modelProfile: input.modelProfile ?? null,
      metadataJson: input.metadataJson ?? "{}",
      createdAtMs: input.createdAtMs ?? now,
      updatedAtMs: input.updatedAtMs ?? now,
      lastActivityAtMs: input.lastActivityAtMs ?? now,
    };
    this.db.prepare(
      `INSERT INTO sessions (
        session_id, owner_id, agent_definition_id, title, status, surface_kind,
        external_ref_kind, external_ref_id, legacy_client_scope, legacy_session_key,
        default_adapter_id, default_cwd, model_profile, metadata_json,
        created_at_ms, updated_at_ms, last_activity_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...sessionValues(session));
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
        status, mode, input_json, system_prompt_hash, model_profile, requested_model_id,
        cwd, final_text, result_json, error_code, error_message, input_tokens,
        output_tokens, cache_read_tokens, cache_write_tokens, cost_usd,
        created_at_ms, started_at_ms, completed_at_ms, updated_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...runValues(run));
    return run;
  }

  insertAttempt(input: NewRunAttempt): RunAttempt {
    const now = this.nowMs();
    const attempt: RunAttempt = {
      attemptId: input.attemptId ?? generateAgentId("attempt"),
      runId: input.runId,
      attemptNo: input.attemptNo,
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
        attempt_id, run_id, attempt_no, status, adapter_id, adapter_instance_id,
        runtime_node_id, binding_id, adapter_native_run_id, resume_from_attempt_id,
        checkpoint_artifact_id, retry_reason, retryable, cancellation_requested_at_ms,
        cancellation_dispatched_at_ms, cancellation_acknowledged_at_ms, started_at_ms,
        completed_at_ms, error_code, error_message, metadata_json, created_at_ms, updated_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
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
          binding_id, session_id, adapter_id, binding_generation, adapter_native_session_id,
          adapter_instance_id, resume_fidelity, status, cwd, model_id, system_prompt_hash,
          metadata_json, created_at_ms, updated_at_ms, last_used_at_ms, invalidated_at_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
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
      requiresApproval: input.requiresApproval,
      status: input.status ?? "pending",
      createdAtMs: input.createdAtMs ?? this.nowMs(),
      resolvedAtMs: input.resolvedAtMs ?? null,
    };
    this.db.prepare(
      `INSERT INTO desktop_task_candidates (
        candidate_id, owner_id, source_session_id, source_run_id, action,
        task_ref, proposed_change_json, evidence_refs_json, confidence,
        requires_approval, status, created_at_ms, resolved_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
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
    session.externalRefKind,
    session.externalRefId,
    session.legacyClientScope,
    session.legacySessionKey,
    session.defaultAdapterId,
    session.defaultCwd,
    session.modelProfile,
    session.metadataJson,
    session.createdAtMs,
    session.updatedAtMs,
    session.lastActivityAtMs,
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
    candidate.requiresApproval,
    candidate.status,
    candidate.createdAtMs,
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
