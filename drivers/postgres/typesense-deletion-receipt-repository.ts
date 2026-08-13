import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION,
  type TypesenseDeletionCollectionRole,
  type TypesenseDeletionReceiptKey,
  type TypesenseDeletionReceiptLoad,
  type TypesenseDeletionReceiptRepository,
  type TypesenseStoredDeletionReceipt,
} from "../../apps/service/workers/typesense-deletion-cleanup-participant";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlValue,
} from "./connection";

export class PostgresTypesenseDeletionReceiptError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "terminal_coordinate_denied"
    | "receipt_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresTypesenseDeletionReceiptError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const COLLECTION = /^[A-Za-z0-9_-]{1,128}$/;

const fail = (code: PostgresTypesenseDeletionReceiptError["code"]): never => {
  throw new PostgresTypesenseDeletionReceiptError(code);
};

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_input");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    fail("invalid_input");
  }
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("invalid_input");
    result[key] = descriptor.value;
  }
  return result;
};

const safeInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): number => {
  if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) value = Number(value);
  if (typeof value === "bigint") value = Number(value);
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0 || value > maximum) {
    fail("persistence_failed");
  }
  return value as number;
};

const role = (value: unknown): value is TypesenseDeletionCollectionRole =>
  value === "legacy_conversations" || value === "canonical_memory_atoms";

const parseKey = (value: unknown): TypesenseDeletionReceiptKey => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "role", "collection_name",
  ]);
  if (row.version !== "typesense-deletion-receipt-key-v1"
    || !isWellFormedAccountId(row.account_id)
    || typeof row.control_revision !== "number" || !Number.isSafeInteger(row.control_revision)
    || row.control_revision < 0
    || typeof row.deletion_epoch !== "number" || !Number.isSafeInteger(row.deletion_epoch)
    || row.deletion_epoch < 0 || typeof row.operation_ref !== "string"
    || !OPERATION_REF.test(row.operation_ref) || typeof row.eligibility_digest !== "string"
    || !DIGEST.test(row.eligibility_digest) || typeof row.registry_digest !== "string"
    || !DIGEST.test(row.registry_digest) || !role(row.role)
    || typeof row.collection_name !== "string" || !COLLECTION.test(row.collection_name)) {
    fail("invalid_input");
  }
  return Object.freeze({ ...row }) as unknown as TypesenseDeletionReceiptKey;
};

const parseReceipt = (value: unknown): TypesenseStoredDeletionReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "role", "collection_name", "result",
    "affected_count", "provider_receipt_digest", "receipt_digest",
  ]);
  const key = parseKey(Object.freeze({
    version: row.version,
    account_id: row.account_id,
    control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch,
    operation_ref: row.operation_ref,
    eligibility_digest: row.eligibility_digest,
    registry_digest: row.registry_digest,
    role: row.role,
    collection_name: row.collection_name,
  }));
  if ((row.result !== "disposed" && row.result !== "already_absent")
    || typeof row.affected_count !== "number" || !Number.isSafeInteger(row.affected_count)
    || row.affected_count < 0
    || row.affected_count > TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION
    || (row.result === "disposed" && row.affected_count === 0)
    || (row.result === "already_absent" && row.affected_count !== 0)
    || typeof row.provider_receipt_digest !== "string" || !DIGEST.test(row.provider_receipt_digest)
    || typeof row.receipt_digest !== "string" || !DIGEST.test(row.receipt_digest)) {
    fail("invalid_input");
  }
  const core = Object.freeze({
    ...key,
    result: row.result,
    affected_count: row.affected_count,
    provider_receipt_digest: row.provider_receipt_digest,
  });
  if (sha256({ contract_version: "typesense-deletion-stored-receipt-v1", receipt: core })
    !== row.receipt_digest) fail("invalid_input");
  return Object.freeze({ ...core, receipt_digest: row.receipt_digest }) as TypesenseStoredDeletionReceipt;
};

interface ReceiptRow extends Record<string, unknown> {
  account_id: unknown;
  deletion_epoch: unknown;
  control_revision: unknown;
  operation_ref: unknown;
  eligibility_digest: unknown;
  registry_digest: unknown;
  resource_role: unknown;
  collection_name: unknown;
  result: unknown;
  affected_count: unknown;
  provider_receipt_digest: unknown;
  receipt_digest: unknown;
}

const receiptFromRow = (
  row: ReceiptRow,
  expected: TypesenseDeletionReceiptKey,
): TypesenseStoredDeletionReceipt => {
  let receipt: TypesenseStoredDeletionReceipt;
  try {
    receipt = parseReceipt(Object.freeze({
      version: "typesense-deletion-receipt-key-v1" as const,
      account_id: row.account_id,
      control_revision: safeInteger(row.control_revision),
      deletion_epoch: safeInteger(row.deletion_epoch),
      operation_ref: row.operation_ref,
      eligibility_digest: row.eligibility_digest,
      registry_digest: row.registry_digest,
      role: row.resource_role,
      collection_name: row.collection_name,
      result: row.result,
      affected_count: safeInteger(
        row.affected_count, TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION,
      ),
      provider_receipt_digest: row.provider_receipt_digest,
      receipt_digest: row.receipt_digest,
    }));
  } catch {
    return fail("persistence_failed");
  }
  if (receipt.account_id !== expected.account_id
    || receipt.control_revision !== expected.control_revision
    || receipt.deletion_epoch !== expected.deletion_epoch
    || receipt.operation_ref !== expected.operation_ref
    || receipt.eligibility_digest !== expected.eligibility_digest
    || receipt.registry_digest !== expected.registry_digest
    || receipt.role !== expected.role
    || receipt.collection_name !== expected.collection_name) fail("persistence_failed");
  return receipt;
};

const keyFromReceipt = (receipt: TypesenseStoredDeletionReceipt): TypesenseDeletionReceiptKey =>
  Object.freeze({
    version: receipt.version,
    account_id: receipt.account_id,
    control_revision: receipt.control_revision,
    deletion_epoch: receipt.deletion_epoch,
    operation_ref: receipt.operation_ref,
    eligibility_digest: receipt.eligibility_digest,
    registry_digest: receipt.registry_digest,
    role: receipt.role,
    collection_name: receipt.collection_name,
  });

const valuesFor = (key: TypesenseDeletionReceiptKey): readonly SqlValue[] => [
  key.account_id, key.control_revision, key.deletion_epoch, key.operation_ref,
  key.eligibility_digest, key.registry_digest, key.role, key.collection_name,
];

const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const descriptors = Object.getOwnPropertyDescriptors(error);
  const code = descriptors.code;
  return code && "value" in code && typeof code.value === "string" ? code.value : null;
};

const mapFailure = (error: unknown): PostgresTypesenseDeletionReceiptError => {
  if (error instanceof PostgresTypesenseDeletionReceiptError) return error;
  const code = providerCode(error);
  if (code === "40001") return new PostgresTypesenseDeletionReceiptError("retryable_serialization");
  if (code === "23505") return new PostgresTypesenseDeletionReceiptError("receipt_conflict");
  if (code === "P0001") return new PostgresTypesenseDeletionReceiptError("terminal_coordinate_denied");
  return new PostgresTypesenseDeletionReceiptError("persistence_failed");
};

const setCleanupRole = (connection: CheckedOutPostgresConnection) => connection.query({
  name: "typesense_cleanup_receipt.set_role",
  text: "SET LOCAL ROLE omi_platform_cleanup",
  values: [],
});

export const createPostgresTypesenseDeletionReceiptRepository = (
  pool: PostgresTransactionPool,
): TypesenseDeletionReceiptRepository => Object.freeze({
  async load(keyValue: TypesenseDeletionReceiptKey): Promise<TypesenseDeletionReceiptLoad> {
    const key = parseKey(keyValue);
    try {
      return await pool.withTransaction(
        // The fixed loader takes a SHARE lock on the terminal export coordinate so
        // the observation cannot race deletion-safety state. PostgreSQL rejects
        // row-locking SELECTs inside a READ ONLY transaction.
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "typesense_cleanup_receipt.load",
            text: "SELECT * FROM omi_memory.load_typesense_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8)",
            values: valuesFor(key),
          });
          if (rows.length === 0) return Object.freeze({ kind: "missing" as const });
          if (rows.length !== 1) fail("persistence_failed");
          const receipt = receiptFromRow(rows[0]!, key);
          return Object.freeze({ kind: "found" as const, receipt });
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },

  async record(
    receiptValue: TypesenseStoredDeletionReceipt,
  ): Promise<TypesenseStoredDeletionReceipt> {
    const receipt = parseReceipt(receiptValue);
    const key = keyFromReceipt(receipt);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "typesense_cleanup_receipt.record",
            text: "SELECT * FROM omi_memory.record_typesense_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
            values: [
              ...valuesFor(key), receipt.result, receipt.affected_count,
              receipt.provider_receipt_digest, receipt.receipt_digest,
            ],
          });
          if (rows.length !== 1) fail("persistence_failed");
          return receiptFromRow(rows[0]!, key);
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
});
