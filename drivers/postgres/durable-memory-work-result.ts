import {
  durableMemoryWorkStateDigest,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineDurableMemoryWorkResultRepository,
  materializeStagedDurableMemoryWorkResult,
  parseStagedDurableMemoryWorkResult,
  type DurableMemoryWorkResultLoadRequest,
  type DurableMemoryWorkResultRepository,
  type DurableMemoryWorkResultStageRequest,
  type StagedDurableMemoryWorkResult,
} from "../../apps/service/stores/durable-memory-work-result-repository";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
} from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface CurrentLeaseRow extends Record<string, unknown> {
  readonly account_id: string;
  readonly job_id: string;
  readonly account_epoch: number | string | bigint;
  readonly accepted_work_digest: string;
  readonly work_kind: string;
  readonly input_frontier: string;
  readonly execution_contract_digest: string;
  readonly state: string;
  readonly state_digest: string;
  readonly attempt: number | string | bigint;
  readonly lease_fence: number | string | bigint;
  readonly worker_id: string | null;
  readonly lease_expires_at_event_time: number | string | bigint | null;
}

interface StagedResultRow extends Record<string, unknown> {
  readonly result_version: string;
  readonly staged_result_id: string;
  readonly account_id: string;
  readonly job_id: string;
  readonly accepted_work_digest: string;
  readonly work_kind: string;
  readonly input_frontier: string;
  readonly execution_contract_digest: string;
  readonly produced_attempt: number | string | bigint;
  readonly produced_lease_fence: number | string | bigint;
  readonly produced_state_digest: string;
  readonly producer_worker_id: string;
  readonly result_contract_version: string;
  readonly response_digest: string;
  readonly normalized_result_digest: string;
  readonly normalized_result_json: unknown;
  readonly stage_request_digest: string;
  readonly content_hash: string;
}

interface InsertResultRow extends Record<string, unknown> {
  readonly inserted: boolean;
}

const LEASE_KEYS = [
  "account_id", "job_id", "account_epoch", "accepted_work_digest", "work_kind",
  "input_frontier", "execution_contract_digest", "state", "state_digest", "attempt",
  "lease_fence", "worker_id", "lease_expires_at_event_time",
] as const;

const RESULT_KEYS = [
  "result_version", "staged_result_id", "account_id", "job_id",
  "accepted_work_digest", "work_kind", "input_frontier", "execution_contract_digest",
  "produced_attempt", "produced_lease_fence", "produced_state_digest",
  "producer_worker_id", "result_contract_version", "response_digest",
  "normalized_result_digest", "normalized_result_json", "stage_request_digest",
  "content_hash",
] as const;

const CURRENT_LEASE_SELECT = `
SELECT
  a.account_id, a.job_id, a.account_epoch, a.accepted_work_digest,
  a.work_kind, a.input_frontier, a.execution_contract_digest,
  s.state, s.state_digest, s.attempt, s.lease_fence, s.worker_id,
  s.lease_expires_at_event_time
FROM omi_memory.memory_work_acceptances AS a
JOIN omi_memory.memory_work_heads AS h
  ON h.account_id = a.account_id AND h.job_id = a.job_id
JOIN omi_memory.memory_work_state_revisions AS s
  ON s.account_id = h.account_id AND s.job_id = h.job_id
 AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
WHERE a.account_id = $1 AND a.job_id = $2 AND a.account_epoch = $3
`;

const STAGED_RESULT_SELECT = `
SELECT
  result_version, staged_result_id, account_id, job_id,
  accepted_work_digest, work_kind, input_frontier, execution_contract_digest,
  produced_attempt, produced_lease_fence, produced_state_digest,
  producer_worker_id, result_contract_version, response_digest,
  normalized_result_digest, normalized_result_json, stage_request_digest,
  content_hash
FROM omi_memory.read_durable_work_staged_result($1, $2)
`;

const exactKeys = (
  value: Record<string, unknown>,
  expected: readonly string[],
): void => {
  const actual = Object.keys(value).sort();
  const keys = [...expected].sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) {
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
  const normalized = Number(value);
  if (!Number.isSafeInteger(normalized) || normalized < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return normalized;
};

const loadCurrentLease = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  job: Readonly<DurableMemoryWorkJob>,
  dbNowEpochSeconds: number,
  lock: boolean,
): Promise<"eligible" | "stale_lease" | "ineligible_state"> => {
  const rows = await connection.query<CurrentLeaseRow>({
    name: lock ? "work.result.current_lease_locked" : "work.result.current_lease",
    text: `${CURRENT_LEASE_SELECT}${lock ? "FOR UPDATE OF h" : ""}`,
    values: [context.account_id, job.job_id, context.account_epoch],
  });
  if (rows.length === 0) return "ineligible_state";
  const row = rows[0];
  if (rows.length !== 1 || !row) throw new PostgresRepositoryError("persistence_failed");
  exactKeys(row, LEASE_KEYS);
  if (row.state !== "leased") return "ineligible_state";
  const expiresAt = integer(row.lease_expires_at_event_time, true);
  if (row.account_id !== job.owner_account_id
    || row.job_id !== job.job_id
    || integer(row.account_epoch) !== job.account_epoch
    || row.accepted_work_digest !== job.accepted_work_digest
    || row.work_kind !== job.work_kind
    || row.input_frontier !== job.input_frontier
    || row.execution_contract_digest !== job.execution_contract_digest
    || row.state_digest !== durableMemoryWorkStateDigest(job)
    || integer(row.attempt) !== job.attempt
    || integer(row.lease_fence) !== job.lease_fence
    || row.worker_id !== context.principal_id
    || row.worker_id !== job.lease?.worker_id
    || expiresAt !== job.lease?.expires_at_event_time
    || expiresAt === null
    || dbNowEpochSeconds >= expiresAt) {
    return "stale_lease";
  }
  return "eligible";
};

const stagedContentHash = (result: StagedDurableMemoryWorkResult): string =>
  sha256CanonicalContent({
    contract_version: "durable-memory-work-staged-result-content-v1",
    staged_result: result,
  });

const parseRow = (row: StagedResultRow): Readonly<StagedDurableMemoryWorkResult> => {
  exactKeys(row, RESULT_KEYS);
  let result: Readonly<StagedDurableMemoryWorkResult>;
  try {
    result = parseStagedDurableMemoryWorkResult({
      version: row.result_version,
      staged_result_id: row.staged_result_id,
      owner_account_id: row.account_id,
      job_id: row.job_id,
      accepted_work_digest: row.accepted_work_digest,
      work_kind: row.work_kind,
      input_frontier: row.input_frontier,
      execution_contract_digest: row.execution_contract_digest,
      produced_attempt: integer(row.produced_attempt),
      produced_lease_fence: integer(row.produced_lease_fence),
      produced_state_digest: row.produced_state_digest,
      producer_worker_id: row.producer_worker_id,
      result_contract_version: row.result_contract_version,
      response_digest: row.response_digest,
      normalized_result_digest: row.normalized_result_digest,
      normalized_result: row.normalized_result_json,
      stage_request_digest: row.stage_request_digest,
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (row.content_hash !== stagedContentHash(result)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return result;
};

const loadStaged = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  jobId: string,
): Promise<Readonly<StagedDurableMemoryWorkResult> | null> => {
  const rows = await connection.query<StagedResultRow>({
    name: "work.result.load_staged",
    text: STAGED_RESULT_SELECT,
    values: [accountId, jobId],
  });
  if (rows.length === 0) return null;
  if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
  return parseRow(rows[0]);
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
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    default:
      throw error;
  }
};

const load = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkResultLoadRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, dbNowEpochSeconds }) => {
        const eligibility = await loadCurrentLease(
          connection, authority, request.leased_job, dbNowEpochSeconds, false,
        );
        if (eligibility !== "eligible") return Object.freeze({ kind: eligibility });
        const result = await loadStaged(connection, authority.account_id, request.leased_job.job_id);
        return result
          ? Object.freeze({ kind: "found" as const, result })
          : Object.freeze({ kind: "missing" as const });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

const stage = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkResultStageRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, dbNowEpochSeconds }) => {
        const eligibility = await loadCurrentLease(
          connection, authority, request.leased_job, dbNowEpochSeconds, true,
        );
        if (eligibility !== "eligible") return Object.freeze({ kind: eligibility });
        const expected = materializeStagedDurableMemoryWorkResult(request);
        const existing = await loadStaged(connection, authority.account_id, request.leased_job.job_id);
        if (existing) {
          return sha256CanonicalContent(existing) === sha256CanonicalContent(expected)
            ? Object.freeze({ kind: "replayed" as const, result: existing })
            : Object.freeze({ kind: "idempotency_conflict" as const });
        }
        const inserted = await connection.query<InsertResultRow>({
          name: "work.result.stage_insert",
          text: `
SELECT omi_memory.insert_durable_work_staged_result(
  $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
  $12, $13, $14, $15, ($16::text)::jsonb, $17, $18
) AS inserted
`,
          values: [
            expected.owner_account_id, expected.staged_result_id, expected.job_id,
            expected.version, expected.accepted_work_digest, expected.work_kind,
            expected.input_frontier, expected.execution_contract_digest,
            expected.produced_attempt, expected.produced_lease_fence,
            expected.produced_state_digest, expected.producer_worker_id,
            expected.result_contract_version, expected.response_digest,
            expected.normalized_result_digest, JSON.stringify(expected.normalized_result),
            expected.stage_request_digest, stagedContentHash(expected),
          ],
        });
        if (inserted.length !== 1 || inserted[0]?.inserted !== true
          || Object.keys(inserted[0]).length !== 1) {
          throw new PostgresRepositoryError("persistence_failed");
        }
        return Object.freeze({ kind: "staged" as const, result: expected });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

export interface PostgresDurableMemoryWorkResultOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/** Inert sensitive-result adapter; no model, worker loop, success, or route is composed. */
export const createPostgresDurableMemoryWorkResultRepository = (
  options: PostgresDurableMemoryWorkResultOptions,
): DurableMemoryWorkResultRepository => defineDurableMemoryWorkResultRepository({
  load: (context, request) => load(
    options.pool, context, request, options.observability ?? {},
  ),
  stage: (context, request) => stage(
    options.pool, context, request, options.observability ?? {},
  ),
});
