import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import type {
  FirestoreLegacyGenerationReceiptKey,
  FirestoreStoredLegacyGenerationReceipt,
} from "../../apps/service/workers/firestore-legacy-generation-cleanup-participant";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresFirestoreLegacyGenerationReceiptRepository,
  PostgresFirestoreLegacyGenerationReceiptError,
} from "./firestore-legacy-generation-receipt-repository";

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const key: FirestoreLegacyGenerationReceiptKey = Object.freeze({
  version: "firestore-legacy-generation-receipt-key-v1",
  account_id: "account:firestore-cleanup",
  control_revision: 7,
  deletion_epoch: 3,
  operation_ref: `opref1_${"a".repeat(64)}`,
  eligibility_digest: "b".repeat(64),
  registry_digest: "c".repeat(64),
  policy_digest: "d".repeat(64),
  owner_mapping_digest: "e".repeat(64),
  project_id: "based-hardware",
  database_id: "(default)",
  role: "legacy_user_tree",
  collection_id: "users",
});
const receipt = (): FirestoreStoredLegacyGenerationReceipt => {
  const core = Object.freeze({
    ...key,
    result: "disposed" as const,
    pre_delete_count: 2,
    pre_delete_set_digest: "f".repeat(64),
    provider_receipt_digest: "1".repeat(64),
  });
  return Object.freeze({
    ...core,
    receipt_digest: sha256({
      contract_version: "firestore-legacy-generation-stored-receipt-v1",
      receipt: core,
    }),
  });
};
const row = (value = receipt()) => ({
  account_id: value.account_id,
  control_revision: String(value.control_revision),
  deletion_epoch: String(value.deletion_epoch),
  operation_ref: value.operation_ref,
  eligibility_digest: value.eligibility_digest,
  registry_digest: value.registry_digest,
  policy_digest: value.policy_digest,
  owner_mapping_digest: value.owner_mapping_digest,
  project_id: value.project_id,
  database_id: value.database_id,
  resource_role: value.role,
  collection_id: value.collection_id,
  result: value.result,
  pre_delete_count: String(value.pre_delete_count),
  pre_delete_set_digest: value.pre_delete_set_digest,
  provider_receipt_digest: value.provider_receipt_digest,
  receipt_digest: value.receipt_digest,
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "firestore-legacy-generation-receipts" });
  readonly statements: SqlStatement[] = [];
  loadRows: readonly Record<string, unknown>[] = [];
  recordRows: readonly Record<string, unknown>[] = [row()];
  failure: unknown = null;
  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (this.failure !== null
      && statement.name !== "firestore_legacy_generation_cleanup_receipt.set_role") throw this.failure;
    if (statement.name === "firestore_legacy_generation_cleanup_receipt.set_role") return [];
    if (statement.name === "firestore_legacy_generation_cleanup_receipt.load") {
      return this.loadRows as readonly Row[];
    }
    if (statement.name === "firestore_legacy_generation_cleanup_receipt.record") {
      return this.recordRows as readonly Row[];
    }
    throw new Error("unexpected statement");
  }
  async execute(): Promise<{ rowCount: number }> {
    throw new Error("receipt repository must use fixed named functions");
  }
}

class FakePool implements PostgresTransactionPool {
  readonly options: SerializableTransactionOptions[] = [];
  calls = 0;
  constructor(readonly connection: FakeConnection) {}
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    this.calls += 1;
    this.options.push(options);
    return callback(this.connection);
  }
}

describe("PostgreSQL Firestore legacy-generation receipt repository", () => {
  test("loads missing/found and records exact replay through fixed cleanup functions", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresFirestoreLegacyGenerationReceiptRepository(
      new FakePool(connection),
    );
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    connection.loadRows = [row()];
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: receipt() });
    await expect(repository.record(receipt())).resolves.toEqual(receipt());
    expect(connection.statements.map((statement) => statement.name)).toEqual([
      "firestore_legacy_generation_cleanup_receipt.set_role",
      "firestore_legacy_generation_cleanup_receipt.load",
      "firestore_legacy_generation_cleanup_receipt.set_role",
      "firestore_legacy_generation_cleanup_receipt.load",
      "firestore_legacy_generation_cleanup_receipt.set_role",
      "firestore_legacy_generation_cleanup_receipt.record",
    ]);
  });

  test("rejects role/collection substitution before I/O and persisted substitution after read", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresFirestoreLegacyGenerationReceiptRepository(pool);
    await expect(repository.load({ ...key, collection_id: "memory_items" })).rejects
      .toEqual(new PostgresFirestoreLegacyGenerationReceiptError("invalid_input"));
    expect(pool.calls).toBe(0);
    connection.loadRows = [{ ...row(), account_id: "account:other" }];
    await expect(repository.load(key)).rejects
      .toEqual(new PostgresFirestoreLegacyGenerationReceiptError("persistence_failed"));
  });

  test("maps database errors without exposing provider text or document paths", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresFirestoreLegacyGenerationReceiptRepository(
      new FakePool(connection),
    );
    connection.failure = Object.assign(new Error("private document and SQL"), { code: "23505" });
    await expect(repository.record(receipt())).rejects
      .toEqual(new PostgresFirestoreLegacyGenerationReceiptError("receipt_conflict"));
    connection.failure = new Error("private document and SQL");
    await expect(repository.load(key)).rejects
      .toEqual(new PostgresFirestoreLegacyGenerationReceiptError("persistence_failed"));
  });
});
