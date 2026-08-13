import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SerializableTransactionOptions, SqlStatement } from "./connection";
import { createPostgresListenFormationOutboxRepository } from "./listen-formation-outbox";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const hash = (value: string): string => value.repeat(64);
const account = "account:alice";
const finalizationId = "listen-finalization:test";
const workId = "listen-formation-work:test";
const outboxId = `listen-outbox:${finalizationId}`;

const authorityRow = (): AuthorityStateRow => ({
  account_id: account, principal_id: "worker:listen", application_id: "app:worker",
  credential_id: "credential:worker", credential_generation: 1, capability: "memories.work.accept",
  grant_id: "grant:worker", grant_version: 1, account_epoch: 2,
  control_conflict_reason: null, control_conflict_at_revision: null,
  destination_activation_epoch: 2, destination_activation_revision: 3,
  lifecycle_state: "active", deletion_epoch: null, account_generation: "new",
  credential_lifecycle: "active", grant_lifecycle: "active", grant_enabled: true,
  authentication_strength: "service-workload", credential_expires_at_epoch_seconds: 10_000,
  control_revision: 3, control_content_hash: hash("1"), credential_content_hash: hash("2"),
  grant_content_hash: hash("3"), db_now_epoch_seconds: 100,
});

const context = (capability = "memories.work.accept") => {
  const row = authorityRow();
  return createAuthorizedLedgerWriteContextIssuer().issue({
    context_version: "authorized-ledger-write-context-v1", principal_id: row.principal_id,
    account_id: account, application_id: row.application_id, credential_id: row.credential_id,
    credential_generation: row.credential_generation, capability,
    grant_id: row.grant_id, grant_version: row.grant_version, account_epoch: 2,
    destination_activation_revision: 3, lifecycle_state: "active", deletion_epoch: null,
    authentication_strength: row.authentication_strength, issued_at_epoch_seconds: 50,
    expires_at_epoch_seconds: 500, authorization_state_digest: authorizationStateDigest(row),
  }, 100);
};

const selected = () => ({
  outbox_id: outboxId, finalization_id: finalizationId, formation_work_id: workId,
  finalization_digest: hash("a"), payload_digest: hash("b"), previous_state_revision: null,
  previous_state_digest: null, previous_state: null, previous_attempt: null,
  previous_lease_expires_at: null, db_now: "1970-01-01T00:01:40.000Z",
});

const claimed = () => ({
  result: "claimed", worker_id: "worker:listen", leased_at: "1970-01-01T00:01:40.000Z",
  lease_expires_at: "1970-01-01T00:02:10.000Z", lease_fence: "1",
});

type Rows = Record<string, readonly Record<string, unknown>[]>;
class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "listen-delivery" });
  readonly statements: SqlStatement[] = [];
  constructor(readonly rows: Rows = {}) {}
  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") return [];
    if (statement.name === "authority.lock_and_revalidate") return [authorityRow() as unknown as Row];
    if (statement.name === "listen.delivery.outcome") return [{
      result: "recorded", state_revision: "2", state_digest: statement.values[8],
    } as unknown as Row];
    return (this.rows[statement.name] ?? []) as readonly Row[];
  }
  async execute(): Promise<{ rowCount: number }> { return { rowCount: 1 }; }
}
class FakePool implements PostgresTransactionPool {
  calls = 0;
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    _options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> { this.calls += 1; return callback(this.connection); }
}

describe("PostgreSQL Listen formation outbox", () => {
  test("preflights accept capability before pool work", async () => {
    const pool = new FakePool(new FakeConnection());
    const repository = createPostgresListenFormationOutboxRepository({
      pool, lease_duration_seconds: 30, retry_delay_seconds: 10, max_attempts: 3,
    });
    await expect(repository.claimNext(context("listen.capture.write"))).resolves.toMatchObject({
      kind: "authorization_denied",
    });
    expect(pool.calls).toBe(0);
  });

  test("claims one immutable outbox row with an append-only fenced lease", async () => {
    const connection = new FakeConnection({
      "listen.delivery.select": [selected()], "listen.delivery.claim": [claimed()],
    });
    const repository = createPostgresListenFormationOutboxRepository({
      pool: new FakePool(connection), lease_duration_seconds: 30,
      retry_delay_seconds: 10, max_attempts: 3,
    });
    await expect(repository.claimNext(context())).resolves.toEqual({
      kind: "claimed", lease: {
        version: "listen-formation-outbox-lease-v1", owner_account_id: account,
        outbox_id: outboxId, finalization_id: finalizationId, formation_work_id: workId,
        finalization_digest: hash("a"), payload_digest: hash("b"), lease_fence: 1,
      },
    });
    expect(connection.statements.map((statement) => statement.name)).toEqual([
      "authority.set_local", "authority.lock_and_revalidate",
      "listen.delivery.select", "listen.delivery.claim",
    ]);
  });

  test("replays an exact accepted work digest and conflicts on changed linkage", async () => {
    const acceptedDigest = hash("c");
    const head = {
      finalization_id: finalizationId, formation_work_id: workId,
      finalization_digest: hash("a"), payload_digest: hash("b"),
      state_revision: "2", state_digest: hash("d"), state: "accepted", attempt: 1,
      lease_fence: "1", worker_id: "worker:listen", lease_expires_at: null,
      failure_code: null, failed_at: null, next_eligible_at: null,
      accepted_work_digest: acceptedDigest, accepted_at: "1970-01-01T00:01:41.000Z",
      db_now: "1970-01-01T00:01:42.000Z",
    };
    const repository = createPostgresListenFormationOutboxRepository({
      pool: new FakePool(new FakeConnection({ "listen.delivery.head": [head] })),
      lease_duration_seconds: 30, retry_delay_seconds: 10, max_attempts: 3,
    });
    const lease = { version: "listen-formation-outbox-lease-v1" as const,
      owner_account_id: account, outbox_id: outboxId, finalization_id: finalizationId,
      formation_work_id: workId, finalization_digest: hash("a"), payload_digest: hash("b"),
      lease_fence: 1 };
    await expect(repository.markAccepted(context(), lease, { accepted_work_digest: acceptedDigest }))
      .resolves.toEqual({ kind: "replayed" });
    await expect(repository.markAccepted(context(), lease, { accepted_work_digest: hash("e") }))
      .resolves.toEqual({ kind: "idempotency_conflict" });
  });

  test("records a bounded retryable failure from the exact live lease", async () => {
    const head = {
      finalization_id: finalizationId, formation_work_id: workId,
      finalization_digest: hash("a"), payload_digest: hash("b"),
      state_revision: "1", state_digest: hash("d"), state: "leased", attempt: 1,
      lease_fence: "1", worker_id: "worker:listen",
      lease_expires_at: "1970-01-01T00:02:10.000Z",
      failure_code: null, failed_at: null, next_eligible_at: null,
      accepted_work_digest: null, accepted_at: null,
      db_now: "1970-01-01T00:01:42.000Z",
    };
    const connection = new FakeConnection({ "listen.delivery.head": [head] });
    const repository = createPostgresListenFormationOutboxRepository({
      pool: new FakePool(connection), lease_duration_seconds: 30,
      retry_delay_seconds: 10, max_attempts: 3,
    });
    const lease = { version: "listen-formation-outbox-lease-v1" as const,
      owner_account_id: account, outbox_id: outboxId, finalization_id: finalizationId,
      formation_work_id: workId, finalization_digest: hash("a"), payload_digest: hash("b"),
      lease_fence: 1 };

    await expect(repository.recordFailure(context(), lease, { code: "dependency_unavailable" }))
      .resolves.toEqual({ kind: "recorded" });
    const outcome = connection.statements.find((statement) => statement.name === "listen.delivery.outcome");
    expect(outcome?.values.slice(0, 8)).toEqual([
      outboxId, 1, hash("d"), 1, "retryable_failed", "dependency_unavailable",
      "1970-01-01T00:01:52.000Z", null,
    ]);
  });
});
