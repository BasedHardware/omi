import { expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import { createOperationalTelemetryEmitter } from "../../core/observability/operational-telemetry";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  authorizationStateDigest,
  mapPostgresFailure,
  PostgresRepositoryError,
  withAuthorizedSerializableTransaction,
  type AuthorityStateRow,
} from "./transaction";

const authorityRow = (overrides: Partial<AuthorityStateRow> = {}): AuthorityStateRow => ({
  account_id: "account:alice",
  principal_id: "principal:alice",
  application_id: "app:desktop",
  credential_id: "credential:one",
  credential_generation: 4,
  capability: "memories.write",
  grant_id: "grant:one",
  grant_version: 9,
  account_epoch: 12,
  control_conflict_reason: null,
  control_conflict_at_revision: null,
  destination_activation_epoch: 12,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  account_generation: "new",
  credential_lifecycle: "active",
  grant_lifecycle: "active",
  grant_enabled: true,
  authentication_strength: "firebase-id-token",
  credential_expires_at_epoch_seconds: 300,
  control_revision: 17,
  control_content_hash: "1".repeat(64),
  credential_content_hash: "2".repeat(64),
  grant_content_hash: "3".repeat(64),
  db_now_epoch_seconds: 150,
  ...overrides,
});

const context = (row = authorityRow()) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "principal:alice",
  account_id: "account:alice",
  application_id: "app:desktop",
  credential_id: "credential:one",
  credential_generation: 4,
  capability: "memories.write",
  grant_id: "grant:one",
  grant_version: 9,
  account_epoch: 12,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "firebase-id-token",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: authorizationStateDigest(row),
}, 150);

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "only-client" });
  readonly statements: SqlStatement[] = [];
  localAccount: string | null = null;

  constructor(readonly row: AuthorityStateRow) {}

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (statement.name === "authority.set_local") {
      this.localAccount = statement.values[0] as string;
      return [];
    }
    if (statement.name === "authority.lock_and_revalidate") return [this.row as unknown as Row];
    return [];
  }

  async execute(statement: SqlStatement): Promise<{ rowCount: number }> {
    this.statements.push(statement);
    return { rowCount: 1 };
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  transactionCount = 0;

  constructor(readonly connection: FakeConnection) {}

  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.options.push(options);
    this.transactionCount += 1;
    try {
      return await callback(this.connection);
    } finally {
      // SET LOCAL-equivalent: the pool adapter must leave no tenant state when
      // success, rollback, or a callback failure returns the client.
      this.connection.localAccount = null;
    }
  }
}

test("exposes only frozen revalidated metadata from one checked-out serializable connection", async () => {
  const row = authorityRow();
  const connection = new FakeConnection(row);
  const pool = new FakePool(connection);
  const result = await withAuthorizedSerializableTransaction(pool, context(row), async (transaction) => {
    expect(transaction.authority).toEqual(context(row));
    expect(transaction.dbNowEpochSeconds).toBe(150);
    expect(Object.isFrozen(transaction)).toBe(true);
    expect("connectionIdentity" in transaction).toBe(false);
    expect("query" in transaction).toBe(false);
    expect("execute" in transaction).toBe(false);
    expect(connection.localAccount).toBe("account:alice");
    return "done";
  });

  expect(result).toBe("done");
  expect(pool.options).toEqual([{ isolationLevel: "serializable", accessMode: "read write" }]);
  expect(connection.statements.map((item) => item.name)).toEqual([
    "authority.set_local",
    "authority.lock_and_revalidate",
  ]);
  expect(connection.statements[0]?.values).toEqual([
    "account:alice", "principal:alice", "grant:one", 12, "active", "memories.write",
  ]);
  expect(connection.statements[1]?.values).toEqual([
    "account:alice", "principal:alice", "app:desktop", "credential:one", 4, "memories.write", "grant:one",
  ]);
  expect(connection.statements[1]?.text).toContain("omi_memory.lock_authority_state($1, $2, $3, $4, $5, $6, $7)");
  expect(connection.localAccount).toBeNull();
});

test("classifies stale context and authorization rows before repository work", async () => {
  for (const [changed, expectedCode] of [
    [authorityRow({ account_epoch: 13 }), "stale_epoch"],
    [authorityRow({ principal_id: "principal:bob" }), "credential_inactive"],
    [authorityRow({ control_conflict_reason: "legacy_and_destination_disagree", control_conflict_at_revision: 17 }), "authorization_state_denied"],
    [authorityRow({ destination_activation_epoch: 13 }), "destination_inactive"],
    [authorityRow({ destination_activation_revision: null }), "destination_inactive"],
    [authorityRow({ lifecycle_state: "deletion_pending", deletion_epoch: 1 }), "lifecycle_inactive"],
    [authorityRow({ credential_lifecycle: "revoked" }), "credential_inactive"],
    [authorityRow({ grant_enabled: false }), "grant_inactive"],
    [authorityRow({ capability: "memories.read" }), "capability_denied"],
    [authorityRow({ control_content_hash: "4".repeat(64) }), "authorization_state_denied"],
    [authorityRow({ db_now_epoch_seconds: 200 }), "expired_context"],
  ] as const) {
    const base = authorityRow();
    let callbackCalls = 0;
    await expect(withAuthorizedSerializableTransaction(
      new FakePool(new FakeConnection(changed)),
      context(base),
      async () => { callbackCalls += 1; },
    )).rejects.toMatchObject({ code: expectedCode, message: expectedCode });
    expect(callbackCalls).toBe(0);
  }
});

test("transaction-local context is cleared when the callback fails", async () => {
  const row = authorityRow();
  const connection = new FakeConnection(row);
  const pool = new FakePool(connection);
  await expect(withAuthorizedSerializableTransaction(pool, context(row), async () => {
    throw new Error("raw private payload must not escape");
  })).rejects.toEqual(new PostgresRepositoryError("persistence_failed"));
  expect(connection.localAccount).toBeNull();
});

test("maps SQLSTATE 40001 exactly and keeps provider contents out of adapter errors", () => {
  const serialization = mapPostgresFailure({ code: "40001", message: "contains SQL and private values" });
  expect(serialization).toEqual(new PostgresRepositoryError("retryable_serialization", true));
  expect(serialization.message).not.toContain("private");
  const unknown = mapPostgresFailure(new Error("secret row and SQL text"));
  expect(unknown).toEqual(new PostgresRepositoryError("persistence_failed"));
  expect(unknown.message).toBe("persistence_failed");
});

test("emits one content-safe transaction outcome after durable success", async () => {
  const row = authorityRow();
  const events: unknown[] = [];
  const times = [1_000, 1_025];
  const result = await withAuthorizedSerializableTransaction(
    new FakePool(new FakeConnection(row)),
    context(row),
    async () => "committed",
    {
      telemetry: createOperationalTelemetryEmitter((event) => events.push(event)),
      nowMilliseconds: () => times.shift() ?? 1_025,
    },
  );

  expect(result).toBe("committed");
  expect(events).toEqual([{
    version: "operational-telemetry-v1",
    family: "database",
    stage: "transaction",
    outcome: "success",
    duration_ms: 25,
    pool: null,
  }]);
  expect(JSON.stringify(events)).not.toContain("alice");
  expect(JSON.stringify(events)).not.toContain("principal");
});

test("classifies serialization and stale authority at the transaction boundary", async () => {
  const events: unknown[] = [];
  const telemetry = createOperationalTelemetryEmitter((event) => events.push(event));
  class FailingPool implements PostgresTransactionPool {
    async withTransaction<Result>(): Promise<Result> {
      throw { code: "40001", message: "private provider body" };
    }
  }
  await expect(withAuthorizedSerializableTransaction(
    new FailingPool(),
    context(),
    async () => "never",
    { telemetry, nowMilliseconds: () => 10 },
  )).rejects.toEqual(new PostgresRepositoryError("retryable_serialization", true));

  const stale = authorityRow({ account_epoch: 13 });
  await expect(withAuthorizedSerializableTransaction(
    new FakePool(new FakeConnection(stale)),
    context(),
    async () => "never",
    { telemetry, nowMilliseconds: () => 10 },
  )).rejects.toEqual(new PostgresRepositoryError("stale_epoch"));

  expect(events).toEqual([
    expect.objectContaining({ family: "database", outcome: "serialization_retryable" }),
    expect.objectContaining({ family: "database", outcome: "stale_authority" }),
  ]);
  expect(JSON.stringify(events)).not.toContain("private provider body");
});

test("telemetry and clock failures cannot alter transaction results or errors", async () => {
  const row = authorityRow();
  let callbackCalls = 0;
  const throwingTelemetry = createOperationalTelemetryEmitter(() => {
    throw new Error("telemetry unavailable");
  });
  const observability = {
    telemetry: throwingTelemetry,
    nowMilliseconds: () => { throw new Error("clock unavailable"); },
  };

  await expect(withAuthorizedSerializableTransaction(
    new FakePool(new FakeConnection(row)),
    context(row),
    async () => { callbackCalls += 1; return "same-result"; },
    observability,
  )).resolves.toBe("same-result");
  expect(callbackCalls).toBe(1);

  await expect(withAuthorizedSerializableTransaction(
    new FakePool(new FakeConnection(row)),
    context(row),
    async () => { throw new Error("private callback failure"); },
    observability,
  )).rejects.toEqual(new PostgresRepositoryError("persistence_failed"));
  expect(callbackCalls).toBe(1);
});
