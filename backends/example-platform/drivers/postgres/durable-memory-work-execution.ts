import {
  durableMemoryWorkRetryDelaySeconds,
  parseRegisteredDurableMemoryWorkExecutionPolicy,
  type RegisteredDurableMemoryWorkExecutionPolicy,
} from "../../core/consolidate/execution-policy";
import {
  durableMemoryWorkStateDigest,
  expireDurableMemoryWorkLease,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
  parseDurableMemoryWorkJob,
  type DurableMemoryWorkErrorCode,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  defineDurableMemoryWorkExecutionRepository,
  type DurableMemoryWorkExecutionRepository,
  type DurableMemoryWorkFailureRequest,
  type DurableMemoryWorkJobRequest,
  type DurableMemoryWorkLeaseNextRequest,
} from "../../apps/service/stores/durable-memory-work-repository";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlStatement,
  SqlValue,
} from "./connection";
import {
  PostgresRepositoryError,
  type PostgresTransactionObservability,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

interface WorkRow extends Record<string, unknown> {
  readonly account_id: string;
  readonly job_id: string;
  readonly work_version: string;
  readonly account_epoch: number | string | bigint;
  readonly lifecycle_state: string;
  readonly deletion_epoch: number | string | bigint | null;
  readonly work_kind: string;
  readonly input_frontier: string;
  readonly input_digest: string;
  readonly execution_contract_digest: string;
  readonly accepted_at_event_time: number | string | bigint;
  readonly max_attempts: number | string | bigint;
  readonly accepted_work_digest: string;
  readonly execution_policy_id: string;
  readonly execution_policy_digest: string;
  readonly state_revision: number | string | bigint;
  readonly state_digest: string;
  readonly state: string;
  readonly attempt: number | string | bigint;
  readonly lease_fence: number | string | bigint;
  readonly worker_id: string | null;
  readonly leased_at_event_time: number | string | bigint | null;
  readonly lease_expires_at_event_time: number | string | bigint | null;
  readonly error_code: string | null;
  readonly failed_at_event_time: number | string | bigint | null;
  readonly next_eligible_event_time: number | string | bigint | null;
  readonly result_kind: string | null;
  readonly response_digest: string | null;
  readonly result_digest: string | null;
  readonly succeeded_at_event_time: number | string | bigint | null;
  readonly persisted_policy_id: string;
  readonly policy_version: string;
  readonly persisted_policy_digest: string;
  readonly policy_work_kind: string;
  readonly policy_execution_contract_digest: string;
  readonly policy_max_attempts: number | string | bigint;
  readonly lease_duration_seconds: number | string | bigint;
  readonly retry_delays_seconds: unknown;
}

interface LoadedWork {
  readonly job: Readonly<DurableMemoryWorkJob>;
  readonly policy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
  readonly state_revision: number;
  readonly state_digest: string;
}

const WORK_ROW_KEYS = [
  "account_id", "job_id", "work_version", "account_epoch", "lifecycle_state",
  "deletion_epoch", "work_kind", "input_frontier", "input_digest",
  "execution_contract_digest", "accepted_at_event_time", "max_attempts",
  "accepted_work_digest", "execution_policy_id", "execution_policy_digest",
  "state_revision", "state_digest", "state", "attempt", "lease_fence",
  "worker_id", "leased_at_event_time", "lease_expires_at_event_time",
  "error_code", "failed_at_event_time", "next_eligible_event_time",
  "result_kind", "response_digest", "result_digest", "succeeded_at_event_time",
  "persisted_policy_id", "policy_version", "persisted_policy_digest",
  "policy_work_kind", "policy_execution_contract_digest", "policy_max_attempts",
  "lease_duration_seconds", "retry_delays_seconds",
] as const;

const WORK_SELECT = `
SELECT
  a.account_id, a.job_id, a.work_version, a.account_epoch,
  a.lifecycle_state, a.deletion_epoch, a.work_kind, a.input_frontier,
  a.input_digest, a.execution_contract_digest, a.accepted_at_event_time,
  a.max_attempts, a.accepted_work_digest,
  a.execution_policy_id, a.execution_policy_digest,
  s.state_revision, s.state_digest, s.state, s.attempt, s.lease_fence,
  s.worker_id, s.leased_at_event_time, s.lease_expires_at_event_time,
  s.error_code, s.failed_at_event_time, s.next_eligible_event_time,
  s.result_kind, s.response_digest, s.result_digest, s.succeeded_at_event_time,
  p.policy_id AS persisted_policy_id, p.policy_version,
  p.policy_digest AS persisted_policy_digest,
  p.work_kind AS policy_work_kind,
  p.execution_contract_digest AS policy_execution_contract_digest,
  p.max_attempts AS policy_max_attempts,
  p.lease_duration_seconds, p.retry_delays_seconds
FROM omi_memory.memory_work_acceptances AS a
JOIN omi_memory.memory_work_heads AS h
  ON h.account_id = a.account_id AND h.job_id = a.job_id
JOIN omi_memory.memory_work_state_revisions AS s
  ON s.account_id = h.account_id AND s.job_id = h.job_id
 AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
JOIN omi_memory.memory_work_execution_policies AS p
  ON p.account_id = a.account_id
 AND p.policy_id = a.execution_policy_id
 AND p.policy_digest = a.execution_policy_digest
 AND p.work_kind = a.work_kind
 AND p.execution_contract_digest = a.execution_contract_digest
 AND p.max_attempts = a.max_attempts
`;

const exactRow = (value: Record<string, unknown>): void => {
  const keys = Object.keys(value).sort();
  const expected = [...WORK_ROW_KEYS].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
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

const string = (value: unknown, nullable = false): string | null => {
  if (value === null && nullable) return null;
  if (typeof value !== "string") throw new PostgresRepositoryError("persistence_failed");
  return value;
};

const loadRow = (row: WorkRow): LoadedWork => {
  exactRow(row);
  let policy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
  let job: Readonly<DurableMemoryWorkJob>;
  try {
    policy = parseRegisteredDurableMemoryWorkExecutionPolicy({
      version: string(row.policy_version),
      policy_id: string(row.persisted_policy_id),
      work_kind: string(row.policy_work_kind),
      execution_contract_digest: string(row.policy_execution_contract_digest),
      max_attempts: integer(row.policy_max_attempts),
      lease_duration_seconds: integer(row.lease_duration_seconds),
      retry_delays_seconds: row.retry_delays_seconds,
      policy_digest: string(row.persisted_policy_digest),
    });
    const state = string(row.state);
    const attempt = integer(row.attempt)!;
    const workerId = string(row.worker_id, true);
    const leasedAt = integer(row.leased_at_event_time, true);
    const leaseExpires = integer(row.lease_expires_at_event_time, true);
    const errorCode = string(row.error_code, true);
    const failedAt = integer(row.failed_at_event_time, true);
    const nextEligible = integer(row.next_eligible_event_time, true);
    const resultKind = string(row.result_kind, true);
    const responseDigest = string(row.response_digest, true);
    const resultDigest = string(row.result_digest, true);
    const succeededAt = integer(row.succeeded_at_event_time, true);
    const lease = state === "leased" ? {
      worker_id: workerId,
      fence: integer(row.lease_fence),
      leased_at_event_time: leasedAt,
      expires_at_event_time: leaseExpires,
    } : null;
    const outcome = state === "retryable_failed" ? {
      kind: "retryable_error", error_code: errorCode,
      failed_at_event_time: failedAt, next_eligible_event_time: nextEligible,
    } : state === "dead_letter" ? {
      kind: "dead_letter", error_code: errorCode, attempts: attempt,
      failed_at_event_time: failedAt,
    } : state === "succeeded" ? {
      kind: "succeeded", result_kind: resultKind, response_digest: responseDigest,
      result_digest: resultDigest, succeeded_at_event_time: succeededAt,
    } : null;
    job = parseDurableMemoryWorkJob({
      version: string(row.work_version),
      job_id: string(row.job_id),
      owner_account_id: string(row.account_id),
      account_epoch: integer(row.account_epoch),
      lifecycle_state: string(row.lifecycle_state),
      deletion_epoch: integer(row.deletion_epoch, true),
      work_kind: string(row.work_kind),
      input_frontier: string(row.input_frontier),
      input_digest: string(row.input_digest),
      execution_contract_digest: string(row.execution_contract_digest),
      accepted_at_event_time: integer(row.accepted_at_event_time),
      max_attempts: integer(row.max_attempts),
      accepted_work_digest: string(row.accepted_work_digest),
      state,
      attempt,
      lease_fence: integer(row.lease_fence),
      lease,
      outcome,
    });
  } catch {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const persistedStateDigest = string(row.state_digest)!;
  if (policy.policy_id !== row.execution_policy_id
    || policy.policy_digest !== row.execution_policy_digest
    || policy.work_kind !== job.work_kind
    || policy.execution_contract_digest !== job.execution_contract_digest
    || policy.max_attempts !== job.max_attempts
    || durableMemoryWorkStateDigest(job) !== persistedStateDigest) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({
    job,
    policy,
    state_revision: integer(row.state_revision)!,
    state_digest: persistedStateDigest,
  });
};

const oneLoaded = (rows: readonly WorkRow[]): LoadedWork | null => {
  if (rows.length === 0) return null;
  if (rows.length !== 1 || !rows[0]) throw new PostgresRepositoryError("persistence_failed");
  return loadRow(rows[0]);
};

const safeAdd = (left: number, right: number): number => {
  const value = left + right;
  if (!Number.isSafeInteger(value) || value < 0) throw new PostgresRepositoryError("persistence_failed");
  return value;
};

const executeOne = async (
  connection: CheckedOutPostgresConnection,
  statement: SqlStatement,
): Promise<void> => {
  if ((await connection.execute(statement)).rowCount !== 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const insertState = async (
  connection: CheckedOutPostgresConnection,
  loaded: LoadedWork,
  next: Readonly<DurableMemoryWorkJob>,
  now: number,
): Promise<LoadedWork> => {
  const nextRevision = safeAdd(loaded.state_revision, 1);
  const stateDigest = durableMemoryWorkStateDigest(next);
  const retry = next.outcome?.kind === "retryable_error" ? next.outcome : null;
  const dead = next.outcome?.kind === "dead_letter" ? next.outcome : null;
  const success = next.outcome?.kind === "succeeded" ? next.outcome : null;
  await executeOne(connection, {
    name: "work.execution.state_insert",
    text: `
INSERT INTO omi_memory.memory_work_state_revisions
  (account_id, job_id, state_revision, state_digest, state, attempt, lease_fence,
   worker_id, leased_at_event_time, lease_expires_at_event_time,
   error_code, failed_at_event_time, next_eligible_event_time,
   result_kind, response_digest, result_digest, succeeded_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7,
        $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $4)
`,
    values: [
      next.owner_account_id, next.job_id, nextRevision, stateDigest, next.state,
      next.attempt, next.lease_fence, next.lease?.worker_id ?? null,
      next.lease?.leased_at_event_time ?? null,
      next.lease?.expires_at_event_time ?? null,
      retry?.error_code ?? dead?.error_code ?? null,
      retry?.failed_at_event_time ?? dead?.failed_at_event_time ?? null,
      retry?.next_eligible_event_time ?? null,
      success?.result_kind ?? null, success?.response_digest ?? null,
      success?.result_digest ?? null, success?.succeeded_at_event_time ?? null,
    ],
  });
  await executeOne(connection, {
    name: "work.execution.head_cas",
    text: `
UPDATE omi_memory.memory_work_heads
SET state_revision = $3, state_digest = $4, updated_at = transaction_timestamp()
WHERE account_id = $1 AND job_id = $2
  AND state_revision = $5 AND state_digest = $6
`,
    values: [
      next.owner_account_id, next.job_id, nextRevision, stateDigest,
      loaded.state_revision, loaded.state_digest,
    ],
  });
  if (next.state === "dead_letter") {
    const outbox = Object.freeze({
      contract_version: "durable-memory-work-dead-letter-outbox-v1",
      account_id: next.owner_account_id,
      job_id: next.job_id,
      state_revision: nextRevision,
      state_digest: stateDigest,
    });
    const outboxId = `mwd1_${sha256CanonicalContent(outbox)}`;
    await executeOne(connection, {
      name: "work.execution.dead_letter_outbox_insert",
      text: `
INSERT INTO omi_memory.memory_work_outbox_events
  (account_id, outbox_id, job_id, terminal_state_revision,
   terminal_state_digest, terminal_state, event_kind, result_digest,
   created_at_event_time, content_hash)
VALUES ($1, $2, $3, $4, $5, 'dead_letter',
        'memory_work_dead_letter', NULL, $6, $7)
`,
      values: [
        next.owner_account_id, outboxId, next.job_id, nextRevision,
        stateDigest, now, sha256CanonicalContent({ ...outbox, outbox_id: outboxId }),
      ],
    });
  }
  return Object.freeze({
    job: next,
    policy: loaded.policy,
    state_revision: nextRevision,
    state_digest: stateDigest,
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
    case "retryable_serialization":
      return Object.freeze({ kind: "serialization_retryable" as const });
    default:
      throw error;
  }
};

const loadSpecific = async (
  connection: CheckedOutPostgresConnection,
  context: AuthorizedLedgerWriteContext,
  jobId: string,
  lock: boolean,
): Promise<LoadedWork | null> => oneLoaded(await connection.query<WorkRow>({
  name: lock ? "work.execution.load_locked" : "work.execution.load",
  text: `${WORK_SELECT}
WHERE a.account_id = $1 AND a.job_id = $2 AND a.account_epoch = $3
${lock ? "FOR UPDATE OF h" : ""}
`,
  values: [context.account_id, jobId, context.account_epoch],
}));

const leaseNext = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkLeaseNextRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, dbNowEpochSeconds }) => {
        const kindPlaceholders = request.work_kinds.map((_, index) => `$${index + 4}`).join(", ");
        const loaded = oneLoaded(await connection.query<WorkRow>({
          name: "work.execution.lease_candidate",
          text: `${WORK_SELECT}
WHERE a.account_id = $1 AND a.account_epoch = $2
  AND a.accepted_at_event_time <= $3
  AND a.work_kind IN (${kindPlaceholders})
  AND (
    s.state = 'pending'
    OR (s.state = 'retryable_failed' AND s.next_eligible_event_time <= $3)
  )
ORDER BY a.accepted_at_event_time, a.job_id
FOR UPDATE OF h SKIP LOCKED
LIMIT 1
`,
          values: [
            authority.account_id, authority.account_epoch, dbNowEpochSeconds,
            ...request.work_kinds,
          ],
        }));
        if (!loaded) return Object.freeze({ kind: "none_available" as const });
        const leased = leaseDurableMemoryWork(
          loaded.job,
          authority.principal_id,
          dbNowEpochSeconds,
          loaded.policy.lease_duration_seconds,
        );
        await insertState(connection, loaded, leased, dbNowEpochSeconds);
        return Object.freeze({ kind: "leased" as const, job: leased });
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
  request: DurableMemoryWorkJobRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        const loaded = await loadSpecific(connection, authority, request.job_id, false);
        return loaded
          ? Object.freeze({ kind: "found" as const, job: loaded.job })
          : Object.freeze({ kind: "not_found" as const });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

const recordFailure = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkFailureRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, dbNowEpochSeconds }) => {
        const loaded = await loadSpecific(connection, authority, request.job_id, true);
        if (!loaded || loaded.job.state !== "leased") {
          return Object.freeze({ kind: "ineligible_state" as const });
        }
        if (loaded.job.lease?.worker_id !== authority.principal_id
          || loaded.job.lease.fence !== request.lease_fence
          || dbNowEpochSeconds >= loaded.job.lease.expires_at_event_time) {
          return Object.freeze({ kind: "stale_lease" as const });
        }
        const delay = durableMemoryWorkRetryDelaySeconds(loaded.policy, loaded.job.attempt);
        const failed = failDurableMemoryWork(
          loaded.job,
          { worker_id: authority.principal_id, fence: request.lease_fence },
          dbNowEpochSeconds,
          request.error_code,
          delay === null ? null : safeAdd(dbNowEpochSeconds, delay),
        );
        await insertState(connection, loaded, failed, dbNowEpochSeconds);
        return Object.freeze({ kind: "recorded" as const, job: failed });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

const recoverExpired = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: DurableMemoryWorkJobRequest,
  observability: PostgresTransactionObservability,
): Promise<unknown> => {
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection, dbNowEpochSeconds }) => {
        const loaded = await loadSpecific(connection, authority, request.job_id, true);
        if (!loaded || loaded.job.state !== "leased" || !loaded.job.lease) {
          return Object.freeze({ kind: "ineligible_state" as const });
        }
        if (dbNowEpochSeconds < loaded.job.lease.expires_at_event_time) {
          return Object.freeze({ kind: "not_expired" as const });
        }
        const delay = durableMemoryWorkRetryDelaySeconds(loaded.policy, loaded.job.attempt);
        const recovered = expireDurableMemoryWorkLease(
          loaded.job,
          dbNowEpochSeconds,
          delay === null ? null : safeAdd(dbNowEpochSeconds, delay),
        );
        await insertState(connection, loaded, recovered, dbNowEpochSeconds);
        return Object.freeze({ kind: "recovered" as const, job: recovered });
      },
      observability,
    );
  } catch (error) {
    return commonFailure(error);
  }
};

export interface PostgresDurableMemoryWorkExecutionOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/** Inert one-shot execution state adapter; no poller, route, or model is composed. */
export const createPostgresDurableMemoryWorkExecutionRepository = (
  options: PostgresDurableMemoryWorkExecutionOptions,
): DurableMemoryWorkExecutionRepository => defineDurableMemoryWorkExecutionRepository({
  leaseNext: (context, request) => leaseNext(
    options.pool, context, request, options.observability ?? {},
  ),
  load: (context, request) => load(
    options.pool, context, request, options.observability ?? {},
  ),
  recordFailure: (context, request) => recordFailure(
    options.pool, context, request, options.observability ?? {},
  ),
  recoverExpired: (context, request) => recoverExpired(
    options.pool, context, request, options.observability ?? {},
  ),
});
