import {
  durableMemoryWorkStateDigest,
  succeedDurableMemoryWork,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineDurableMemoryWorkSuccessRepository,
  durableMemoryWorkSuccessOutboxId,
  type DurableMemoryWorkSuccessOutcome,
  type DurableMemoryWorkSuccessRepository,
  type DurableMemoryWorkSuccessRequest,
} from "../../apps/service/stores/durable-memory-work-success-repository";
import {
  parseStagedDurableMemoryWorkResult,
} from "../../apps/service/stores/durable-memory-work-result-repository";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlStatement } from "./connection";
import { appendAuthoritativeLedgerWithinTransaction } from "./authoritative-ledger-repository";
import { durableMemoryWorkStagedResultContentHash } from "./durable-memory-work-result";
import { persistDerivedGroupDreamMaterializationWithinTransaction } from "./derived-group-dream-materialization";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface WorkRow extends Record<string, unknown> {
  readonly account_id: string;
  readonly job_id: string;
  readonly work_version: string;
  readonly accepted_work_digest: string;
  readonly account_epoch: number | string | bigint;
  readonly lifecycle_state: string;
  readonly deletion_epoch: number | string | bigint | null;
  readonly work_kind: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly accepted_at_event_time: number | string | bigint;
  readonly max_attempts: number | string | bigint;
  readonly state_revision: number | string | bigint;
  readonly state_digest: string;
  readonly state: string;
  readonly attempt: number | string | bigint;
  readonly lease_fence: number | string | bigint;
  readonly worker_id: string | null;
  readonly leased_at_event_time: number | string | bigint | null;
  readonly lease_expires_at_event_time: number | string | bigint | null;
  readonly result_kind: string | null;
  readonly response_digest: string | null;
  readonly result_digest: string | null;
  readonly succeeded_at_event_time: number | string | bigint | null;
}

interface SuccessBundleRow extends Record<string, unknown> {
  readonly staged_result_id: string;
  readonly staged_accepted_work_digest: string;
  readonly staged_work_kind: string;
  readonly staged_input_frontier: string;
  readonly staged_execution_contract_digest: string;
  readonly staged_produced_attempt: number | string | bigint;
  readonly staged_produced_lease_fence: number | string | bigint;
  readonly staged_produced_state_digest: string;
  readonly staged_producer_worker_id: string;
  readonly staged_result_contract_version: string;
  readonly staged_response_digest: string;
  readonly staged_normalized_result_digest: string;
  readonly staged_normalized_result_json: unknown;
  readonly staged_stage_request_digest: string;
  readonly staged_content_hash: string;
  readonly success_terminal_state_revision: number | string | bigint | null;
  readonly success_terminal_state_digest: string | null;
  readonly success_work_kind: string | null;
  readonly success_input_frontier: string | null;
  readonly success_result_kind: string | null;
  readonly success_response_digest: string | null;
  readonly success_result_digest: string | null;
  readonly success_origin_code: string | null;
  readonly success_graph_commit_id: string | null;
  readonly success_graph_commit_sequence: number | string | bigint | null;
  readonly success_graph_success_kind: string | null;
  readonly success_append_receipt_state: string | null;
  readonly success_staged_result_id: string | null;
  readonly success_staged_result_digest: string | null;
  readonly success_content_hash: string | null;
  readonly outbox_id: string | null;
  readonly outbox_terminal_state_revision: number | string | bigint | null;
  readonly outbox_terminal_state_digest: string | null;
  readonly outbox_terminal_state: string | null;
  readonly outbox_event_kind: string | null;
  readonly outbox_result_digest: string | null;
  readonly outbox_created_at_event_time: number | string | bigint | null;
  readonly outbox_content_hash: string | null;
}

interface InsertResultRow extends Record<string, unknown> {
  readonly inserted: boolean;
}

const WORK_KEYS = [
  "account_id", "job_id", "work_version", "accepted_work_digest", "account_epoch",
  "lifecycle_state", "deletion_epoch", "work_kind", "input_frontier", "input_digest",
  "execution_contract_digest", "accepted_at_event_time", "max_attempts",
  "state_revision", "state_digest", "state", "attempt", "lease_fence", "worker_id",
  "leased_at_event_time", "lease_expires_at_event_time", "result_kind",
  "response_digest", "result_digest", "succeeded_at_event_time",
] as const;

const BUNDLE_KEYS = [
  "staged_result_id", "staged_accepted_work_digest", "staged_work_kind",
  "staged_input_frontier", "staged_execution_contract_digest",
  "staged_produced_attempt", "staged_produced_lease_fence",
  "staged_produced_state_digest", "staged_producer_worker_id",
  "staged_result_contract_version", "staged_response_digest",
  "staged_normalized_result_digest", "staged_normalized_result_json",
  "staged_stage_request_digest",
  "staged_content_hash", "success_terminal_state_revision",
  "success_terminal_state_digest", "success_work_kind", "success_input_frontier",
  "success_result_kind", "success_response_digest", "success_result_digest",
  "success_origin_code", "success_graph_commit_id", "success_graph_commit_sequence",
  "success_graph_success_kind", "success_append_receipt_state",
  "success_staged_result_id", "success_staged_result_digest", "success_content_hash",
  "outbox_id", "outbox_terminal_state_revision", "outbox_terminal_state_digest",
  "outbox_terminal_state", "outbox_event_kind", "outbox_result_digest",
  "outbox_created_at_event_time", "outbox_content_hash",
] as const;

const WORK_SELECT = `
SELECT
  a.account_id, a.job_id, a.work_version, a.accepted_work_digest,
  a.account_epoch, a.lifecycle_state, a.deletion_epoch, a.work_kind,
  a.input_frontier, a.input_digest, a.execution_contract_digest,
  a.accepted_at_event_time, a.max_attempts,
  s.state_revision, s.state_digest, s.state, s.attempt, s.lease_fence,
  s.worker_id, s.leased_at_event_time, s.lease_expires_at_event_time,
  s.result_kind, s.response_digest, s.result_digest, s.succeeded_at_event_time
FROM omi_memory.memory_work_acceptances AS a
JOIN omi_memory.memory_work_heads AS h
  ON h.account_id = a.account_id AND h.job_id = a.job_id
JOIN omi_memory.memory_work_state_revisions AS s
  ON s.account_id = h.account_id AND s.job_id = h.job_id
 AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
WHERE a.account_id = $1 AND a.job_id = $2 AND a.account_epoch = $3
FOR UPDATE OF h
`;

const BUNDLE_SELECT = `
SELECT * FROM omi_memory.read_durable_work_success_bundle($1, $2)
`;

const exactKeys = (value: Record<string, unknown>, keys: readonly string[]): void => {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};
const integer = (value: unknown, nullable = false): number | null => {
  if (value === null && nullable) return null;
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const result = Number(value);
  if (!Number.isSafeInteger(result) || result < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return result;
};

const safeAdd = (value: number, increment: number): number => {
  const result = value + increment;
  if (!Number.isSafeInteger(result) || result < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return result;
};

const executeOne = async (
  connection: CheckedOutPostgresConnection,
  statement: SqlStatement,
): Promise<void> => {
  if ((await connection.execute(statement)).rowCount !== 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const exactAcceptedWork = (row: WorkRow, job: Readonly<DurableMemoryWorkJob>): boolean =>
  row.account_id === job.owner_account_id
  && row.job_id === job.job_id
  && row.work_version === job.version
  && row.accepted_work_digest === job.accepted_work_digest
  && integer(row.account_epoch) === job.account_epoch
  && row.lifecycle_state === job.lifecycle_state
  && integer(row.deletion_epoch, true) === job.deletion_epoch
  && row.work_kind === job.work_kind
  && row.input_frontier === job.input_frontier
  && row.input_digest === job.input_digest
  && row.execution_contract_digest === job.execution_contract_digest
  && integer(row.accepted_at_event_time) === job.accepted_at_event_time
  && integer(row.max_attempts) === job.max_attempts;

const loadWork = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkSuccessRequest,
): Promise<WorkRow | null> => {
  const rows = await connection.query<WorkRow>({
    name: "work.success.load_locked",
    text: WORK_SELECT,
    values: [context.account_id, request.leased_job.job_id, context.account_epoch],
  });
  if (rows.length === 0) return null;
  if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
  exactKeys(rows[0], WORK_KEYS);
  if (!exactAcceptedWork(rows[0], request.leased_job)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return rows[0];
};

const loadBundle = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  jobId: string,
): Promise<SuccessBundleRow | null> => {
  const rows = await connection.query<SuccessBundleRow>({
    name: "work.success.bundle",
    text: BUNDLE_SELECT,
    values: [accountId, jobId],
  });
  if (rows.length === 0) return null;
  if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
  exactKeys(rows[0], BUNDLE_KEYS);
  return rows[0];
};

const persistedStageMatches = (
  row: SuccessBundleRow,
  request: DurableMemoryWorkSuccessRequest,
): boolean => {
  const stage = request.staged_result;
  let persisted;
  try {
    persisted = parseStagedDurableMemoryWorkResult({
      version: stage.version,
      staged_result_id: row.staged_result_id,
      owner_account_id: request.leased_job.owner_account_id,
      job_id: request.leased_job.job_id,
      accepted_work_digest: row.staged_accepted_work_digest,
      work_kind: row.staged_work_kind,
      input_frontier: row.staged_input_frontier,
      execution_contract_digest: row.staged_execution_contract_digest,
      produced_attempt: integer(row.staged_produced_attempt),
      produced_lease_fence: integer(row.staged_produced_lease_fence),
      produced_state_digest: row.staged_produced_state_digest,
      producer_worker_id: row.staged_producer_worker_id,
      result_contract_version: row.staged_result_contract_version,
      response_digest: row.staged_response_digest,
      normalized_result_digest: row.staged_normalized_result_digest,
      normalized_result: row.staged_normalized_result_json,
      stage_request_digest: row.staged_stage_request_digest,
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (row.staged_content_hash !== durableMemoryWorkStagedResultContentHash(persisted)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return sha256CanonicalContent(persisted) === sha256CanonicalContent(stage);
};

const graphCoordinates = (request: DurableMemoryWorkSuccessRequest) => {
  if (request.authoritative_append === null) {
    return Object.freeze({
      origin_code: null, graph_commit_id: null, graph_commit_sequence: null,
      graph_success_kind: null, append_receipt_state: null,
    });
  }
  const origin = request.authoritative_append.origin;
  return Object.freeze({
    origin_code: origin.kind === "formation" ? "formation" : origin.reason,
    graph_commit_id: request.authoritative_append.transition.derivation.commit.commit_id,
    graph_commit_sequence: null as number | null,
    graph_success_kind: "success",
    append_receipt_state: "finalized",
  });
};

const successContentHash = (
  request: DurableMemoryWorkSuccessRequest,
  stateRevision: number,
  stateDigest: string,
  graphSequence: number | null,
): string => {
  const graph = graphCoordinates(request);
  return sha256CanonicalContent({
    contract_version: "durable-memory-work-success-result-content-v1",
    owner_account_id: request.leased_job.owner_account_id,
    job_id: request.leased_job.job_id,
    terminal_state_revision: stateRevision,
    terminal_state_digest: stateDigest,
    work_kind: request.leased_job.work_kind,
    input_frontier: request.leased_job.input_frontier,
    result_kind: request.result_kind,
    response_digest: request.response_digest,
    result_digest: request.result_digest,
    origin_code: graph.origin_code,
    graph_commit_id: graph.graph_commit_id,
    graph_commit_sequence: graphSequence,
    graph_success_kind: graph.graph_success_kind,
    append_receipt_state: graph.append_receipt_state,
    staged_result_id: request.staged_result.staged_result_id,
    staged_result_digest: request.staged_result.normalized_result_digest,
  });
};

const outboxContentHash = (
  request: DurableMemoryWorkSuccessRequest,
  outboxId: string,
  stateRevision: number,
  stateDigest: string,
  succeededAt: number,
): string => sha256CanonicalContent({
  contract_version: "durable-memory-work-success-outbox-content-v1",
  owner_account_id: request.leased_job.owner_account_id,
  outbox_id: outboxId,
  job_id: request.leased_job.job_id,
  terminal_state_revision: stateRevision,
  terminal_state_digest: stateDigest,
  terminal_state: "succeeded",
  event_kind: "memory_work_succeeded",
  result_digest: request.result_digest,
  created_at_event_time: succeededAt,
});

const replayOutcome = (
  row: WorkRow,
  bundle: SuccessBundleRow,
  request: DurableMemoryWorkSuccessRequest,
): DurableMemoryWorkSuccessOutcome => {
  const succeededAt = integer(row.succeeded_at_event_time, true);
  if (succeededAt === null) throw new PostgresRepositoryError("persistence_failed");
  let succeeded: Readonly<DurableMemoryWorkJob>;
  try {
    succeeded = succeedDurableMemoryWork(
      request.leased_job,
      { worker_id: request.leased_job.lease!.worker_id, fence: request.leased_job.lease!.fence },
      succeededAt,
      request.result_kind,
      request.response_digest,
      request.result_digest,
    );
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const stateRevision = integer(row.state_revision)!;
  const stateDigest = durableMemoryWorkStateDigest(succeeded);
  const graphSequence = integer(bundle.success_graph_commit_sequence, true);
  const graph = graphCoordinates(request);
  const outboxId = durableMemoryWorkSuccessOutboxId(request);
  const exact = row.state_digest === stateDigest
    && integer(row.attempt) === succeeded.attempt
    && integer(row.lease_fence) === succeeded.lease_fence
    && row.worker_id === null
    && row.result_kind === request.result_kind
    && row.response_digest === request.response_digest
    && row.result_digest === request.result_digest
    && bundle.success_terminal_state_revision !== null
    && integer(bundle.success_terminal_state_revision) === stateRevision
    && bundle.success_terminal_state_digest === stateDigest
    && bundle.success_work_kind === request.leased_job.work_kind
    && bundle.success_input_frontier === request.leased_job.input_frontier
    && bundle.success_result_kind === request.result_kind
    && bundle.success_response_digest === request.response_digest
    && bundle.success_result_digest === request.result_digest
    && bundle.success_origin_code === graph.origin_code
    && bundle.success_graph_commit_id === graph.graph_commit_id
    && bundle.success_graph_success_kind === graph.graph_success_kind
    && bundle.success_append_receipt_state === graph.append_receipt_state
    && bundle.success_staged_result_id === request.staged_result.staged_result_id
    && bundle.success_staged_result_digest === request.staged_result.normalized_result_digest
    && bundle.success_content_hash === successContentHash(
      request, stateRevision, stateDigest, graphSequence,
    )
    && bundle.outbox_id === outboxId
    && integer(bundle.outbox_terminal_state_revision, true) === stateRevision
    && bundle.outbox_terminal_state_digest === stateDigest
    && bundle.outbox_terminal_state === "succeeded"
    && bundle.outbox_event_kind === "memory_work_succeeded"
    && bundle.outbox_result_digest === request.result_digest
    && integer(bundle.outbox_created_at_event_time, true) === succeededAt
    && bundle.outbox_content_hash === outboxContentHash(
      request, outboxId, stateRevision, stateDigest, succeededAt,
    );
  if (!exact) return Object.freeze({ kind: "idempotency_conflict" as const });
  return Object.freeze({
    kind: "replayed" as const,
    job: succeeded,
    commit_id: graph.graph_commit_id,
    sequence: graphSequence,
    outbox_id: outboxId,
  });
};

const commitWithinTransaction = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  dbNowEpochSeconds: number,
  request: DurableMemoryWorkSuccessRequest,
): Promise<DurableMemoryWorkSuccessOutcome> => {
  const row = await loadWork(connection, context, request);
  if (row === null) return Object.freeze({ kind: "ineligible_state" as const });
  if (row.state !== "leased" && row.state !== "succeeded") {
    return Object.freeze({ kind: "ineligible_state" as const });
  }
  const lease = request.leased_job.lease!;
  if (row.state === "leased" && (row.state_digest !== durableMemoryWorkStateDigest(request.leased_job)
    || integer(row.attempt) !== request.leased_job.attempt
    || integer(row.lease_fence) !== request.leased_job.lease_fence
    || row.worker_id !== context.principal_id
    || row.worker_id !== lease.worker_id
    || integer(row.leased_at_event_time, true) !== lease.leased_at_event_time
    || integer(row.lease_expires_at_event_time, true) !== lease.expires_at_event_time
    || dbNowEpochSeconds >= lease.expires_at_event_time)) {
    return Object.freeze({ kind: "stale_lease" as const });
  }
  const bundle = await loadBundle(connection, context.account_id, request.leased_job.job_id);
  if (bundle === null) throw new PostgresRepositoryError("persistence_failed");
  if (!persistedStageMatches(bundle, request)) {
    return Object.freeze({ kind: "idempotency_conflict" as const });
  }
  if (row.state === "succeeded") return replayOutcome(row, bundle, request);
  if (bundle.success_terminal_state_revision !== null) {
    throw new PostgresRepositoryError("persistence_failed");
  }

  let graphCommitId: string | null = null;
  let graphSequence: number | null = null;
  if (request.authoritative_append !== null) {
    const appended = await appendAuthoritativeLedgerWithinTransaction(
      connection, context, request.authoritative_append, false,
    );
    if (appended.kind === "idempotency_conflict") return appended;
    if (appended.kind !== "committed" && appended.kind !== "replayed") {
      // A graph append already committed without this terminal work unit would
      // violate the atomic-success invariant rather than constitute replay.
      throw new PostgresRepositoryError("persistence_failed");
    }
    graphCommitId = appended.commit_id;
    graphSequence = appended.sequence;
    if (request.leased_job.work_kind === "derived_group_dream") {
      await persistDerivedGroupDreamMaterializationWithinTransaction(
        connection, context, request, graphCommitId, graphSequence,
      );
    }
  }

  let succeeded: Readonly<DurableMemoryWorkJob>;
  try {
    succeeded = succeedDurableMemoryWork(
      request.leased_job,
      { worker_id: lease.worker_id, fence: lease.fence },
      dbNowEpochSeconds,
      request.result_kind,
      request.response_digest,
      request.result_digest,
    );
  } catch {
    return Object.freeze({ kind: "stale_lease" as const });
  }
  const currentRevision = integer(row.state_revision)!;
  const stateRevision = safeAdd(currentRevision, 1);
  const stateDigest = durableMemoryWorkStateDigest(succeeded);
  await executeOne(connection, {
    name: "work.success.state_insert",
    text: `
INSERT INTO omi_memory.memory_work_state_revisions
  (account_id, job_id, state_revision, state_digest, state, attempt, lease_fence,
   worker_id, leased_at_event_time, lease_expires_at_event_time,
   error_code, failed_at_event_time, next_eligible_event_time,
   result_kind, response_digest, result_digest, succeeded_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, 'succeeded', $5, $6,
        NULL, NULL, NULL, NULL, NULL, NULL, $7, $8, $9, $10, $4)
`,
    values: [
      context.account_id, succeeded.job_id, stateRevision, stateDigest,
      succeeded.attempt, succeeded.lease_fence, request.result_kind,
      request.response_digest, request.result_digest, dbNowEpochSeconds,
    ],
  });
  const graph = graphCoordinates(request);
  const inserted = await connection.query<InsertResultRow>({
    name: "work.success.result_insert",
    text: `
SELECT omi_memory.insert_durable_work_success_result(
  $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
  $11, $12, $13, $14, $15, $16, $17, $18,
  $19, $20, $21
) AS inserted
`,
    values: [
      context.account_id, succeeded.job_id, stateRevision, stateDigest,
      succeeded.work_kind, succeeded.input_frontier, request.result_kind,
      request.response_digest, request.result_digest, graph.origin_code,
      graphCommitId, graphSequence, graph.graph_success_kind,
      graph.append_receipt_state, request.staged_result.staged_result_id,
      request.staged_result.normalized_result_digest,
      successContentHash(request, stateRevision, stateDigest, graphSequence),
      durableMemoryWorkStateDigest(request.leased_job), request.leased_job.attempt,
      request.leased_job.lease_fence, context.principal_id,
    ],
  });
  if (inserted.length !== 1 || inserted[0]?.inserted !== true
    || Object.keys(inserted[0]).length !== 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  await executeOne(connection, {
    name: "work.success.head_cas",
    text: `
UPDATE omi_memory.memory_work_heads
SET state_revision = $3, state_digest = $4, updated_at = transaction_timestamp()
WHERE account_id = $1 AND job_id = $2
  AND state_revision = $5 AND state_digest = $6
`,
    values: [
      context.account_id, succeeded.job_id, stateRevision, stateDigest,
      currentRevision, row.state_digest,
    ],
  });
  const outboxId = durableMemoryWorkSuccessOutboxId(request);
  await executeOne(connection, {
    name: "work.success.outbox_insert",
    text: `
INSERT INTO omi_memory.memory_work_outbox_events
  (account_id, outbox_id, job_id, terminal_state_revision,
   terminal_state_digest, terminal_state, event_kind, result_digest,
   created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, 'succeeded',
        'memory_work_succeeded', $6, $7, $8)
`,
    values: [
      context.account_id, outboxId, succeeded.job_id, stateRevision, stateDigest,
      request.result_digest, dbNowEpochSeconds,
      outboxContentHash(request, outboxId, stateRevision, stateDigest, dbNowEpochSeconds),
    ],
  });
  return Object.freeze({
    kind: "committed" as const,
    job: succeeded,
    commit_id: graphCommitId,
    sequence: graphSequence,
    outbox_id: outboxId,
  });
};

const commonFailure = (error: unknown): unknown => {
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
    case "stale_parent":
      return Object.freeze({ kind: "stale_parent" as const });
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    default:
      throw error;
  }
};

export interface PostgresDurableMemoryWorkSuccessOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Inert atomic-success adapter. No worker loop, route, provider, or production
 * runtime composition is added by constructing this repository.
 */
export const createPostgresDurableMemoryWorkSuccessRepository = (
  options: PostgresDurableMemoryWorkSuccessOptions,
): DurableMemoryWorkSuccessRepository => defineDurableMemoryWorkSuccessRepository(
  async (context, request) => {
    try {
      return await withAuthorizedSerializableConnectionTransaction(
        options.pool,
        context,
        ({ authority, connection, dbNowEpochSeconds }) => commitWithinTransaction(
          connection, authority, dbNowEpochSeconds, request,
        ),
        options.observability ?? {},
      );
    } catch (error) {
      return commonFailure(error);
    }
  },
);
