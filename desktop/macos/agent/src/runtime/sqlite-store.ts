import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
import { DatabaseSync, type SQLInputValue, type SQLOutputValue } from "node:sqlite";
import type {
  AdapterBinding,
  AgentEvent,
  AgentIdKind,
  AgentRun,
  AgentSession,
  AgentStore,
  NewAdapterBinding,
  NewAgentEvent,
  NewAgentRun,
  NewAgentSession,
  NewRunAttempt,
  RunAttempt,
  StartupReconciliationResult,
} from "./types.js";

const DATABASE_FILENAME = "omi-agentd.sqlite3";
const PHASE_1_MIGRATION_VERSION = 1;

const ACTIVE_ATTEMPT_STATUSES = ["queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling"] as const;
const TERMINAL_ATTEMPT_STATUSES = ["succeeded", "failed", "cancelled", "timed_out", "orphaned"] as const;

type DatabaseFactory = new (path: string) => Pick<DatabaseSync, "exec" | "prepare" | "close" | "isTransaction">;
type Row = Record<string, SQLOutputValue>;

export interface SqliteAgentStoreOptions {
  stateDir?: string;
  databasePath?: string;
  reconcileOnOpen?: boolean;
  nowMs?: () => number;
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

  constructor(options: SqliteAgentStoreOptions = {}) {
    const databasePath = options.databasePath ?? databasePathForStateDir(requiredStateDir(options.stateDir));
    mkdirSync(dirname(databasePath), { recursive: true });
    this.db = new DatabaseSync(databasePath);
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
    if (this.hasMigration(PHASE_1_MIGRATION_VERSION)) {
      return;
    }
    runPhase1Migration(this.db, this.nowMs());
  }

  withTransaction<T>(work: () => T): T {
    return runTransaction(this.db, work);
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
          type: "runtime.attempt_orphaned",
          payload: { attemptId: attempt.attempt_id, reason: "daemon_startup_reconciliation" },
          createdAtMs: now,
        }));
      }
      for (const runId of orphanedRunIds) {
        eventIds.push(this.appendReconciliationEvent({
          sessionId: sessionIdForRun(this.db, runId),
          runId,
          attemptId: null,
          type: "runtime.run_orphaned",
          payload: { runId, reason: "daemon_startup_reconciliation" },
          createdAtMs: now,
        }));
      }
      for (const binding of staleBindings) {
        eventIds.push(this.appendReconciliationEvent({
          sessionId: text(binding.session_id),
          runId: null,
          attemptId: null,
          type: "runtime.binding_stale",
          payload: { bindingId: binding.binding_id, reason: "non_resumable_binding_after_restart" },
          createdAtMs: now,
        }));
      }

      return {
        orphanedAttemptIds: activeAttempts.map((row) => text(row.attempt_id)),
        orphanedRunIds,
        staleBindingIds: staleBindings.map((row) => text(row.binding_id)),
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
    this.db.prepare(
      `INSERT INTO adapter_bindings (
        binding_id, session_id, adapter_id, binding_generation, adapter_native_session_id,
        adapter_instance_id, resume_fidelity, status, cwd, model_id, system_prompt_hash,
        metadata_json, created_at_ms, updated_at_ms, last_used_at_ms, invalidated_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).run(...bindingValues(binding));
    return binding;
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
