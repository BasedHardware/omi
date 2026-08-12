import type { MemoryStrategyAssignmentBundle } from "../../core/consolidate/strategy-assignment";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import {
  defineDurableMemoryWorkAcceptanceRepository,
  type DurableMemoryWorkAcceptanceRepository,
  type NormalizedDurableMemoryWorkAcceptanceRequest,
} from "../../apps/service/stores/durable-memory-work-repository";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlValue } from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface HashRow extends Record<string, unknown> {
  readonly content_hash: string;
}

interface PendingStateRow extends Record<string, unknown> {
  readonly state_revision: number | string | bigint;
  readonly state_digest: string;
  readonly state: string;
}

interface ManifestRow extends Record<string, unknown> {
  readonly input_kind: string;
  readonly input_ref: string;
  readonly input_digest: string;
}

const safeInteger = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const numeric = Number(value);
  if (!Number.isSafeInteger(numeric) || numeric < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return numeric;
};

const executeRequired = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  text: string,
  values: readonly SqlValue[],
): Promise<void> => {
  if ((await connection.execute({ name, text, values })).rowCount !== 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const insertImmutableAndVerify = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  insertText: string,
  insertValues: readonly SqlValue[],
  selectText: string,
  selectValues: readonly SqlValue[],
  expectedHash: string,
): Promise<void> => {
  await connection.execute({ name: `${name}.insert`, text: insertText, values: insertValues });
  const rows = await connection.query<HashRow>({
    name: `${name}.verify`, text: selectText, values: selectValues,
  });
  if (rows.length !== 1 || rows[0]?.content_hash !== expectedHash) {
    throw new PostgresRepositoryError("idempotency_conflict");
  }
};

const persistStrategyAssignment = async (
  connection: CheckedOutPostgresConnection,
  bundle: Readonly<MemoryStrategyAssignmentBundle>,
): Promise<void> => {
  const accountId = bundle.owner_account_id;
  for (const strategy of bundle.strategies) {
    const coordinates = strategy.coordinates;
    await insertImmutableAndVerify(
      connection,
      "work.strategy_definition",
      `
INSERT INTO omi_memory.memory_strategy_definitions
  (account_id, strategy_id, strategy_version, work_kind,
   execution_contract_digest, algorithm_strategy_version, model_version,
   prompt_version, policy_version, code_version, schema_version,
   tokenizer_version, tool_version, result_contract_version,
   speaker_strategy_version, boundary_strategy_version, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
ON CONFLICT (account_id, strategy_id) DO NOTHING
`, [
        accountId, strategy.strategy_id, strategy.version, strategy.work_kind,
        strategy.execution_contract_digest, coordinates.strategy_version,
        coordinates.model_version, coordinates.prompt_version, coordinates.policy_version,
        coordinates.code_version, coordinates.schema_version, coordinates.tokenizer_version,
        coordinates.tool_version, coordinates.result_contract_version,
        coordinates.speaker_strategy_version, coordinates.boundary_strategy_version,
        strategy.execution_contract_digest,
      ],
      `SELECT content_hash FROM omi_memory.memory_strategy_definitions
       WHERE account_id = $1 AND strategy_id = $2`,
      [accountId, strategy.strategy_id],
      strategy.execution_contract_digest,
    );
  }

  const policy = bundle.policy;
  await insertImmutableAndVerify(
    connection,
    "work.strategy_policy",
    `
INSERT INTO omi_memory.memory_strategy_assignment_policies
  (account_id, policy_id, policy_version, policy_digest, work_kind,
   unit_kind, key_version, authority_strategy_id,
   authority_execution_contract_digest, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (account_id, policy_id) DO NOTHING
`, [
      accountId, policy.policy_id, policy.version, policy.policy_digest,
      policy.work_kind, policy.unit_kind, policy.key_version,
      policy.authority_strategy_id, policy.authority_execution_contract_digest,
      policy.policy_digest,
    ],
    `SELECT content_hash FROM omi_memory.memory_strategy_assignment_policies
     WHERE account_id = $1 AND policy_id = $2`,
    [accountId, policy.policy_id],
    policy.policy_digest,
  );
  for (let ordinal = 0; ordinal < policy.shadow_candidates.length; ordinal += 1) {
    const shadow = policy.shadow_candidates[ordinal]!;
    await connection.execute({
      name: "work.strategy_policy_shadow.insert",
      text: `
INSERT INTO omi_memory.memory_strategy_policy_shadows
  (account_id, policy_id, shadow_ordinal, strategy_id,
   execution_contract_digest, work_kind, basis_points)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (account_id, policy_id, shadow_ordinal) DO NOTHING
`,
      values: [
        accountId, policy.policy_id, ordinal, shadow.strategy_id,
        shadow.execution_contract_digest, policy.work_kind, shadow.basis_points,
      ],
    });
  }

  await insertImmutableAndVerify(
    connection,
    "work.strategy_bundle",
    `
INSERT INTO omi_memory.memory_strategy_assignment_bundles
  (account_id, assignment_bundle_id, assignment_bundle_digest,
   assignment_version, policy_id, policy_digest, work_kind, unit_kind,
   unit_digest, key_version, authority_assignment_id, authority_strategy_id,
   authority_execution_contract_digest, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
ON CONFLICT (account_id, assignment_bundle_id) DO NOTHING
`, [
      accountId, bundle.assignment_bundle_id, bundle.assignment_bundle_digest,
      bundle.version, policy.policy_id, policy.policy_digest, bundle.work_kind,
      bundle.unit_kind, bundle.unit_digest, policy.key_version,
      bundle.authority.assignment_id, bundle.authority.strategy_id,
      bundle.authority.execution_contract_digest, bundle.assignment_bundle_digest,
    ],
    `SELECT content_hash FROM omi_memory.memory_strategy_assignment_bundles
     WHERE account_id = $1 AND assignment_bundle_id = $2`,
    [accountId, bundle.assignment_bundle_id],
    bundle.assignment_bundle_digest,
  );
  for (let ordinal = 0; ordinal < bundle.shadows.length; ordinal += 1) {
    const shadow = bundle.shadows[ordinal]!;
    if (shadow.bucket === null || shadow.basis_points === null) {
      throw new PostgresRepositoryError("persistence_failed");
    }
    const contentHash = sha256CanonicalContent({
      assignment_bundle_id: bundle.assignment_bundle_id,
      shadow_ordinal: ordinal,
      assignment: shadow,
    });
    await insertImmutableAndVerify(
      connection,
      "work.strategy_shadow_assignment",
      `
INSERT INTO omi_memory.memory_strategy_shadow_assignments
  (account_id, assignment_bundle_id, shadow_ordinal, assignment_id,
   policy_id, strategy_id, execution_contract_digest, work_kind,
   bucket, basis_points, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
ON CONFLICT (account_id, assignment_bundle_id, shadow_ordinal) DO NOTHING
`, [
        accountId, bundle.assignment_bundle_id, ordinal, shadow.assignment_id,
        policy.policy_id, shadow.strategy_id, shadow.execution_contract_digest,
        bundle.work_kind, shadow.bucket, shadow.basis_points, contentHash,
      ],
      `SELECT content_hash FROM omi_memory.memory_strategy_shadow_assignments
       WHERE account_id = $1 AND assignment_bundle_id = $2 AND shadow_ordinal = $3`,
      [accountId, bundle.assignment_bundle_id, ordinal],
      contentHash,
    );
  }
};

const verifyReplay = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  request: NormalizedDurableMemoryWorkAcceptanceRequest,
): Promise<"replayed" | "conflict" | "missing"> => {
  const rows = await connection.query<HashRow>({
    name: "work.acceptance.lookup",
    text: `SELECT content_hash FROM omi_memory.memory_work_acceptances
           WHERE account_id = $1 AND job_id = $2`,
    values: [context.account_id, request.pending_job.job_id],
  });
  if (rows.length === 0) return "missing";
  if (rows.length !== 1 || rows[0]?.content_hash !== request.request_digest) return "conflict";
  const state = await connection.query<PendingStateRow>({
    name: "work.acceptance.pending_verify",
    text: `
SELECT s.state_revision, s.state_digest, s.state
FROM omi_memory.memory_work_heads AS h
JOIN omi_memory.memory_work_state_revisions AS s
  ON s.account_id = h.account_id AND s.job_id = h.job_id
 AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
WHERE h.account_id = $1 AND h.job_id = $2
`,
    values: [context.account_id, request.pending_job.job_id],
  });
  if (state.length !== 1 || safeInteger(state[0]?.state_revision) !== 0
    || state[0]?.state !== "pending" || state[0]?.state_digest !== request.state_digest) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const manifest = await connection.query<ManifestRow>({
    name: "work.acceptance.manifest_verify",
    text: `SELECT input_kind, input_ref, input_digest
           FROM omi_memory.memory_work_input_manifest
           WHERE account_id = $1 AND job_id = $2 ORDER BY input_ordinal`,
    values: [context.account_id, request.pending_job.job_id],
  });
  if (sha256CanonicalContent(manifest) !== sha256CanonicalContent(request.input_manifest)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return "replayed";
};

const accept = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: NormalizedDurableMemoryWorkAcceptanceRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, lockedControlRevision }) => {
        await connection.query({
          name: "work.acceptance.lock_key",
          text: "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
          values: [`memory-work:${authority.account_id}:${request.pending_job.job_id}`],
        });
        const replay = await verifyReplay(connection, authority, request);
        if (replay === "conflict") return Object.freeze({ kind: "idempotency_conflict" as const });
        if (replay === "replayed") {
          return Object.freeze({ kind: "replayed" as const, job: request.pending_job });
        }

        await persistStrategyAssignment(connection, request.strategy_assignment);
        const job = request.pending_job;
        await executeRequired(connection, "work.acceptance.insert", `
INSERT INTO omi_memory.memory_work_acceptances
  (account_id, job_id, work_version, accepted_work_digest, account_epoch,
   accepted_control_revision, lifecycle_state, deletion_epoch, account_generation,
   work_kind, input_frontier, input_digest, execution_contract_digest,
   accepted_at_event_time, max_attempts, content_hash,
   assignment_bundle_id, assignment_bundle_digest,
   authority_assignment_id, authority_strategy_id)
VALUES ($1, $2, $3, $4, $5, $6, 'active', NULL, 'new',
        $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
`, [
          authority.account_id, job.job_id, job.version, job.accepted_work_digest,
          authority.account_epoch, lockedControlRevision, job.work_kind, job.input_frontier,
          job.input_digest, job.execution_contract_digest, job.accepted_at_event_time,
          job.max_attempts, request.request_digest,
          request.strategy_assignment.assignment_bundle_id,
          request.strategy_assignment.assignment_bundle_digest,
          request.strategy_assignment.authority.assignment_id,
          request.strategy_assignment.authority.strategy_id,
        ]);
        for (let ordinal = 0; ordinal < request.input_manifest.length; ordinal += 1) {
          const input = request.input_manifest[ordinal]!;
          await executeRequired(connection, "work.acceptance.manifest_insert", `
INSERT INTO omi_memory.memory_work_input_manifest
  (account_id, job_id, input_ordinal, input_kind, input_ref, input_digest)
VALUES ($1, $2, $3, $4, $5, $6)
`, [
            authority.account_id, job.job_id, ordinal,
            input.input_kind, input.input_ref, input.input_digest,
          ]);
        }
        await executeRequired(connection, "work.acceptance.state_insert", `
INSERT INTO omi_memory.memory_work_state_revisions
  (account_id, job_id, state_revision, state_digest, state, attempt, lease_fence,
   worker_id, leased_at_event_time, lease_expires_at_event_time,
   error_code, failed_at_event_time, next_eligible_event_time,
   result_kind, response_digest, result_digest, succeeded_at_event_time, content_hash)
VALUES ($1, $2, 0, $3, 'pending', 0, 0,
        NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, $3)
`, [authority.account_id, job.job_id, request.state_digest]);
        await executeRequired(connection, "work.acceptance.head_insert", `
INSERT INTO omi_memory.memory_work_heads
  (account_id, job_id, state_revision, state_digest)
VALUES ($1, $2, 0, $3)
`, [authority.account_id, job.job_id, request.state_digest]);
        return Object.freeze({ kind: "accepted" as const, job });
      },
      observability,
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    switch (error.code) {
      case "expired_context":
      case "stale_epoch":
      case "destination_inactive":
      case "lifecycle_inactive":
        return Object.freeze({ kind: "stale_context" as const, reason: error.code });
      case "credential_inactive":
      case "grant_inactive":
      case "capability_denied":
        return Object.freeze({ kind: "authorization_denied" as const, reason: error.code });
      case "idempotency_conflict":
        return Object.freeze({ kind: "idempotency_conflict" as const });
      case "retryable_serialization":
        return Object.freeze({ kind: "serialization_retryable" as const });
      default:
        throw error;
    }
  }
};

export interface PostgresDurableMemoryWorkAcceptanceOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/** Inert PostgreSQL acceptance path; no worker loop, model call, or route is composed. */
export const createPostgresDurableMemoryWorkAcceptanceRepository = (
  options: PostgresDurableMemoryWorkAcceptanceOptions,
): DurableMemoryWorkAcceptanceRepository => defineDurableMemoryWorkAcceptanceRepository(
  (context, request) => accept(options.pool, context, request, options.observability ?? {}),
);
