import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import type {
  GcsDeletionReceiptKey,
  GcsStoredDeletionReceipt,
} from "../../apps/service/workers/gcs-deletion-cleanup-participant";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlStatement,
} from "./connection";
import {
  createPostgresGcsDeletionReceiptRepository,
  PostgresGcsDeletionReceiptError,
} from "./gcs-deletion-receipt-repository";

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const key: GcsDeletionReceiptKey = Object.freeze({
  version: "gcs-deletion-receipt-key-v1",
  account_id: "account:gcs-cleanup",
  control_revision: 7,
  deletion_epoch: 3,
  operation_ref: `opref1_${"a".repeat(64)}`,
  eligibility_digest: "b".repeat(64),
  registry_digest: "c".repeat(64),
  policy_digest: "d".repeat(64),
  owner_mapping_digest: "2".repeat(64),
  role: "private_sync_chunks",
  bucket_name: "omi-private-cloud-sync",
  prefix_digest: "e".repeat(64),
});
const receipt = (): GcsStoredDeletionReceipt => {
  const core = Object.freeze({
    ...key,
    result: "disposed" as const,
    pre_delete_count: 2,
    pre_delete_set_digest: "f".repeat(64),
    provider_receipt_digest: "1".repeat(64),
  });
  return Object.freeze({
    ...core,
    receipt_digest: sha256({ contract_version: "gcs-deletion-stored-receipt-v1", receipt: core }),
  });
};
const row = (value = receipt()) => ({
  account_id: value.account_id,
  deletion_epoch: String(value.deletion_epoch),
  control_revision: String(value.control_revision),
  operation_ref: value.operation_ref,
  eligibility_digest: value.eligibility_digest,
  registry_digest: value.registry_digest,
  policy_digest: value.policy_digest,
  owner_mapping_digest: value.owner_mapping_digest,
  resource_role: value.role,
  bucket_name: value.bucket_name,
  prefix_digest: value.prefix_digest,
  result: value.result,
  pre_delete_count: String(value.pre_delete_count),
  pre_delete_set_digest: value.pre_delete_set_digest,
  provider_receipt_digest: value.provider_receipt_digest,
  receipt_digest: value.receipt_digest,
  recorded_at: new Date(),
});

class FakeConnection implements CheckedOutPostgresConnection {
  readonly connectionIdentity = Object.freeze({ client: "gcs-receipts" });
  readonly statements: SqlStatement[] = [];
  loadRows: readonly Record<string, unknown>[] = [];
  recordRows: readonly Record<string, unknown>[] = [row()];
  failure: unknown = null;

  async query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]> {
    this.statements.push(statement);
    if (this.failure !== null && statement.name !== "gcs_cleanup_receipt.set_role") throw this.failure;
    if (statement.name === "gcs_cleanup_receipt.set_role") return [];
    if (statement.name === "gcs_cleanup_receipt.load") return this.loadRows as readonly Row[];
    if (statement.name === "gcs_cleanup_receipt.record") return this.recordRows as readonly Row[];
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

describe("PostgreSQL GCS deletion receipt repository", () => {
  test("loads missing/found receipts and records exact replay through fixed cleanup operations", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresGcsDeletionReceiptRepository(pool);
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    connection.loadRows = [row()];
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: receipt() });
    await expect(repository.record(receipt())).resolves.toEqual(receipt());
    expect(pool.options).toEqual([
      { isolationLevel: "serializable", accessMode: "read write" },
      { isolationLevel: "serializable", accessMode: "read write" },
      { isolationLevel: "serializable", accessMode: "read write" },
    ]);
    expect(connection.statements.map((statement) => statement.name)).toEqual([
      "gcs_cleanup_receipt.set_role", "gcs_cleanup_receipt.load",
      "gcs_cleanup_receipt.set_role", "gcs_cleanup_receipt.load",
      "gcs_cleanup_receipt.set_role", "gcs_cleanup_receipt.record",
    ]);
    expect(connection.statements.at(-1)?.values).toEqual([
      key.account_id, key.control_revision, key.deletion_epoch, key.operation_ref,
      key.eligibility_digest, key.registry_digest, key.policy_digest, key.owner_mapping_digest, key.role,
      key.bucket_name, key.prefix_digest, "disposed", 2, "f".repeat(64),
      "1".repeat(64), receipt().receipt_digest,
    ]);
  });

  test("rejects invalid bucket coordinates and persisted substitution before trust", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresGcsDeletionReceiptRepository(pool);
    await expect(repository.load({ ...key, bucket_name: "UPPERCASE" })).rejects
      .toEqual(new PostgresGcsDeletionReceiptError("invalid_input"));
    expect(pool.calls).toBe(0);
    connection.loadRows = [{ ...row(), account_id: "account:other" }];
    await expect(repository.load(key)).rejects
      .toEqual(new PostgresGcsDeletionReceiptError("persistence_failed"));
  });

  test("maps database failures without exposing object paths, SQL, or provider text", async () => {
    const connection = new FakeConnection();
    const repository = createPostgresGcsDeletionReceiptRepository(new FakePool(connection));
    connection.failure = Object.assign(new Error("private object path and SQL"), { code: "23505" });
    await expect(repository.record(receipt())).rejects
      .toEqual(new PostgresGcsDeletionReceiptError("receipt_conflict"));
    connection.failure = new Error("private object path and SQL");
    await expect(repository.load(key)).rejects
      .toEqual(new PostgresGcsDeletionReceiptError("persistence_failed"));
  });

  test("rejects digest-valid but semantically impossible receipts before database I/O", async () => {
    const connection = new FakeConnection();
    const pool = new FakePool(connection);
    const repository = createPostgresGcsDeletionReceiptRepository(pool);
    const core = Object.freeze({
      ...key,
      result: "already_absent" as const,
      pre_delete_count: 1,
      pre_delete_set_digest: "f".repeat(64),
      provider_receipt_digest: "1".repeat(64),
    });
    const invalid = Object.freeze({
      ...core,
      receipt_digest: sha256({ contract_version: "gcs-deletion-stored-receipt-v1", receipt: core }),
    });
    await expect(repository.record(invalid)).rejects
      .toEqual(new PostgresGcsDeletionReceiptError("invalid_input"));
    expect(pool.calls).toBe(0);
  });
});
