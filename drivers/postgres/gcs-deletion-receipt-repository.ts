import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  GCS_DELETION_MAX_OBJECTS_PER_ROLE,
  type GcsDeletionReceiptKey,
  type GcsDeletionReceiptLoad,
  type GcsDeletionReceiptRepository,
  type GcsDeletionRole,
  type GcsStoredDeletionReceipt,
} from "../../apps/service/workers/gcs-deletion-cleanup-participant";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlValue,
} from "./connection";

export class PostgresGcsDeletionReceiptError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "terminal_coordinate_denied"
    | "receipt_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresGcsDeletionReceiptError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const ROLES = Object.freeze([
  "speech_profiles", "conversation_recordings", "private_sync_chunks",
  "private_sync_audio", "private_sync_merged", "private_sync_playback",
  "temporal_sync", "chat_files",
] as const);

const fail = (code: PostgresGcsDeletionReceiptError["code"]): never => {
  throw new PostgresGcsDeletionReceiptError(code);
};
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);
const role = (value: unknown): value is GcsDeletionRole =>
  typeof value === "string" && (ROLES as readonly string[]).includes(value);
const bucketName = (value: unknown): value is string => {
  if (typeof value !== "string" || value.length < 3 || value.length > 222
    || !/^[a-z0-9][a-z0-9._-]*[a-z0-9]$/.test(value)) return false;
  return value.split(".").every((part) => part.length <= 63
    && /^[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?$/.test(part));
};

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

const parseKey = (value: unknown): GcsDeletionReceiptKey => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "role", "bucket_name", "prefix_digest",
  ]);
  if (row.version !== "gcs-deletion-receipt-key-v1"
    || !isWellFormedAccountId(row.account_id)
    || typeof row.control_revision !== "number" || !Number.isSafeInteger(row.control_revision)
    || row.control_revision < 0
    || typeof row.deletion_epoch !== "number" || !Number.isSafeInteger(row.deletion_epoch)
    || row.deletion_epoch < 0 || typeof row.operation_ref !== "string"
    || !OPERATION_REF.test(row.operation_ref) || !digest(row.eligibility_digest)
    || !digest(row.registry_digest) || !digest(row.policy_digest)
    || !digest(row.owner_mapping_digest) || !role(row.role)
    || !bucketName(row.bucket_name)
    || !digest(row.prefix_digest)) fail("invalid_input");
  return Object.freeze({ ...row }) as unknown as GcsDeletionReceiptKey;
};

const parseReceipt = (value: unknown): GcsStoredDeletionReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "role", "bucket_name", "prefix_digest", "result", "pre_delete_count", "pre_delete_set_digest",
    "provider_receipt_digest", "receipt_digest",
  ]);
  const key = parseKey(Object.freeze({
    version: row.version, account_id: row.account_id, control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch, operation_ref: row.operation_ref,
    eligibility_digest: row.eligibility_digest, registry_digest: row.registry_digest,
    policy_digest: row.policy_digest, owner_mapping_digest: row.owner_mapping_digest,
    role: row.role, bucket_name: row.bucket_name,
    prefix_digest: row.prefix_digest,
  }));
  if ((row.result !== "disposed" && row.result !== "already_absent")
    || typeof row.pre_delete_count !== "number" || !Number.isSafeInteger(row.pre_delete_count)
    || row.pre_delete_count < 0 || row.pre_delete_count > GCS_DELETION_MAX_OBJECTS_PER_ROLE
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
  if (sha256({ contract_version: "gcs-deletion-stored-receipt-v1", receipt: core })
    !== row.receipt_digest) fail("invalid_input");
  return Object.freeze({ ...core, receipt_digest: row.receipt_digest }) as GcsStoredDeletionReceipt;
};

interface ReceiptRow extends Record<string, unknown> {
  account_id: unknown;
  deletion_epoch: unknown;
  control_revision: unknown;
  operation_ref: unknown;
  eligibility_digest: unknown;
  registry_digest: unknown;
  policy_digest: unknown;
  owner_mapping_digest: unknown;
  resource_role: unknown;
  bucket_name: unknown;
  prefix_digest: unknown;
  result: unknown;
  pre_delete_count: unknown;
  pre_delete_set_digest: unknown;
  provider_receipt_digest: unknown;
  receipt_digest: unknown;
}

const receiptFromRow = (row: ReceiptRow, expected: GcsDeletionReceiptKey): GcsStoredDeletionReceipt => {
  let receipt: GcsStoredDeletionReceipt;
  try {
    receipt = parseReceipt(Object.freeze({
      version: "gcs-deletion-receipt-key-v1" as const,
      account_id: row.account_id,
      control_revision: safeInteger(row.control_revision),
      deletion_epoch: safeInteger(row.deletion_epoch),
      operation_ref: row.operation_ref,
      eligibility_digest: row.eligibility_digest,
      registry_digest: row.registry_digest,
      policy_digest: row.policy_digest,
      owner_mapping_digest: row.owner_mapping_digest,
      role: row.resource_role,
      bucket_name: row.bucket_name,
      prefix_digest: row.prefix_digest,
      result: row.result,
      pre_delete_count: safeInteger(row.pre_delete_count, GCS_DELETION_MAX_OBJECTS_PER_ROLE),
      pre_delete_set_digest: row.pre_delete_set_digest,
      provider_receipt_digest: row.provider_receipt_digest,
      receipt_digest: row.receipt_digest,
    }));
  } catch {
    return fail("persistence_failed");
  }
  for (const field of [
    "account_id", "control_revision", "deletion_epoch", "operation_ref", "eligibility_digest",
    "registry_digest", "policy_digest", "owner_mapping_digest", "role", "bucket_name", "prefix_digest",
  ] as const) if (receipt[field] !== expected[field]) fail("persistence_failed");
  return receipt;
};

const keyFromReceipt = (receipt: GcsStoredDeletionReceipt): GcsDeletionReceiptKey => Object.freeze({
  version: receipt.version,
  account_id: receipt.account_id,
  control_revision: receipt.control_revision,
  deletion_epoch: receipt.deletion_epoch,
  operation_ref: receipt.operation_ref,
  eligibility_digest: receipt.eligibility_digest,
  registry_digest: receipt.registry_digest,
  policy_digest: receipt.policy_digest,
  owner_mapping_digest: receipt.owner_mapping_digest,
  role: receipt.role,
  bucket_name: receipt.bucket_name,
  prefix_digest: receipt.prefix_digest,
});

const valuesFor = (key: GcsDeletionReceiptKey): readonly SqlValue[] => [
  key.account_id, key.control_revision, key.deletion_epoch, key.operation_ref,
  key.eligibility_digest, key.registry_digest, key.policy_digest, key.owner_mapping_digest, key.role,
  key.bucket_name, key.prefix_digest,
];
const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : null;
};
const mapFailure = (error: unknown): PostgresGcsDeletionReceiptError => {
  if (error instanceof PostgresGcsDeletionReceiptError) return error;
  const code = providerCode(error);
  if (code === "40001") return new PostgresGcsDeletionReceiptError("retryable_serialization");
  if (code === "23505") return new PostgresGcsDeletionReceiptError("receipt_conflict");
  if (code === "P0001") return new PostgresGcsDeletionReceiptError("terminal_coordinate_denied");
  return new PostgresGcsDeletionReceiptError("persistence_failed");
};
const setCleanupRole = (connection: CheckedOutPostgresConnection) => connection.query({
  name: "gcs_cleanup_receipt.set_role",
  text: "SET LOCAL ROLE omi_platform_cleanup",
  values: [],
});

export const createPostgresGcsDeletionReceiptRepository = (
  pool: PostgresTransactionPool,
): GcsDeletionReceiptRepository => Object.freeze({
  async load(keyValue: GcsDeletionReceiptKey): Promise<GcsDeletionReceiptLoad> {
    const key = parseKey(keyValue);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "gcs_cleanup_receipt.load",
            text: "SELECT * FROM omi_memory.load_gcs_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
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

  async record(receiptValue: GcsStoredDeletionReceipt): Promise<GcsStoredDeletionReceipt> {
    const receipt = parseReceipt(receiptValue);
    const key = keyFromReceipt(receipt);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "gcs_cleanup_receipt.record",
            text: "SELECT * FROM omi_memory.record_gcs_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)",
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
