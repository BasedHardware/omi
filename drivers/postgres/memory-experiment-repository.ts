import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineMemoryReadGroundingRepository,
  type FinalizedMemoryReadGroundingArtifact,
  type MemoryReadGroundingRepository,
} from "../../apps/service/stores/memory-read-grounding-repository";
import {
  defineMemoryShadowResultRepository,
  materializeMemoryEvaluationResult,
  memoryEvaluationResultId,
  type MemoryEvaluationCoordinate,
  type MemoryEvaluationPair,
  type MemoryEvaluationResult,
  type MemoryEvaluationStageRequest,
  type MemoryShadowResultRepository,
} from "../../apps/service/stores/memory-shadow-result-repository";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlValue } from "./connection";
import { persistPostgresMemoryStrategyAssignment } from "./durable-memory-work-acceptance";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

type ResultRole = "baseline" | "candidate";

interface HashRow extends Record<string, unknown> {
  readonly content_hash: string;
}

interface ResultRow extends Record<string, unknown> {
  readonly result_version: string;
  readonly evaluation_result_id: string;
  readonly account_id: string;
  readonly account_epoch: string | number | bigint;
  readonly assignment_bundle_id: string;
  readonly assignment_bundle_digest: string;
  readonly assignment_id: string;
  readonly evaluation_role: string;
  readonly evaluation_mode: string;
  readonly evaluation_run_id: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly repeat_ordinal: string | number | bigint;
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly result_contract_version: string;
  readonly response_digest: string;
  readonly normalized_result_digest: string;
  readonly normalized_result_json: unknown;
  readonly stage_request_digest: string;
  readonly content_hash: string;
}

interface PairRow extends Record<string, unknown> {
  readonly pair_digest: string;
  readonly content_hash: string;
}

interface ArtifactRow extends Record<string, unknown> {
  readonly artifact_version: string;
  readonly grounding_artifact_id: string;
  readonly evaluation_result_id: string;
  readonly copied_input_digest: string;
  readonly input_frontier_digest: string;
  readonly strategy_id: string;
  readonly execution_contract_digest: string;
  readonly normalized_result_digest: string;
  readonly response_digest: string;
  readonly projection_authorization_digest: string;
  readonly reader_projection_digest: string;
  readonly projected_content_digest: string;
  readonly grounded_reference_count: string | number | bigint;
  readonly rows_json: unknown;
  readonly artifact_digest: string;
}

const resultTable = (role: ResultRole): string => role === "baseline"
  ? "memory_strategy_evaluation_baselines"
  : "memory_strategy_shadow_results";

const groundingTable = (role: ResultRole): string => role === "baseline"
  ? "memory_strategy_baseline_read_groundings"
  : "memory_strategy_candidate_read_groundings";

const integer = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const normalized = Number(value);
  if (!Number.isSafeInteger(normalized) || normalized < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return normalized;
};

const executeOne = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  text: string,
  values: readonly SqlValue[],
): Promise<void> => {
  if ((await connection.execute({ name, text, values })).rowCount !== 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const resultFromRow = (row: ResultRow): MemoryEvaluationResult => ({
  version: row.result_version as MemoryEvaluationResult["version"],
  evaluation_result_id: row.evaluation_result_id,
  owner_account_id: row.account_id,
  account_epoch: integer(row.account_epoch),
  assignment_bundle_id: row.assignment_bundle_id,
  assignment_bundle_digest: row.assignment_bundle_digest,
  assignment_id: row.assignment_id,
  evaluation_role: row.evaluation_role as MemoryEvaluationResult["evaluation_role"],
  evaluation_mode: row.evaluation_mode as MemoryEvaluationResult["evaluation_mode"],
  evaluation_run_id: row.evaluation_run_id,
  input_frontier: row.input_frontier,
  input_digest: row.input_digest,
  repeat_ordinal: integer(row.repeat_ordinal),
  strategy_id: row.strategy_id,
  execution_contract_digest: row.execution_contract_digest,
  result_contract_version: row.result_contract_version,
  response_digest: row.response_digest,
  normalized_result_digest: row.normalized_result_digest,
  normalized_result: row.normalized_result_json as MemoryEvaluationResult["normalized_result"],
  stage_request_digest: row.stage_request_digest,
});

const resultColumns = (role: ResultRole): string => `result_version, evaluation_result_id, account_id, account_epoch,
  assignment_bundle_id, assignment_bundle_digest, assignment_id, '${role}' AS evaluation_role,
  evaluation_mode, evaluation_run_id, input_frontier, input_digest, repeat_ordinal,
  strategy_id, execution_contract_digest, result_contract_version, response_digest,
  normalized_result_digest, normalized_result_json, stage_request_digest, content_hash`;

const loadResult = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  role: ResultRole,
  resultId: string,
): Promise<ResultRow | null> => {
  const rows = await connection.query<ResultRow>({
    name: `experiment.${role}_result_load`,
    text: `SELECT ${resultColumns(role)} FROM omi_memory.${resultTable(role)}
           WHERE account_id = $1 AND evaluation_result_id = $2`,
    values: [accountId, resultId],
  });
  if (rows.length > 1) throw new PostgresRepositoryError("persistence_failed");
  return rows[0] ?? null;
};

const verifyResultRow = (row: ResultRow, expected: MemoryEvaluationResult): void => {
  const materialized = resultFromRow(row);
  const expectedHash = sha256CanonicalContent(expected);
  if (row.content_hash !== expectedHash
    || sha256CanonicalContent(materialized) !== expectedHash) {
    throw new PostgresRepositoryError("idempotency_conflict");
  }
};

const insertResult = async (
  connection: CheckedOutPostgresConnection,
  request: MemoryEvaluationStageRequest,
  result: MemoryEvaluationResult,
): Promise<void> => {
  const role = result.evaluation_role;
  await executeOne(connection, `experiment.${role}_result_insert`, `
INSERT INTO omi_memory.${resultTable(role)}
  (account_id, evaluation_result_id, result_version, account_epoch,
   assignment_bundle_id, assignment_bundle_digest, assignment_id, strategy_id,
   execution_contract_digest, work_kind, evaluation_mode, evaluation_run_id,
   input_frontier, input_digest, repeat_ordinal, result_contract_version,
   response_digest, normalized_result_digest, normalized_result_json,
   stage_request_digest, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
        $15, $16, $17, $18, ($19::text)::jsonb, $20, $21)
`, [
    result.owner_account_id, result.evaluation_result_id, result.version,
    result.account_epoch, result.assignment_bundle_id, result.assignment_bundle_digest,
    result.assignment_id, result.strategy_id, result.execution_contract_digest,
    request.assignment_bundle.work_kind, result.evaluation_mode, result.evaluation_run_id,
    result.input_frontier, result.input_digest, result.repeat_ordinal,
    result.result_contract_version, result.response_digest, result.normalized_result_digest,
    JSON.stringify(result.normalized_result), result.stage_request_digest,
    sha256CanonicalContent(result),
  ]);
};

const commonFailure = (error: PostgresRepositoryError): unknown => {
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
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    case "idempotency_conflict":
      return Object.freeze({ kind: "idempotency_conflict" as const });
    default:
      throw error;
  }
};

const providerCode = (error: unknown): string | undefined => {
  if (error === null || typeof error !== "object") return undefined;
  const code = Reflect.get(error, "code");
  return typeof code === "string" ? code : undefined;
};

const inTransaction = async <Result>(
  options: PostgresMemoryExperimentRepositoryOptions,
  context: AuthorizedLedgerWriteContext,
  callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
): Promise<Result | unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      options.pool,
      context,
      async ({ connection }) => {
        try {
          return await callback(connection);
        } catch (error) {
          if (providerCode(error) === "23505") {
            throw new PostgresRepositoryError("idempotency_conflict");
          }
          throw error;
        }
      },
      options.observability ?? {},
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    return commonFailure(error);
  }
};

const stageResult = async (
  options: PostgresMemoryExperimentRepositoryOptions,
  context: AuthorizedLedgerWriteContext,
  request: MemoryEvaluationStageRequest,
): Promise<unknown> => inTransaction(options, context, async (connection) => {
  const result = materializeMemoryEvaluationResult(context, request);
  const prior = await loadResult(connection, context.account_id, result.evaluation_role, result.evaluation_result_id);
  if (prior) {
    verifyResultRow(prior, result);
    return Object.freeze({ kind: "replayed" as const, result });
  }
  await persistPostgresMemoryStrategyAssignment(connection, request.assignment_bundle);
  await insertResult(connection, request, result);
  return Object.freeze({ kind: "staged" as const, result });
});

const loadByCoordinate = async (
  options: PostgresMemoryExperimentRepositoryOptions,
  context: AuthorizedLedgerWriteContext,
  coordinate: MemoryEvaluationCoordinate,
): Promise<unknown> => inTransaction(options, context, async (connection) => {
  const role = coordinate.evaluation_role;
  const resultId = memoryEvaluationResultId(context, coordinate);
  const row = await loadResult(connection, context.account_id, role, resultId);
  if (!row) return Object.freeze({ kind: "missing" as const });
  const result = resultFromRow(row);
  if (row.content_hash !== sha256CanonicalContent(result)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({ kind: "found" as const, result });
});

const recordPair = async (
  options: PostgresMemoryExperimentRepositoryOptions,
  context: AuthorizedLedgerWriteContext,
  pair: MemoryEvaluationPair,
): Promise<unknown> => inTransaction(options, context, async (connection) => {
  const rows = await connection.query<PairRow>({
    name: "experiment.pair_load",
    text: `SELECT pair_digest, content_hash
           FROM omi_memory.memory_strategy_evaluation_pairs
           WHERE account_id = $1 AND pair_id = $2`,
    values: [context.account_id, pair.pair_id],
  });
  if (rows.length > 1) throw new PostgresRepositoryError("persistence_failed");
  if (rows[0]) {
    if (rows[0].pair_digest !== pair.pair_digest || rows[0].content_hash !== pair.pair_digest) {
      throw new PostgresRepositoryError("idempotency_conflict");
    }
    return Object.freeze({ kind: "replayed" as const, pair });
  }
  await executeOne(connection, "experiment.pair_insert", `
INSERT INTO omi_memory.memory_strategy_evaluation_pairs
  (account_id, pair_id, pair_version, pair_digest, account_epoch,
   assignment_bundle_id, evaluation_mode, evaluation_run_id,
   input_frontier_digest, input_digest, repeat_ordinal,
   baseline_result_id, baseline_strategy_id, baseline_result_digest,
   candidate_result_id, candidate_strategy_id, candidate_result_digest, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
        $15, $16, $17, $18)
`, [
    context.account_id, pair.pair_id, pair.version, pair.pair_digest,
    pair.account_epoch, pair.assignment_bundle_id, pair.evaluation_mode,
    pair.evaluation_run_id, pair.input_frontier_digest, pair.input_digest,
    pair.repeat_ordinal, pair.baseline_result_id, pair.baseline_strategy_id,
    pair.baseline_result_digest, pair.candidate_result_id,
    pair.candidate_strategy_id, pair.candidate_result_digest, pair.pair_digest,
  ]);
  return Object.freeze({ kind: "recorded" as const, pair });
});

const artifactFromRow = (row: ArtifactRow): FinalizedMemoryReadGroundingArtifact => ({
  version: row.artifact_version as FinalizedMemoryReadGroundingArtifact["version"],
  grounding_artifact_id: row.grounding_artifact_id,
  evaluation_result_ref: row.evaluation_result_id,
  normalized_result_digest: row.normalized_result_digest,
  copied_input_digest: row.copied_input_digest,
  input_frontier_digest: row.input_frontier_digest,
  strategy_id: row.strategy_id,
  execution_contract_digest: row.execution_contract_digest,
  projection_authorization_digest: row.projection_authorization_digest,
  reader_projection_digest: row.reader_projection_digest,
  projected_content_digest: row.projected_content_digest,
  response_digest: row.response_digest,
  grounded_reference_count: integer(row.grounded_reference_count),
  rows: row.rows_json as FinalizedMemoryReadGroundingArtifact["rows"],
  artifact_digest: row.artifact_digest,
});

const loadArtifact = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  role: ResultRole,
  resultId: string,
): Promise<ArtifactRow | null> => {
  const rows = await connection.query<ArtifactRow>({
    name: `experiment.${role}_grounding_load`,
    text: `SELECT artifact_version, grounding_artifact_id, evaluation_result_id,
                  copied_input_digest, input_frontier_digest, strategy_id,
                  execution_contract_digest, normalized_result_digest, response_digest,
                  projection_authorization_digest, reader_projection_digest,
                  projected_content_digest, grounded_reference_count, rows_json, artifact_digest
           FROM omi_memory.${groundingTable(role)}
           WHERE account_id = $1 AND evaluation_result_id = $2`,
    values: [accountId, resultId],
  });
  if (rows.length > 1) throw new PostgresRepositoryError("persistence_failed");
  return rows[0] ?? null;
};

const stageGrounding = async (
  options: PostgresMemoryExperimentRepositoryOptions,
  context: AuthorizedLedgerWriteContext,
  result: MemoryEvaluationResult,
  artifact: FinalizedMemoryReadGroundingArtifact,
  request: MemoryEvaluationStageRequest,
): Promise<unknown> => inTransaction(options, context, async (connection) => {
  const role = result.evaluation_role;
  const persistedResult = await loadResult(connection, context.account_id, role, result.evaluation_result_id);
  if (persistedResult) verifyResultRow(persistedResult, result);
  else {
    await persistPostgresMemoryStrategyAssignment(connection, request.assignment_bundle);
    await insertResult(connection, request, result);
  }
  const prior = await loadArtifact(connection, context.account_id, role, result.evaluation_result_id);
  if (prior) {
    if (prior.artifact_digest !== artifact.artifact_digest) {
      throw new PostgresRepositoryError("idempotency_conflict");
    }
    return Object.freeze({ kind: "replayed" as const, artifact });
  }
  await executeOne(connection, `experiment.${role}_grounding_insert`, `
INSERT INTO omi_memory.${groundingTable(role)}
  (account_id, grounding_artifact_id, evaluation_result_id, artifact_version,
   account_epoch, copied_input_digest, input_frontier_digest, strategy_id,
   execution_contract_digest, result_contract_version, normalized_result_digest,
   response_digest, projection_authorization_digest, reader_projection_digest,
   projected_content_digest, grounded_reference_count, rows_json, artifact_digest)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
        $15, $16, ($17::text)::jsonb, $18)
`, [
    context.account_id, artifact.grounding_artifact_id, result.evaluation_result_id,
    artifact.version, result.account_epoch, artifact.copied_input_digest,
    artifact.input_frontier_digest, artifact.strategy_id,
    artifact.execution_contract_digest, result.result_contract_version,
    artifact.normalized_result_digest, artifact.response_digest,
    artifact.projection_authorization_digest, artifact.reader_projection_digest,
    artifact.projected_content_digest, artifact.grounded_reference_count,
    JSON.stringify(artifact.rows), artifact.artifact_digest,
  ]);
  return Object.freeze({ kind: "staged" as const, artifact });
});

const loadGrounding = async (
  options: PostgresMemoryExperimentRepositoryOptions,
  context: AuthorizedLedgerWriteContext,
  result: MemoryEvaluationResult,
): Promise<unknown> => inTransaction(options, context, async (connection) => {
  const row = await loadArtifact(connection, context.account_id, result.evaluation_role, result.evaluation_result_id);
  return row ? Object.freeze({ kind: "found" as const, artifact: artifactFromRow(row) })
    : Object.freeze({ kind: "missing" as const });
});

export interface PostgresMemoryExperimentRepositoryOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/** Inert isolated result/pair store. It has no graph, product, or answer authority. */
export const createPostgresMemoryShadowResultRepository = (
  options: PostgresMemoryExperimentRepositoryOptions,
): MemoryShadowResultRepository => defineMemoryShadowResultRepository({
  load: (context, coordinate) => loadByCoordinate(options, context, coordinate),
  stage: (context, request) => stageResult(options, context, request),
  recordPair: (context, pair) => recordPair(options, context, pair),
});

/** Inert exact grounding store. Every artifact is closed over one persisted result. */
export const createPostgresMemoryReadGroundingRepository = (
  options: PostgresMemoryExperimentRepositoryOptions,
): MemoryReadGroundingRepository => defineMemoryReadGroundingRepository({
  stage: (context, result, artifact, request) => stageGrounding(options, context, result, artifact, request),
  load: (context, result) => loadGrounding(options, context, result),
});
