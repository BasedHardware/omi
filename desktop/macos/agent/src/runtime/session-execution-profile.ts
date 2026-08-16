import {
  adapterCredentialScopeFor,
  isProductionAdapterId,
} from "../adapters/interface.js";
import { providerBoundaryForAdapter } from "./execution-policy.js";
import type {
  AgentExecutionRole,
  AgentSession,
  AgentStore,
  DefaultExecutionProfilePreference,
  SessionCredentialScope,
  SessionExecutionProfile,
  SessionExecutionProfileSource,
} from "./types.js";

const ACTIVE_RUN_STATUSES = [
  "queued",
  "starting",
  "running",
  "waiting_input",
  "waiting_approval",
  "cancelling",
] as const;

function nullableText(value: unknown): string | null {
  return value === null || value === undefined ? null : String(value);
}

export function credentialScopeForAdapter(adapterId: string): SessionCredentialScope {
  return isProductionAdapterId(adapterId) ? adapterCredentialScopeFor(adapterId) : "local_user";
}

export function sessionExecutionProfileFromRow(row: Record<string, unknown>): SessionExecutionProfile {
  return {
    sessionId: String(row.session_id),
    generation: Number(row.generation),
    adapterId: String(row.adapter_id),
    credentialScope: String(row.credential_scope) as SessionCredentialScope,
    modelProfile: nullableText(row.model_profile),
    workingDirectory: String(row.working_directory ?? ""),
    executionRole: String(row.execution_role) === "leaf" ? "leaf" : "coordinator",
    source: String(row.source) as SessionExecutionProfileSource,
    auditJson: String(row.audit_json ?? "{}"),
    createdAtMs: Number(row.created_at_ms),
  };
}

export function readSessionExecutionProfile(
  store: AgentStore,
  sessionId: string,
  generation?: number,
): SessionExecutionProfile {
  const row = generation === undefined
    ? store.getRow(
        `SELECT p.*
         FROM sessions s
         JOIN session_execution_profiles p
           ON p.session_id = s.session_id AND p.generation = s.current_profile_generation
         WHERE s.session_id = ?`,
        [sessionId],
      )
    : store.getRow(
        "SELECT * FROM session_execution_profiles WHERE session_id = ? AND generation = ?",
        [sessionId, generation],
      );
  return sessionExecutionProfileFromRow(row);
}

export function applyExecutionProfileToSession(
  session: AgentSession,
  profile: SessionExecutionProfile,
): AgentSession {
  if (session.sessionId !== profile.sessionId) {
    throw new Error("Execution profile does not belong to the session");
  }
  return {
    ...session,
    executionProfileGeneration: profile.generation,
    defaultAdapterId: profile.adapterId,
    defaultCwd: profile.workingDirectory || session.defaultCwd,
    modelProfile: profile.modelProfile,
    executionRole: profile.executionRole,
    providerBoundary: providerBoundaryForAdapter(profile.adapterId),
  };
}

export interface MigrateSessionExecutionProfileInput {
  sessionId: string;
  ownerId: string;
  expectedProfileGeneration: number;
  adapterId: string;
  credentialScope?: SessionCredentialScope;
  modelProfile?: string | null;
  workingDirectory?: string;
  executionRole?: AgentExecutionRole;
  source?: Extract<SessionExecutionProfileSource, "migration" | "child_derivation">;
  reason: string;
}

export interface MigrateSessionExecutionProfileResult {
  previous: SessionExecutionProfile;
  profile: SessionExecutionProfile;
  staleBindingIds: string[];
}

export function migrateSessionExecutionProfile(
  store: AgentStore,
  input: MigrateSessionExecutionProfileInput,
  nowMs: number,
): MigrateSessionExecutionProfileResult {
  return store.withTransaction(() => {
    if (!isProductionAdapterId(input.adapterId)) {
      throw new Error(`Unknown production adapter ${input.adapterId}`);
    }
    const session = store.getRow(
      "SELECT owner_id, current_profile_generation FROM sessions WHERE session_id = ?",
      [input.sessionId],
    );
    if (String(session.owner_id) !== input.ownerId) {
      throw new Error("Agent session is not visible to the active owner");
    }
    if (Number(session.current_profile_generation) !== input.expectedProfileGeneration) {
      throw new Error("Session execution profile generation is stale");
    }
    const active = store.getOptionalRow(
      `SELECT run_id FROM runs
       WHERE session_id = ? AND status IN (${ACTIVE_RUN_STATUSES.map(() => "?").join(", ")})
       LIMIT 1`,
      [input.sessionId, ...ACTIVE_RUN_STATUSES],
    );
    if (active) {
      throw new Error("Cannot migrate a session execution profile while a run is active");
    }

    const previous = readSessionExecutionProfile(store, input.sessionId);
    const credentialScope = input.credentialScope ?? credentialScopeForAdapter(input.adapterId);
    const expectedScope = credentialScopeForAdapter(input.adapterId);
    if (credentialScope !== expectedScope) {
      throw new Error(`Adapter ${input.adapterId} requires ${expectedScope} credentials`);
    }
    const generation = Number(session.current_profile_generation) + 1;
    const auditJson = JSON.stringify({
      reason: input.reason,
      previousGeneration: previous.generation,
      legacyProjection: {
        readAuthority: false,
        owner: "desktop-kernel",
        removalCondition: "all supported desktop versions write immutable session execution profiles",
        removeBy: "2026-10-01",
      },
    });
    store.execute(
      `INSERT INTO session_execution_profiles(
        session_id, generation, adapter_id, credential_scope, model_profile,
        working_directory, execution_role, source, audit_json, created_at_ms
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        input.sessionId,
        generation,
        input.adapterId,
        credentialScope,
        input.modelProfile === undefined ? previous.modelProfile : input.modelProfile,
        input.workingDirectory ?? previous.workingDirectory,
        input.executionRole ?? previous.executionRole,
        input.source ?? "migration",
        auditJson,
        nowMs,
      ],
    );

    const staleRows = store.allRows(
      "SELECT binding_id FROM adapter_bindings WHERE session_id = ? AND status = 'active'",
      [input.sessionId],
    );
    const staleBindingIds = staleRows.map((row) => String(row.binding_id));
    store.execute(
      `UPDATE adapter_bindings
       SET status = 'stale', invalidated_at_ms = COALESCE(invalidated_at_ms, ?), updated_at_ms = ?
       WHERE session_id = ? AND status = 'active'`,
      [nowMs, nowMs, input.sessionId],
    );
    // Legacy columns are a bounded rollback projection only. Runtime readers
    // must resolve session_execution_profiles instead.
    store.execute(
      `UPDATE sessions
       SET current_profile_generation = ?, default_adapter_id = ?, provider_boundary = ?,
           model_profile = ?, default_cwd = ?, execution_role = ?, updated_at_ms = ?
       WHERE session_id = ?`,
      [
        generation,
        input.adapterId,
        providerBoundaryForAdapter(input.adapterId),
        input.modelProfile === undefined ? previous.modelProfile : input.modelProfile,
        input.workingDirectory ?? previous.workingDirectory,
        input.executionRole ?? previous.executionRole,
        nowMs,
        input.sessionId,
      ],
    );
    return {
      previous,
      profile: readSessionExecutionProfile(store, input.sessionId, generation),
      staleBindingIds,
    };
  });
}

function defaultPreferenceFromRow(row: Record<string, unknown>): DefaultExecutionProfilePreference {
  return {
    ownerId: String(row.owner_id),
    generation: Number(row.generation),
    adapterId: String(row.adapter_id),
    credentialScope: String(row.credential_scope) as SessionCredentialScope,
    modelProfile: nullableText(row.model_profile),
    workingDirectory: String(row.working_directory),
    updatedAtMs: Number(row.updated_at_ms),
  };
}

export function readDefaultExecutionProfilePreference(
  store: AgentStore,
  ownerId: string,
): DefaultExecutionProfilePreference | undefined {
  const row = store.getOptionalRow(
    "SELECT * FROM default_execution_profile_preferences WHERE owner_id = ?",
    [ownerId],
  );
  return row ? defaultPreferenceFromRow(row) : undefined;
}

export interface ConfigureDefaultExecutionProfileInput {
  ownerId: string;
  adapterId: string;
  modelProfile: string | null;
  workingDirectory: string;
  expectedPreferenceGeneration?: number;
}

export function configureDefaultExecutionProfile(
  store: AgentStore,
  input: ConfigureDefaultExecutionProfileInput,
  nowMs: number,
): DefaultExecutionProfilePreference {
  if (!isProductionAdapterId(input.adapterId)) {
    throw new Error(`Unknown production adapter ${input.adapterId}`);
  }
  const workingDirectory = input.workingDirectory.trim();
  if (!workingDirectory) throw new Error("Default execution profile requires workingDirectory");
  const credentialScope = credentialScopeForAdapter(input.adapterId);
  return store.withTransaction(() => {
    const previous = readDefaultExecutionProfilePreference(store, input.ownerId);
    if (
      input.expectedPreferenceGeneration !== undefined
      && input.expectedPreferenceGeneration !== (previous?.generation ?? 0)
    ) {
      throw new Error("Default execution profile preference generation is stale");
    }
    const unchanged = previous
      && previous.adapterId === input.adapterId
      && previous.modelProfile === input.modelProfile
      && previous.workingDirectory === workingDirectory;
    if (unchanged) return previous;
    const generation = (previous?.generation ?? 0) + 1;
    store.execute(
      `INSERT INTO default_execution_profile_preferences(
         owner_id, generation, adapter_id, credential_scope, model_profile,
         working_directory, updated_at_ms
       ) VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(owner_id) DO UPDATE SET
         generation = excluded.generation,
         adapter_id = excluded.adapter_id,
         credential_scope = excluded.credential_scope,
         model_profile = excluded.model_profile,
         working_directory = excluded.working_directory,
         updated_at_ms = excluded.updated_at_ms`,
      [
        input.ownerId,
        generation,
        input.adapterId,
        credentialScope,
        input.modelProfile,
        workingDirectory,
        nowMs,
      ],
    );
    return readDefaultExecutionProfilePreference(store, input.ownerId)!;
  });
}
