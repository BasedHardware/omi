import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  FIRESTORE_LEGACY_GENERATION_COLLECTIONS,
  FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT,
  type FirestoreLegacyGenerationReceiptKey,
  type FirestoreLegacyGenerationReceiptLoad,
  type FirestoreLegacyGenerationReceiptRepository,
  type FirestoreLegacyGenerationRole,
  type FirestoreStoredLegacyGenerationReceipt,
} from "../../apps/service/workers/firestore-legacy-generation-cleanup-participant";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlValue,
} from "./connection";

export class PostgresFirestoreLegacyGenerationReceiptError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "terminal_coordinate_denied"
    | "receipt_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresFirestoreLegacyGenerationReceiptError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const PROJECT_ID = /^[a-z][a-z0-9-]{4,28}[a-z0-9]$/;
const DATABASE_ID = /^(?:\(default\)|[a-z][a-z0-9_-]{0,62})$/;
const ROLE_TO_COLLECTION = new Map<string, string>(FIRESTORE_LEGACY_GENERATION_COLLECTIONS);

const fail = (code: PostgresFirestoreLegacyGenerationReceiptError["code"]): never => {
  throw new PostgresFirestoreLegacyGenerationReceiptError(code);
};
const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_input");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== keys.length
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
  return value;
};

const parseKey = (value: unknown): FirestoreLegacyGenerationReceiptKey => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "project_id", "database_id", "role", "collection_id",
  ]);
  if (row.version !== "firestore-legacy-generation-receipt-key-v1"
    || !isWellFormedAccountId(row.account_id)
    || typeof row.control_revision !== "number" || !Number.isSafeInteger(row.control_revision)
    || row.control_revision < 0
    || typeof row.deletion_epoch !== "number" || !Number.isSafeInteger(row.deletion_epoch)
    || row.deletion_epoch < 0 || typeof row.operation_ref !== "string"
    || !OPERATION_REF.test(row.operation_ref) || !digest(row.eligibility_digest)
    || !digest(row.registry_digest) || !digest(row.policy_digest)
    || !digest(row.owner_mapping_digest) || typeof row.project_id !== "string"
    || !PROJECT_ID.test(row.project_id) || typeof row.database_id !== "string"
    || !DATABASE_ID.test(row.database_id) || typeof row.role !== "string"
    || ROLE_TO_COLLECTION.get(row.role) !== row.collection_id) fail("invalid_input");
  return Object.freeze({ ...row }) as unknown as FirestoreLegacyGenerationReceiptKey;
};

const parseReceipt = (value: unknown): FirestoreStoredLegacyGenerationReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "project_id", "database_id", "role", "collection_id", "result", "pre_delete_count",
    "pre_delete_set_digest", "provider_receipt_digest", "receipt_digest",
  ]);
  const key = parseKey(Object.freeze({
    version: row.version,
    account_id: row.account_id,
    control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch,
    operation_ref: row.operation_ref,
    eligibility_digest: row.eligibility_digest,
    registry_digest: row.registry_digest,
    policy_digest: row.policy_digest,
    owner_mapping_digest: row.owner_mapping_digest,
    project_id: row.project_id,
    database_id: row.database_id,
    role: row.role,
    collection_id: row.collection_id,
  }));
  if ((row.result !== "disposed" && row.result !== "already_absent")
    || typeof row.pre_delete_count !== "number" || !Number.isSafeInteger(row.pre_delete_count)
    || row.pre_delete_count < 0
    || row.pre_delete_count > FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT
    || (row.result === "disposed" && row.pre_delete_count === 0)
    || (row.result === "already_absent" && row.pre_delete_count !== 0)
    || !digest(row.pre_delete_set_digest) || !digest(row.provider_receipt_digest)
    || !digest(row.receipt_digest)) fail("invalid_input");
  const core = Object.freeze({
    ...key,
    result: row.result,
    pre_delete_count: row.pre_delete_count,
    pre_delete_set_digest: row.pre_delete_set_digest,
    provider_receipt_digest: row.provider_receipt_digest,
  });
  if (sha256({ contract_version: "firestore-legacy-generation-stored-receipt-v1", receipt: core })
    !== row.receipt_digest) fail("invalid_input");
  return Object.freeze({ ...core, receipt_digest: row.receipt_digest }) as
    FirestoreStoredLegacyGenerationReceipt;
};

interface ReceiptRow extends Record<string, unknown> {
  account_id: unknown;
  control_revision: unknown;
  deletion_epoch: unknown;
  operation_ref: unknown;
  eligibility_digest: unknown;
  registry_digest: unknown;
  policy_digest: unknown;
  owner_mapping_digest: unknown;
  project_id: unknown;
  database_id: unknown;
  resource_role: unknown;
  collection_id: unknown;
  result: unknown;
  pre_delete_count: unknown;
  pre_delete_set_digest: unknown;
  provider_receipt_digest: unknown;
  receipt_digest: unknown;
}

const receiptFromRow = (
  row: ReceiptRow,
  expected: FirestoreLegacyGenerationReceiptKey,
): FirestoreStoredLegacyGenerationReceipt => {
  let receipt: FirestoreStoredLegacyGenerationReceipt;
  try {
    receipt = parseReceipt(Object.freeze({
      version: "firestore-legacy-generation-receipt-key-v1",
      account_id: row.account_id,
      control_revision: safeInteger(row.control_revision),
      deletion_epoch: safeInteger(row.deletion_epoch),
      operation_ref: row.operation_ref,
      eligibility_digest: row.eligibility_digest,
      registry_digest: row.registry_digest,
      policy_digest: row.policy_digest,
      owner_mapping_digest: row.owner_mapping_digest,
      project_id: row.project_id,
      database_id: row.database_id,
      role: row.resource_role,
      collection_id: row.collection_id,
      result: row.result,
      pre_delete_count: safeInteger(
        row.pre_delete_count, FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT,
      ),
      pre_delete_set_digest: row.pre_delete_set_digest,
      provider_receipt_digest: row.provider_receipt_digest,
      receipt_digest: row.receipt_digest,
    }));
  } catch {
    return fail("persistence_failed");
  }
  for (const field of [
    "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "project_id", "database_id", "role", "collection_id",
  ] as const) if (receipt[field] !== expected[field]) fail("persistence_failed");
  return receipt;
};

const valuesFor = (key: FirestoreLegacyGenerationReceiptKey): readonly SqlValue[] => [
  key.account_id,
  key.control_revision,
  key.deletion_epoch,
  key.operation_ref,
  key.eligibility_digest,
  key.registry_digest,
  key.policy_digest,
  key.owner_mapping_digest,
  key.project_id,
  key.database_id,
  key.role,
  key.collection_id,
];
const keyFromReceipt = (
  receipt: FirestoreStoredLegacyGenerationReceipt,
): FirestoreLegacyGenerationReceiptKey => Object.freeze({
  version: receipt.version,
  account_id: receipt.account_id,
  control_revision: receipt.control_revision,
  deletion_epoch: receipt.deletion_epoch,
  operation_ref: receipt.operation_ref,
  eligibility_digest: receipt.eligibility_digest,
  registry_digest: receipt.registry_digest,
  policy_digest: receipt.policy_digest,
  owner_mapping_digest: receipt.owner_mapping_digest,
  project_id: receipt.project_id,
  database_id: receipt.database_id,
  role: receipt.role,
  collection_id: receipt.collection_id,
});
const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : null;
};
const mapFailure = (error: unknown): PostgresFirestoreLegacyGenerationReceiptError => {
  if (error instanceof PostgresFirestoreLegacyGenerationReceiptError) return error;
  const code = providerCode(error);
  if (code === "40001") return new PostgresFirestoreLegacyGenerationReceiptError("retryable_serialization");
  if (code === "23505") return new PostgresFirestoreLegacyGenerationReceiptError("receipt_conflict");
  if (code === "P0001") return new PostgresFirestoreLegacyGenerationReceiptError("terminal_coordinate_denied");
  return new PostgresFirestoreLegacyGenerationReceiptError("persistence_failed");
};
const setCleanupRole = (connection: CheckedOutPostgresConnection) => connection.query({
  name: "firestore_legacy_generation_cleanup_receipt.set_role",
  text: "SET LOCAL ROLE omi_platform_cleanup",
  values: [],
});

export const createPostgresFirestoreLegacyGenerationReceiptRepository = (
  pool: PostgresTransactionPool,
): FirestoreLegacyGenerationReceiptRepository => Object.freeze({
  async load(keyValue): Promise<FirestoreLegacyGenerationReceiptLoad> {
    const key = parseKey(keyValue);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "firestore_legacy_generation_cleanup_receipt.load",
            text: "SELECT * FROM omi_memory.load_firestore_legacy_generation_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
            values: valuesFor(key),
          });
          if (rows.length === 0) return Object.freeze({ kind: "missing" as const });
          if (rows.length !== 1) fail("persistence_failed");
          return Object.freeze({ kind: "found" as const, receipt: receiptFromRow(rows[0]!, key) });
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
  async record(receiptValue): Promise<FirestoreStoredLegacyGenerationReceipt> {
    const receipt = parseReceipt(receiptValue);
    const key = keyFromReceipt(receipt);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "firestore_legacy_generation_cleanup_receipt.record",
            text: "SELECT * FROM omi_memory.record_firestore_legacy_generation_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)",
            values: [
              ...valuesFor(key), receipt.result, receipt.pre_delete_count,
              receipt.pre_delete_set_digest, receipt.provider_receipt_digest, receipt.receipt_digest,
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
