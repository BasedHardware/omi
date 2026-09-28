import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import {
  authoritativeAppendRequestDigest,
  type AuthoritativeLedgerAppend,
} from "../../apps/service/stores/authoritative-ledger-repository";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  materializeStagedDurableMemoryWorkResult,
  type DurableMemoryWorkResultStageBody,
} from "../../apps/service/stores/durable-memory-work-result-repository";
import {
  durableMemoryWorkSuccessRequestDigest,
  type DurableMemoryWorkSuccessBody,
  type DurableMemoryWorkSuccessRequest,
} from "../../apps/service/stores/durable-memory-work-success-repository";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  durableMemoryWorkStateDigest,
  leaseDurableMemoryWork,
  type DurableMemoryWorkJob,
} from "../../core/consolidate/state-machine";
import { prepareDerivation, type AtomicGraphTransition } from "../../core/ledger";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import { durableMemoryWorkStagedResultContentHash } from "./durable-memory-work-result";
import { createPostgresDurableMemoryWorkSuccessRepository } from "./durable-memory-work-success";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";

const leased = leaseDurableMemoryWork(acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:predicate_batch:one",
  owner_account_id: owner,
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "predicate_batch",
  input_frontier: "frontier:one",
  input_digest: digest("b"),
  execution_contract_digest: digest("c"),
  accepted_at_event_time: 90,
  max_attempts: 2,
}), "worker:one", 100, 30);

const authorityRow = (now = 101): AuthorityStateRow => ({
  account_id: owner, principal_id: "worker:one", application_id: "app:worker",
  credential_id: "credential:one", credential_generation: 1,
  capability: "memories.work.execute", grant_id: "grant:one", grant_version: 1,
  account_epoch: 7, control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 7, destination_activation_revision: 17,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 1_000,
  control_revision: 17, control_content_hash: digest("1"),
  credential_content_hash: digest("2"), grant_content_hash: digest("3"),
  db_now_epoch_seconds: now,
});

const context = () => {
  const row = authorityRow();
  return createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: row.principal_id, account_id: owner, application_id: row.application_id,
    credential_id: row.credential_id, credential_generation: 1,
    capability: "memories.work.execute", grant_id: row.grant_id, grant_version: 1,
    account_epoch: 7, destination_activation_revision: 17,
    lifecycle_state: "active", deletion_epoch: null,
    authentication_strength: "service-workload", issued_at_epoch_seconds: 80,
    expires_at_epoch_seconds: 900,
    authorization_state_digest: authorizationStateDigest(row),
  }, 101);
};

const append = (): AuthoritativeLedgerAppend => {
  const transition: AtomicGraphTransition = {
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation: prepareDerivation({
      attempt_id: "attempt:predicate:one", commit_id: "commit:predicate:one",
      owner_account_id: owner, parent_commit: null,
      idempotency_key: "append:predicate:one", input_revisions: [], output_revisions: [],
      versions: {
        strategy_version: "strategy:v1", model_version: "model:v1",
        prompt_version: "prompt:v1", policy_version: "policy:v1",
        code_version: "code:v1", schema_version: "schema:v1",
        tokenizer_version: "tokenizer:v1", tool_version: "tool:v1",
      },
      success_kind: "success",
    }),
    revisions: [], adjacency: [], artifacts: [],
  };
  const origin = { kind: "non_formation" as const, reason: "predicate_alignment" as const };
  return Object.freeze({
    transition,
    origin,
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: null,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
  });
};

const successRequest = (
  resultKind: "successful" | "successful_empty",
  normalizedResult: Record<string, unknown> = {
    assertions: resultKind === "successful" ? ["alias:one"] : [],
  },
): DurableMemoryWorkSuccessRequest => {
  const resultContractVersion = "predicate-result:v1";
  const normalizedResultDigest = durableMemoryWorkNormalizedResultDigest(
    resultContractVersion, normalizedResult,
  );
  const stageBody: DurableMemoryWorkResultStageBody = {
    leased_job: leased,
    result_contract_version: resultContractVersion,
    response_digest: digest("d"),
    normalized_result_digest: normalizedResultDigest,
    normalized_result: normalizedResult,
  };
  const stagedResult = materializeStagedDurableMemoryWorkResult({
    ...stageBody,
    request_digest: durableMemoryWorkResultStageRequestDigest(stageBody),
  });
  const authoritativeAppend = resultKind === "successful" ? append() : null;
  const body: DurableMemoryWorkSuccessBody = {
    leased_job: leased,
    result_kind: resultKind,
    response_digest: digest("d"),
    result_digest: authoritativeAppend?.append_attempt.request_digest ?? normalizedResultDigest,
    staged_result: stagedResult,
    authoritative_append: authoritativeAppend,
  };
  return Object.freeze({ ...body, request_digest: durableMemoryWorkSuccessRequestDigest(body) });
};

const workRow = (job: Readonly<DurableMemoryWorkJob>, stateRevision = 1) => {
  const succeeded = job.outcome?.kind === "succeeded" ? job.outcome : null;
  return {
    account_id: job.owner_account_id, job_id: job.job_id, work_version: job.version,
    accepted_work_digest: job.accepted_work_digest, account_epoch: String(job.account_epoch),
    lifecycle_state: job.lifecycle_state, deletion_epoch: job.deletion_epoch,
    work_kind: job.work_kind, input_frontier: job.input_frontier,
    input_digest: job.input_digest, execution_contract_digest: job.execution_contract_digest,
    accepted_at_event_time: job.accepted_at_event_time, max_attempts: job.max_attempts,
    state_revision: String(stateRevision), state_digest: durableMemoryWorkStateDigest(job),
    state: job.state, attempt: job.attempt, lease_fence: String(job.lease_fence),
    worker_id: job.lease?.worker_id ?? null,
    leased_at_event_time: job.lease?.leased_at_event_time ?? null,
    lease_expires_at_event_time: job.lease?.expires_at_event_time ?? null,
    result_kind: succeeded?.result_kind ?? null,
    response_digest: succeeded?.response_digest ?? null,
    result_digest: succeeded?.result_digest ?? null,
    succeeded_at_event_time: succeeded?.succeeded_at_event_time ?? null,
  };
};

const stageBundle = (request: DurableMemoryWorkSuccessRequest) => ({
  staged_result_id: request.staged_result.staged_result_id,
  staged_accepted_work_digest: request.staged_result.accepted_work_digest,
  staged_work_kind: request.staged_result.work_kind,
  staged_input_frontier: request.staged_result.input_frontier,
  staged_execution_contract_digest: request.staged_result.execution_contract_digest,
  staged_produced_attempt: request.staged_result.produced_attempt,
  staged_produced_lease_fence: String(request.staged_result.produced_lease_fence),
  staged_produced_state_digest: request.staged_result.produced_state_digest,
  staged_producer_worker_id: request.staged_result.producer_worker_id,
  staged_result_contract_version: request.staged_result.result_contract_version,
  staged_response_digest: request.staged_result.response_digest,
  staged_normalized_result_digest: request.staged_result.normalized_result_digest,
  staged_normalized_result_json: structuredClone(request.staged_result.normalized_result),
  staged_stage_request_digest: request.staged_result.stage_request_digest,
  staged_content_hash: durableMemoryWorkStagedResultContentHash(request.staged_result),
  success_terminal_state_revision: null, success_terminal_state_digest: null,
  success_work_kind: null, success_input_frontier: null, success_result_kind: null,
  success_response_digest: null, success_result_digest: null, success_origin_code: null,
  success_graph_commit_id: null, success_graph_commit_sequence: null,
  success_graph_success_kind: null, success_append_receipt_state: null,
  success_staged_result_id: null, success_staged_result_digest: null,
  success_content_hash: null, outbox_id: null, outbox_terminal_state_revision: null,
  outbox_terminal_state_digest: null, outbox_terminal_state: null,
  outbox_event_kind: null, outbox_result_digest: null,
  outbox_created_at_event_time: null, outbox_content_hash: null,
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "one" });
  readonly statements: SqlStatement[] = [];
  now = 101;
  work: Record<string, unknown> = workRow(leased);
  pendingWork: Record<string, unknown> | null = null;
  bundle: Record<string, unknown>;
  graphHead = { commit_id: null as string | null, sequence: "0" };
  receiptReserved = false;
  failStatement: string | null = null;

  constructor(readonly request: DurableMemoryWorkSuccessRequest) {
    this.bundle = stageBundle(request);
  }

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") {
      return [authorityRow(this.now) as unknown as Row];
    }
    if (statement.name === "work.success.load_locked") {
      return [structuredClone(this.work) as Row];
    }
    if (statement.name === "work.success.bundle") {
      return [structuredClone(this.bundle) as Row];
    }
    if (statement.name === "ledger.receipt_lookup") return [];
    if (statement.name === "ledger.head_lock") {
      return [structuredClone(this.graphHead) as unknown as Row];
    }
    if (statement.name === "work.success.result_insert") {
      if (this.failStatement === statement.name) throw new Error("raw provider payload");
      const value = statement.values;
      this.bundle = {
        ...this.bundle,
        success_terminal_state_revision: value[2], success_terminal_state_digest: value[3],
        success_work_kind: value[4], success_input_frontier: value[5],
        success_result_kind: value[6], success_response_digest: value[7],
        success_result_digest: value[8], success_origin_code: value[9],
        success_graph_commit_id: value[10], success_graph_commit_sequence: value[11],
        success_graph_success_kind: value[12], success_append_receipt_state: value[13],
        success_staged_result_id: value[14], success_staged_result_digest: value[15],
        success_content_hash: value[16],
      };
      return [{ inserted: true } as unknown as Row];
    }
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    if (this.failStatement === statement.name) return { rowCount: 0 };
    if (statement.name === "ledger.receipt_reserve") {
      this.receiptReserved = true;
      return { rowCount: 1 };
    }
    if (statement.name === "ledger.head_advance") {
      if (this.graphHead.commit_id !== statement.values[4]) return { rowCount: 0 };
      this.graphHead = { commit_id: String(statement.values[1]), sequence: String(statement.values[2]) };
      return { rowCount: 1 };
    }
    if (statement.name === "work.success.state_insert") {
      this.pendingWork = {
        ...this.work,
        state_revision: String(statement.values[2]), state_digest: statement.values[3],
        state: "succeeded", attempt: statement.values[4], lease_fence: String(statement.values[5]),
        worker_id: null, leased_at_event_time: null, lease_expires_at_event_time: null,
        result_kind: statement.values[6], response_digest: statement.values[7],
        result_digest: statement.values[8], succeeded_at_event_time: statement.values[9],
      };
      return { rowCount: 1 };
    }
    if (statement.name === "work.success.head_cas") {
      if (!this.pendingWork) return { rowCount: 0 };
      this.work = this.pendingWork;
      this.pendingWork = null;
      return { rowCount: 1 };
    }
    if (statement.name === "work.success.outbox_insert") {
      this.bundle = {
        ...this.bundle,
        outbox_id: statement.values[1], outbox_terminal_state_revision: statement.values[3],
        outbox_terminal_state_digest: statement.values[4], outbox_terminal_state: "succeeded",
        outbox_event_kind: "memory_work_succeeded", outbox_result_digest: statement.values[5],
        outbox_created_at_event_time: statement.values[6], outbox_content_hash: statement.values[7],
      };
      return { rowCount: 1 };
    }
    return { rowCount: 1 };
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
      work: this.connection.work, pendingWork: this.connection.pendingWork,
      bundle: this.connection.bundle, graphHead: this.connection.graphHead,
      receiptReserved: this.connection.receiptReserved,
    });
    try {
      return await callback(this.connection);
    } catch (error) {
      this.connection.work = snapshot.work;
      this.connection.pendingWork = snapshot.pendingWork;
      this.connection.bundle = snapshot.bundle;
      this.connection.graphHead = snapshot.graphHead;
      this.connection.receiptReserved = snapshot.receiptReserved;
      throw error;
    }
  }
}

describe("PostgreSQL atomic durable-work success", () => {
  test("successful-empty atomically commits terminal state, exact stage linkage, and outbox", async () => {
    const request = successRequest("successful_empty");
    const connection = new FakeConnection(request);
    const repository = createPostgresDurableMemoryWorkSuccessRepository({
      pool: new FakePool(connection),
    });
    await expect(repository.commit(context(), request)).resolves.toMatchObject({
      kind: "committed", job: { state: "succeeded" }, commit_id: null, sequence: null,
    });
    await expect(repository.commit(context(), request)).resolves.toMatchObject({
      kind: "replayed", job: { state: "succeeded" }, commit_id: null, sequence: null,
    });
    await expect(repository.commit(
      context(), successRequest("successful_empty", { assertions: ["changed"] }),
    )).resolves.toEqual({ kind: "idempotency_conflict" });
    expect(connection.statements.map((statement) => statement.name)).toEqual(expect.arrayContaining([
      "work.success.state_insert", "work.success.result_insert",
      "work.success.head_cas", "work.success.outbox_insert",
    ]));
  });

  test("graph success shares one transaction with append receipt, graph head, work head, and outbox", async () => {
    const request = successRequest("successful");
    const connection = new FakeConnection(request);
    const repository = createPostgresDurableMemoryWorkSuccessRepository({
      pool: new FakePool(connection),
    });
    await expect(repository.commit(context(), request)).resolves.toMatchObject({
      kind: "committed", commit_id: "commit:predicate:one", sequence: 1,
    });
    expect(connection.graphHead).toEqual({ commit_id: "commit:predicate:one", sequence: "1" });
    await expect(repository.commit(context(), request)).resolves.toMatchObject({
      kind: "replayed", commit_id: "commit:predicate:one", sequence: 1,
    });
  });

  test("stale parent stays distinct and rolls back graph receipt plus every success row", async () => {
    const request = successRequest("successful");
    const connection = new FakeConnection(request);
    connection.graphHead = { commit_id: "commit:other", sequence: "1" };
    const repository = createPostgresDurableMemoryWorkSuccessRepository({
      pool: new FakePool(connection),
    });
    await expect(repository.commit(context(), request)).resolves.toEqual({ kind: "stale_parent" });
    expect(connection.work["state"]).toBe("leased");
    expect(connection.bundle["success_terminal_state_revision"]).toBeNull();
    expect(connection.receiptReserved).toBe(false);
  });

  test("an injected late failure rolls back graph, work, result, and outbox without raw leakage", async () => {
    const request = successRequest("successful");
    const connection = new FakeConnection(request);
    connection.failStatement = "work.success.outbox_insert";
    const repository = createPostgresDurableMemoryWorkSuccessRepository({
      pool: new FakePool(connection),
    });
    await expect(repository.commit(context(), request)).rejects.toMatchObject({
      code: "persistence_failed", message: "persistence_failed",
    });
    expect(connection.work["state"]).toBe("leased");
    expect(connection.graphHead).toEqual({ commit_id: null, sequence: "0" });
    expect(connection.bundle["success_terminal_state_revision"]).toBeNull();
    expect(JSON.stringify(connection.statements)).not.toContain("raw provider payload");
  });

  test("expired lease and forged staged metadata fail before authoritative graph mutation", async () => {
    const request = successRequest("successful");
    const connection = new FakeConnection(request);
    connection.now = 130;
    const repository = createPostgresDurableMemoryWorkSuccessRepository({
      pool: new FakePool(connection),
    });
    await expect(repository.commit(context(), request)).resolves.toEqual({ kind: "stale_lease" });
    expect(connection.statements.map((statement) => statement.name)).not.toContain(
      "work.success.bundle",
    );
    connection.now = 101;
    connection.bundle = { ...connection.bundle, staged_content_hash: digest("f") };
    await expect(repository.commit(context(), request)).rejects.toMatchObject({
      code: "persistence_failed", message: "persistence_failed",
    });
    expect(connection.graphHead).toEqual({ commit_id: null, sequence: "0" });
  });
});
