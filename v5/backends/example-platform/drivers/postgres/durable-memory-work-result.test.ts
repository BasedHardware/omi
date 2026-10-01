import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  type DurableMemoryWorkResultStageBody,
  type DurableMemoryWorkResultStageRequest,
} from "../../apps/service/stores/durable-memory-work-result-repository";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  durableMemoryWorkStateDigest,
  expireDurableMemoryWorkLease,
  leaseDurableMemoryWork,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { createPostgresDurableMemoryWorkResultRepository } from "./durable-memory-work-result";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";

const leased = leaseDurableMemoryWork(acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:formation:one",
  owner_account_id: owner,
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "formation",
  input_frontier: "frontier:one",
  input_digest: digest("b"),
  execution_contract_digest: digest("c"),
  accepted_at_event_time: 90,
  max_attempts: 3,
}), "worker:one", 100, 30);

const authorityRow = (now = 101, principal = "worker:one"): AuthorityStateRow => ({
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
  const row = authorityRow(101, principal);
  return createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: principal, account_id: owner, application_id: row.application_id,
    credential_id: row.credential_id, credential_generation: 1,
    capability: "memories.work.execute", grant_id: row.grant_id, grant_version: 1,
    account_epoch: 7, destination_activation_revision: 17,
    lifecycle_state: "active", deletion_epoch: null,
    authentication_strength: "service-workload", issued_at_epoch_seconds: 80,
    expires_at_epoch_seconds: 900,
    authorization_state_digest: authorizationStateDigest(row),
  }, 101);
};

const stageRequest = (
  job: Readonly<DurableMemoryWorkJob> = leased,
  normalizedResult: Record<string, unknown> = { claims: [{ candidate_ref: "candidate:1" }] },
): DurableMemoryWorkResultStageRequest => {
  const resultContractVersion = "formation-result:v2";
  const normalized = normalizedResult as never;
  const body: DurableMemoryWorkResultStageBody = {
    leased_job: job,
    result_contract_version: resultContractVersion,
    response_digest: digest("d"),
    normalized_result_digest: durableMemoryWorkNormalizedResultDigest(
      resultContractVersion, normalized,
    ),
    normalized_result: normalized,
  };
  return Object.freeze({ ...body, request_digest: durableMemoryWorkResultStageRequestDigest(body) });
};

const currentLeaseRow = (job: Readonly<DurableMemoryWorkJob>) => ({
  account_id: job.owner_account_id, job_id: job.job_id,
  account_epoch: String(job.account_epoch), accepted_work_digest: job.accepted_work_digest,
  work_kind: job.work_kind, input_frontier: job.input_frontier,
  execution_contract_digest: job.execution_contract_digest,
  state: job.state, state_digest: durableMemoryWorkStateDigest(job),
  attempt: job.attempt, lease_fence: String(job.lease_fence),
  worker_id: job.lease?.worker_id ?? null,
  lease_expires_at_event_time: job.lease?.expires_at_event_time ?? null,
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "one" });
  readonly statements: SqlStatement[] = [];
  current: Record<string, unknown> | null = currentLeaseRow(leased);
  staged: Record<string, unknown> | null = null;
  now = 101;
  principal = "worker:one";

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") {
      return [authorityRow(this.now, this.principal) as unknown as Row];
    }
    if (statement.name === "work.result.current_lease"
      || statement.name === "work.result.current_lease_locked") {
      return this.current ? [structuredClone(this.current) as Row] : [];
    }
    if (statement.name === "work.result.load_staged") {
      return this.staged ? [structuredClone(this.staged) as Row] : [];
    }
    if (statement.name === "work.result.stage_insert" && !this.staged) {
      const value = statement.values;
      this.staged = {
        account_id: value[0], staged_result_id: value[1], job_id: value[2],
        result_version: value[3], accepted_work_digest: value[4], work_kind: value[5],
        input_frontier: value[6], execution_contract_digest: value[7],
        produced_attempt: value[8], produced_lease_fence: value[9],
        produced_state_digest: value[10], producer_worker_id: value[11],
        result_contract_version: value[12], response_digest: value[13],
        normalized_result_digest: value[14], normalized_result_json: JSON.parse(String(value[15])),
        stage_request_digest: value[16], content_hash: value[17],
      };
      return [{ inserted: true } as unknown as Row];
    }
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
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
    const staged = structuredClone(this.connection.staged);
    try {
      return await callback(this.connection);
    } catch (error) {
      this.connection.staged = staged;
      throw error;
    }
  }
}

describe("PostgreSQL durable work normalized-result staging", () => {
  test("stages and loads one exact sensitive result behind the current database lease", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresDurableMemoryWorkResultRepository({ pool });
    const request = stageRequest();
    await expect(repository.load(context(), { leased_job: leased }))
      .resolves.toEqual({ kind: "missing" });
    const staged = await repository.stage(context(), request);
    expect(staged).toMatchObject({
      kind: "staged",
      result: { job_id: leased.job_id, produced_attempt: 1, producer_worker_id: "worker:one" },
    });
    await expect(repository.load(context(), { leased_job: leased }))
      .resolves.toMatchObject({ kind: "found", result: { normalized_result: request.normalized_result } });
    expect(connection.statements.map((statement) => statement.name)).toEqual(expect.arrayContaining([
      "work.result.current_lease_locked", "work.result.stage_insert", "work.result.load_staged",
    ]));
    expect(pool.options.every((option) => option.isolationLevel === "serializable"
      && option.accessMode === "read write")).toBe(true);
  });

  test("exact stage replay is idempotent while changed normalized bytes conflict", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkResultRepository({ pool: new FakePool(connection) });
    const request = stageRequest();
    await repository.stage(context(), request);
    await expect(repository.stage(context(), request)).resolves.toMatchObject({ kind: "replayed" });
    await expect(repository.stage(context(), stageRequest(leased, { claims: [] })))
      .resolves.toEqual({ kind: "idempotency_conflict" });
    expect(connection.statements.filter((statement) => statement.name === "work.result.stage_insert"))
      .toHaveLength(1);
  });

  test("a later current lease loads the immutable output produced by the first lease", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkResultRepository({ pool: new FakePool(connection) });
    await repository.stage(context(), stageRequest());
    const failed = expireDurableMemoryWorkLease(leased, 130, 131);
    const later = leaseDurableMemoryWork(failed, "worker:two", 131, 30);
    connection.current = currentLeaseRow(later);
    connection.now = 132;
    connection.principal = "worker:two";
    await expect(repository.load(context("worker:two"), { leased_job: later }))
      .resolves.toMatchObject({
        kind: "found",
        result: { produced_attempt: 1, produced_lease_fence: 1, producer_worker_id: "worker:one" },
      });
  });

  test("stale, expired, ineligible, and corrupted coordinates fail closed without raw content", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresDurableMemoryWorkResultRepository({ pool: new FakePool(connection) });
    const request = stageRequest();
    connection.now = 130;
    await expect(repository.stage(context(), request)).resolves.toEqual({ kind: "stale_lease" });
    connection.now = 101;
    connection.current = { ...connection.current!, state: "retryable_failed" };
    await expect(repository.load(context(), { leased_job: leased }))
      .resolves.toEqual({ kind: "ineligible_state" });
    connection.current = currentLeaseRow(leased);
    await repository.stage(context(), request);
    connection.staged = { ...connection.staged!, content_hash: "secret transcript" };
    await expect(repository.load(context(), { leased_job: leased })).rejects.toMatchObject({
      code: "persistence_failed", message: "persistence_failed",
    });
    expect(JSON.stringify(connection.statements)).not.toContain("secret transcript");
  });
});
