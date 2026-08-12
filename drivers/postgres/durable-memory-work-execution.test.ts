import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  registerDurableMemoryWorkExecutionPolicy,
} from "../../core/consolidate/execution-policy";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  durableMemoryWorkStateDigest,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresDurableMemoryWorkExecutionRepository } from "./durable-memory-work-execution";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";
const contractDigest = digest("c");

const accepted = acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:formation:one",
  owner_account_id: owner,
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "formation",
  input_frontier: "frontier:one",
  input_digest: digest("b"),
  execution_contract_digest: contractDigest,
  accepted_at_event_time: 90,
  max_attempts: 2,
});

const policy = registerDurableMemoryWorkExecutionPolicy({
  version: DURABLE_MEMORY_WORK_EXECUTION_POLICY_VERSION,
  policy_id: "execution-policy:formation:v1",
  work_kind: "formation",
  execution_contract_digest: contractDigest,
  max_attempts: 2,
  lease_duration_seconds: 30,
  retry_delays_seconds: [10],
});

const authorityRow = (now: number, principal = "worker:one"): AuthorityStateRow => ({
  account_id: owner, principal_id: principal, application_id: "app:worker",
  credential_id: `credential:${principal}`, credential_generation: 1,
  capability: "memories.work.execute", grant_id: `grant:${principal}`, grant_version: 1,
  account_epoch: 7, control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 1_000,
  control_revision: 17, control_content_hash: digest("1"),
  credential_content_hash: digest("2"), grant_content_hash: digest("3"),
  db_now_epoch_seconds: now,
});

const context = (principal = "worker:one") => {
  const row = authorityRow(100, principal);
  return createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: principal, account_id: owner, application_id: "app:worker",
    credential_id: row.credential_id, credential_generation: 1,
    capability: "memories.work.execute", grant_id: row.grant_id, grant_version: 1,
    account_epoch: 7, destination_activation_revision: 17,
    lifecycle_state: "active", deletion_epoch: null,
    authentication_strength: "service-workload", issued_at_epoch_seconds: 80,
    expires_at_epoch_seconds: 900,
    authorization_state_digest: authorizationStateDigest(row),
  }, 100);
};

const stateColumns = (job: Readonly<DurableMemoryWorkJob>) => {
  const retry = job.outcome?.kind === "retryable_error" ? job.outcome : null;
  const dead = job.outcome?.kind === "dead_letter" ? job.outcome : null;
  const success = job.outcome?.kind === "succeeded" ? job.outcome : null;
  return {
    state: job.state, attempt: job.attempt, lease_fence: job.lease_fence,
    worker_id: job.lease?.worker_id ?? null,
    leased_at_event_time: job.lease?.leased_at_event_time ?? null,
    lease_expires_at_event_time: job.lease?.expires_at_event_time ?? null,
    error_code: retry?.error_code ?? dead?.error_code ?? null,
    failed_at_event_time: retry?.failed_at_event_time ?? dead?.failed_at_event_time ?? null,
    next_eligible_event_time: retry?.next_eligible_event_time ?? null,
    result_kind: success?.result_kind ?? null,
    response_digest: success?.response_digest ?? null,
    result_digest: success?.result_digest ?? null,
    succeeded_at_event_time: success?.succeeded_at_event_time ?? null,
  };
};

const workRow = (
  job: Readonly<DurableMemoryWorkJob>,
  stateRevision = 0,
  stateDigest = durableMemoryWorkStateDigest(job),
) => ({
  account_id: job.owner_account_id, job_id: job.job_id, work_version: job.version,
  account_epoch: String(job.account_epoch), lifecycle_state: job.lifecycle_state,
  deletion_epoch: job.deletion_epoch, work_kind: job.work_kind,
  input_frontier: job.input_frontier, input_digest: job.input_digest,
  execution_contract_digest: job.execution_contract_digest,
  accepted_at_event_time: String(job.accepted_at_event_time),
  max_attempts: job.max_attempts, accepted_work_digest: job.accepted_work_digest,
  execution_policy_id: policy.policy_id, execution_policy_digest: policy.policy_digest,
  state_revision: String(stateRevision), state_digest: stateDigest,
  ...stateColumns(job),
  persisted_policy_id: policy.policy_id, policy_version: policy.version,
  persisted_policy_digest: policy.policy_digest, policy_work_kind: policy.work_kind,
  policy_execution_contract_digest: policy.execution_contract_digest,
  policy_max_attempts: policy.max_attempts,
  lease_duration_seconds: policy.lease_duration_seconds,
  retry_delays_seconds: [...policy.retry_delays_seconds],
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "one" });
  readonly statements: SqlStatement[] = [];
  row: Record<string, unknown> | null = workRow(accepted);
  pendingRow: Record<string, unknown> | null = null;
  outboxRows = 0;
  now = 100;
  principal = "worker:one";
  skipLocked = false;

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") {
      return [authorityRow(this.now, this.principal) as unknown as Row];
    }
    if (statement.name === "work.execution.lease_candidate") {
      if (!this.row || this.skipLocked) return [];
      const state = this.row["state"];
      const next = this.row["next_eligible_event_time"];
      const eligible = state === "pending"
        || (state === "retryable_failed" && typeof next === "number" && next <= this.now);
      return eligible ? [structuredClone(this.row) as Row] : [];
    }
    if (statement.name === "work.execution.load" || statement.name === "work.execution.load_locked") {
      return this.row && statement.values[1] === this.row["job_id"]
        ? [structuredClone(this.row) as Row] : [];
    }
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (statement.name === "work.execution.state_insert") {
      if (!this.row) return { rowCount: 0 };
      this.pendingRow = {
        ...this.row,
        state_revision: String(statement.values[2]), state_digest: statement.values[3],
        state: statement.values[4], attempt: statement.values[5], lease_fence: statement.values[6],
        worker_id: statement.values[7], leased_at_event_time: statement.values[8],
        lease_expires_at_event_time: statement.values[9], error_code: statement.values[10],
        failed_at_event_time: statement.values[11], next_eligible_event_time: statement.values[12],
        result_kind: statement.values[13], response_digest: statement.values[14],
        result_digest: statement.values[15], succeeded_at_event_time: statement.values[16],
      };
      return { rowCount: 1 };
    }
    if (statement.name === "work.execution.head_cas") {
      if (!this.row || !this.pendingRow
        || String(this.row["state_revision"]) !== String(statement.values[4])
        || this.row["state_digest"] !== statement.values[5]) return { rowCount: 0 };
      this.row = this.pendingRow;
      this.pendingRow = null;
      return { rowCount: 1 };
    }
    if (statement.name === "work.execution.dead_letter_outbox_insert") {
      this.outboxRows += 1;
      return { rowCount: 1 };
    }
    return { rowCount: 0 };
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  constructor(readonly connection: FakeConnection) {}

  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.options.push(options);
    const snapshot = structuredClone({
      row: this.connection.row,
      pendingRow: this.connection.pendingRow,
      outboxRows: this.connection.outboxRows,
    });
    try {
      return await callback(this.connection);
    } catch (error) {
      this.connection.row = snapshot.row;
      this.connection.pendingRow = snapshot.pendingRow;
      this.connection.outboxRows = snapshot.outboxRows;
      throw error;
    }
  }
}

describe("PostgreSQL durable work execution", () => {
  test("leases one eligible job with database time and the exact persisted lease duration", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresDurableMemoryWorkExecutionRepository({ pool });
    const authorized = context();
    await expect(repository.leaseNext(authorized, { work_kinds: ["formation"] }))
      .resolves.toMatchObject({
        kind: "leased",
        job: {
          state: "leased", attempt: 1, lease_fence: 1,
          lease: { worker_id: "worker:one", leased_at_event_time: 100, expires_at_event_time: 130 },
        },
      });
    await expect(repository.load(authorized, { job_id: accepted.job_id }))
      .resolves.toMatchObject({ kind: "found", job: { state: "leased", attempt: 1 } });
    await expect(repository.leaseNext(authorized, { work_kinds: ["formation"] }))
      .resolves.toEqual({ kind: "none_available" });
    expect(connection.statements.map((statement) => statement.name)).toEqual(expect.arrayContaining([
      "work.execution.lease_candidate", "work.execution.state_insert", "work.execution.head_cas",
    ]));
    expect(pool.options.every((option) =>
      option.isolationLevel === "serializable" && option.accessMode === "read write")).toBe(true);
  });

  test("policy retry delay gates the second lease and final failure atomically dead-letters", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkExecutionRepository({
      pool: new FakePool(connection),
    });
    const authorized = context();
    const first = await repository.leaseNext(authorized, { work_kinds: ["formation"] });
    expect(first.kind).toBe("leased");
    await expect(repository.recordFailure(authorized, {
      job_id: accepted.job_id, lease_fence: 1, error_code: "model_timeout",
    })).resolves.toMatchObject({
      kind: "recorded",
      job: {
        state: "retryable_failed", attempt: 1,
        outcome: { error_code: "model_timeout", failed_at_event_time: 100, next_eligible_event_time: 110 },
      },
    });
    connection.now = 109;
    await expect(repository.leaseNext(authorized, { work_kinds: ["formation"] }))
      .resolves.toEqual({ kind: "none_available" });
    connection.now = 110;
    await expect(repository.leaseNext(authorized, { work_kinds: ["formation"] }))
      .resolves.toMatchObject({ kind: "leased", job: { attempt: 2, lease_fence: 2 } });
    await expect(repository.recordFailure(authorized, {
      job_id: accepted.job_id, lease_fence: 2, error_code: "model_response_invalid",
    })).resolves.toMatchObject({
      kind: "recorded",
      job: { state: "dead_letter", attempt: 2, outcome: { attempts: 2 } },
    });
    expect(connection.outboxRows).toBe(1);
    await expect(repository.recordFailure(authorized, {
      job_id: accepted.job_id, lease_fence: 2, error_code: "model_response_invalid",
    })).resolves.toEqual({ kind: "ineligible_state" });
  });

  test("stale fences do not mutate and expired leases recover as explicit worker loss", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkExecutionRepository({
      pool: new FakePool(connection),
    });
    const authorized = context();
    await repository.leaseNext(authorized, { work_kinds: ["formation"] });
    const before = structuredClone(connection.row);
    await expect(repository.recordFailure(authorized, {
      job_id: accepted.job_id, lease_fence: 2, error_code: "model_timeout",
    })).resolves.toEqual({ kind: "stale_lease" });
    expect(connection.row).toEqual(before);
    connection.now = 129;
    await expect(repository.recoverExpired(authorized, { job_id: accepted.job_id }))
      .resolves.toEqual({ kind: "not_expired" });
    connection.now = 130;
    await expect(repository.recoverExpired(authorized, { job_id: accepted.job_id }))
      .resolves.toMatchObject({
        kind: "recovered",
        job: {
          state: "retryable_failed",
          outcome: { error_code: "worker_lost", next_eligible_event_time: 140 },
        },
      });
    expect(connection.outboxRows).toBe(0);
  });

  test("locked work is skipped and corrupted policy/state rows fail without raw detail", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkExecutionRepository({
      pool: new FakePool(connection),
    });
    connection.skipLocked = true;
    await expect(repository.leaseNext(context(), { work_kinds: ["formation"] }))
      .resolves.toEqual({ kind: "none_available" });
    connection.skipLocked = false;
    connection.row = { ...connection.row!, policy_digest: "secret transcript" };
    await expect(repository.load(context(), { job_id: accepted.job_id })).rejects.toMatchObject({
      code: "persistence_failed", message: "persistence_failed",
    });
    expect(JSON.stringify(connection.statements)).not.toContain("secret transcript");
  });
});

