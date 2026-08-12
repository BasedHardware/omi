import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineMemoryQueryEvaluationInputRepository,
  type MemoryQueryEvaluationInput,
  type MemoryQueryEvaluationInputRepository,
} from "../../apps/service/stores/memory-query-evaluation-input-repository";
import { defineMemoryQueryEvaluationGraphSource, type MemoryQueryEvaluationGraphSource } from
  "../../apps/service/stores/memory-query-evaluation-graph-source";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import { createPostgresAuthoritativeGraphSnapshotRepository } from "./authoritative-graph-snapshot";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface InputRow extends Record<string, unknown> {
  readonly input_version: string;
  readonly account_id: string;
  readonly account_epoch: string | number | bigint;
  readonly input_ref: string;
  readonly source_ref: string;
  readonly input_frontier: string;
  readonly query_text: string;
  readonly account_timezone: string;
  readonly graph_generation: string | number | bigint;
  readonly graph_snapshot_digest: string;
  readonly stage_request_digest: string;
  readonly content_hash: string;
}

const integer = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) throw new PostgresRepositoryError("persistence_failed");
  return parsed;
};

const fromRow = (row: InputRow): MemoryQueryEvaluationInput => ({
  version: row.input_version as MemoryQueryEvaluationInput["version"],
  owner_account_id: row.account_id,
  account_epoch: integer(row.account_epoch),
  input_ref: row.input_ref,
  source_ref: row.source_ref,
  input_frontier: row.input_frontier,
  query_text: row.query_text,
  account_timezone: row.account_timezone,
  graph_generation: integer(row.graph_generation),
  graph_snapshot_digest: row.graph_snapshot_digest,
  stage_request_digest: row.stage_request_digest,
});

const exactPersistedInput = (
  row: InputRow,
  expected: Readonly<MemoryQueryEvaluationInput>,
): MemoryQueryEvaluationInput => {
  const persisted = fromRow(row);
  if (row.content_hash !== expected.stage_request_digest
    || sha256CanonicalContent(persisted) !== sha256CanonicalContent(expected)) {
    throw new PostgresRepositoryError("idempotency_conflict");
  }
  return persisted;
};

const loadRow = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  sourceRef: string,
): Promise<InputRow | null> => {
  const rows = await connection.query<InputRow>({
    name: "experiment.query_input_load",
    text: `SELECT input_version, account_id, account_epoch, input_ref, source_ref,
                  input_frontier, query_text, account_timezone, graph_generation,
                  graph_snapshot_digest, stage_request_digest, content_hash
           FROM omi_memory.memory_query_evaluation_inputs
           WHERE account_id = $1 AND source_ref = $2`,
    values: [accountId, sourceRef],
  });
  if (rows.length > 1) throw new PostgresRepositoryError("persistence_failed");
  return rows[0] ?? null;
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

const transact = async <Result>(
  options: PostgresMemoryQueryEvaluationSourceOptions,
  context: AuthorizedLedgerWriteContext,
  callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
): Promise<Result | unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      options.pool, context, ({ connection }) => callback(connection), options.observability ?? {},
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    return commonFailure(error);
  }
};

export interface PostgresMemoryQueryEvaluationSourceOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

export const createPostgresMemoryQueryEvaluationInputRepository = (
  options: PostgresMemoryQueryEvaluationSourceOptions,
): MemoryQueryEvaluationInputRepository => defineMemoryQueryEvaluationInputRepository({
  stage: (context, input) => transact(options, context, async (connection) => {
    const prior = await loadRow(connection, context.account_id, input.source_ref);
    if (prior) {
      exactPersistedInput(prior, input);
      return Object.freeze({ kind: "replayed" as const, input });
    }
    const result = await connection.execute({
      name: "experiment.query_input_insert",
      text: `INSERT INTO omi_memory.memory_query_evaluation_inputs
        (account_id, source_ref, input_version, account_epoch, input_ref,
         input_frontier, query_text, account_timezone, graph_generation,
         graph_snapshot_digest, stage_request_digest, content_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT DO NOTHING`,
      values: [
        context.account_id, input.source_ref, input.version, input.account_epoch,
        input.input_ref, input.input_frontier, input.query_text, input.account_timezone,
        input.graph_generation, input.graph_snapshot_digest, input.stage_request_digest,
        input.stage_request_digest,
      ],
    });
    if (result.rowCount === 0) {
      const raced = await loadRow(connection, context.account_id, input.source_ref);
      if (!raced) throw new PostgresRepositoryError("idempotency_conflict");
      exactPersistedInput(raced, input);
      return Object.freeze({ kind: "replayed" as const, input });
    }
    if (result.rowCount !== 1) throw new PostgresRepositoryError("persistence_failed");
    return Object.freeze({ kind: "staged" as const, input });
  }),
  load: (context, sourceRef) => transact(options, context, async (connection) => {
    const row = await loadRow(connection, context.account_id, sourceRef);
    if (!row) return Object.freeze({ kind: "missing" as const });
    const input = fromRow(row);
    if (row.content_hash !== input.stage_request_digest) throw new PostgresRepositoryError("persistence_failed");
    return Object.freeze({ kind: "found" as const, input });
  }),
});

/**
 * Route-free exact graph source. Query bytes come only from the isolated input
 * record; graph bytes come only from a freshly authority-checked coherent
 * snapshot whose generation and digest still match that record.
 */
export const createPostgresMemoryQueryEvaluationGraphSource = (
  options: PostgresMemoryQueryEvaluationSourceOptions,
): MemoryQueryEvaluationGraphSource => {
  const inputs = createPostgresMemoryQueryEvaluationInputRepository(options);
  const graphs = createPostgresAuthoritativeGraphSnapshotRepository(options);
  return defineMemoryQueryEvaluationGraphSource(async (context, request) => {
    const loaded = await inputs.load(context, request.source_ref);
    if (loaded.kind === "missing") return Object.freeze({ kind: "not_found" as const });
    if (loaded.kind !== "found") return loaded;
    if (loaded.input.input_frontier !== request.input_frontier) {
      return Object.freeze({ kind: "not_found" as const });
    }
    let graph;
    try {
      graph = await graphs.load(context);
    } catch (error) {
      if (!(error instanceof PostgresRepositoryError)) throw error;
      return commonFailure(error);
    }
    if (graph.graph_generation !== loaded.input.graph_generation
      || sha256CanonicalContent(graph) !== loaded.input.graph_snapshot_digest) {
      return Object.freeze({ kind: "not_found" as const });
    }
    return Object.freeze({
      kind: "found" as const,
      owner_account_id: context.account_id,
      account_epoch: context.account_epoch,
      source_ref: loaded.input.source_ref,
      input_frontier: loaded.input.input_frontier,
      query_text: loaded.input.query_text,
      account_timezone: loaded.input.account_timezone,
      graph_snapshot: graph,
    });
  });
};
