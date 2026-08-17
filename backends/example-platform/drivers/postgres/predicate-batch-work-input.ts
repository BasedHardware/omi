import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { durableMemoryWorkStateDigest, type DurableMemoryWorkJob } from "../../core/consolidate/state-machine";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  definePredicateBatchWorkInputRepository,
  materializeStagedPredicateBatchWorkInput,
  parseStagedPredicateBatchWorkInput,
  type PredicateBatchWorkInputRepository,
  type PredicateBatchWorkInputStageRequest,
  type StagedPredicateBatchWorkInput,
} from "../../apps/service/workers/predicate-batch-work-input-repository";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface InputRow extends Record<string, unknown> {
  readonly input_version: string;
  readonly staged_input_id: string;
  readonly account_id: string;
  readonly job_id: string;
  readonly account_epoch: number | string | bigint;
  readonly accepted_work_digest: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly snapshot_digest: string;
  readonly snapshot_json: unknown;
  readonly stage_request_digest: string;
  readonly content_hash: string;
}

interface LeaseRow extends Record<string, unknown> {
  readonly state: string;
  readonly state_digest: string;
  readonly attempt: number | string | bigint;
  readonly lease_fence: number | string | bigint;
  readonly worker_id: string | null;
  readonly lease_expires_at_event_time: number | string | bigint | null;
}

const INPUT_KEYS = [
  "input_version", "staged_input_id", "account_id", "job_id", "account_epoch",
  "accepted_work_digest", "input_frontier", "input_digest", "execution_contract_digest",
  "snapshot_digest", "snapshot_json", "stage_request_digest", "content_hash",
] as const;
const LEASE_KEYS = [
  "state", "state_digest", "attempt", "lease_fence", "worker_id",
  "lease_expires_at_event_time",
] as const;

const exactKeys = (value: Record<string, unknown>, expected: readonly string[]): void => {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const integer = (value: unknown): number => {
  if (typeof value !== "number" && typeof value !== "string" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const result = Number(value);
  if (!Number.isSafeInteger(result) || result < 0) throw new PostgresRepositoryError("persistence_failed");
  return result;
};

const contentHash = (input: StagedPredicateBatchWorkInput): string => sha256CanonicalContent({
  contract_version: "predicate-batch-work-staged-input-content-v1",
  staged_input: input,
});

const parseRow = (row: InputRow, expectedJob?: DurableMemoryWorkJob): StagedPredicateBatchWorkInput => {
  exactKeys(row, INPUT_KEYS);
  let input: StagedPredicateBatchWorkInput;
  try {
    input = parseStagedPredicateBatchWorkInput({
      version: row.input_version,
      staged_input_id: row.staged_input_id,
      owner_account_id: row.account_id,
      job_id: row.job_id,
      account_epoch: integer(row.account_epoch),
      accepted_work_digest: row.accepted_work_digest,
      input_frontier: row.input_frontier,
      input_digest: row.input_digest,
      execution_contract_digest: row.execution_contract_digest,
      snapshot_digest: row.snapshot_digest,
      snapshot: row.snapshot_json,
      stage_request_digest: row.stage_request_digest,
    }, expectedJob);
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (row.content_hash !== contentHash(input)) throw new PostgresRepositoryError("persistence_failed");
  return input;
};

const read = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  jobId: string,
  expectedJob?: DurableMemoryWorkJob,
): Promise<StagedPredicateBatchWorkInput | null> => {
  const rows = await connection.query<InputRow>({
    name: "predicate.input.read",
    text: "SELECT * FROM omi_memory.read_predicate_batch_work_input($1, $2)",
    values: [accountId, jobId],
  });
  if (rows.length === 0) return null;
  if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
  return parseRow(rows[0], expectedJob);
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

const stage = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: PredicateBatchWorkInputStageRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        await connection.query({
          name: "predicate.input.lock_key",
          text: "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
          values: [`predicate-input:${authority.account_id}:${request.pending_job.job_id}`],
        });
        const expected = materializeStagedPredicateBatchWorkInput(request);
        const existing = await read(connection, authority.account_id, expected.job_id);
        if (existing) {
          return sha256CanonicalContent(existing) === sha256CanonicalContent(expected)
            ? Object.freeze({ kind: "replayed" as const, input: existing })
            : Object.freeze({ kind: "idempotency_conflict" as const });
        }
        const rows = await connection.query<{ inserted: boolean }>({
          name: "predicate.input.insert",
          text: `
SELECT omi_memory.insert_predicate_batch_work_input(
  $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
  ($12::text)::jsonb, $13, $14
) AS inserted
`,
          values: [
            expected.owner_account_id, expected.staged_input_id, expected.job_id,
            expected.version, expected.account_epoch, expected.accepted_work_digest,
            expected.input_frontier, expected.input_digest, expected.execution_contract_digest,
            expected.snapshot_digest, expected.snapshot.version,
            JSON.stringify(expected.snapshot), expected.stage_request_digest, contentHash(expected),
          ],
        });
        if (rows.length !== 1 || rows[0]?.inserted !== true || Object.keys(rows[0]).length !== 1) {
          throw new PostgresRepositoryError("persistence_failed");
        }
        return Object.freeze({ kind: "staged" as const, input: expected });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

const load = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  job: Readonly<DurableMemoryWorkJob>,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, dbNowEpochSeconds }) => {
        const rows = await connection.query<LeaseRow>({
          name: "predicate.input.current_lease",
          text: `
SELECT s.state, s.state_digest, s.attempt, s.lease_fence, s.worker_id,
       s.lease_expires_at_event_time
FROM omi_memory.memory_work_heads AS h
JOIN omi_memory.memory_work_state_revisions AS s
  ON s.account_id = h.account_id AND s.job_id = h.job_id
 AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
WHERE h.account_id = $1 AND h.job_id = $2
`,
          values: [authority.account_id, job.job_id],
        });
        if (rows.length === 0) return Object.freeze({ kind: "ineligible_state" as const });
        if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
        const row = rows[0];
        exactKeys(row, LEASE_KEYS);
        const expiresAt = row.lease_expires_at_event_time === null
          ? null : integer(row.lease_expires_at_event_time);
        if (row.state !== "leased") return Object.freeze({ kind: "ineligible_state" as const });
        if (row.state_digest !== durableMemoryWorkStateDigest(job)
          || integer(row.attempt) !== job.attempt || integer(row.lease_fence) !== job.lease_fence
          || row.worker_id !== authority.principal_id || expiresAt !== job.lease?.expires_at_event_time
          || expiresAt === null || dbNowEpochSeconds >= expiresAt) {
          return Object.freeze({ kind: "stale_lease" as const });
        }
        const input = await read(connection, authority.account_id, job.job_id, job);
        return input
          ? Object.freeze({ kind: "found" as const, input })
          : Object.freeze({ kind: "not_found" as const });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

export interface PostgresPredicateBatchWorkInputOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/** Inert predicate input adapter. It adds no model, scheduler, route, or runtime default. */
export const createPostgresPredicateBatchWorkInputRepository = (
  options: PostgresPredicateBatchWorkInputOptions,
): PredicateBatchWorkInputRepository => definePredicateBatchWorkInputRepository({
  stage: (context, request) => stage(options.pool, context, request, options.observability ?? {}),
  load: (context, job) => load(options.pool, context, job, options.observability ?? {}),
});
