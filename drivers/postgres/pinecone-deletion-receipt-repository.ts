import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  PINECONE_DELETION_INDEX_NAME,
  PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE,
  type PineconeDeletionNamespace,
  type PineconeDeletionReceiptKey,
  type PineconeDeletionReceiptLoad,
  type PineconeDeletionReceiptRepository,
  type PineconeStoredDeletionReceipt,
} from "../../apps/service/workers/pinecone-deletion-cleanup-participant";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlValue,
} from "./connection";

export class PostgresPineconeDeletionReceiptError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "terminal_coordinate_denied"
    | "receipt_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresPineconeDeletionReceiptError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;

const fail = (code: PostgresPineconeDeletionReceiptError["code"]): never => {
  throw new PostgresPineconeDeletionReceiptError(code);
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

const namespaceForRole = (value: unknown): PineconeDeletionNamespace | null => {
  switch (value) {
    case "conversation_vectors": return "ns1";
    case "memory_vectors": return "ns2";
    case "screen_activity_vectors": return "ns3";
    case "action_item_vectors": return "ns4";
    case "transcript_chunk_vectors": return "ns_tchunks";
    case "x_post_vectors": return "ns_x";
    case "workstream_association_vectors": return "workstream-association-v1";
    default: return null;
  }
};

const parseKey = (value: unknown): PineconeDeletionReceiptKey => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "role", "index_name", "namespace_name",
  ]);
  const expectedNamespace = namespaceForRole(row.role);
  if (row.version !== "pinecone-deletion-receipt-key-v1"
    || !isWellFormedAccountId(row.account_id)
    || typeof row.control_revision !== "number" || !Number.isSafeInteger(row.control_revision)
    || row.control_revision < 0
    || typeof row.deletion_epoch !== "number" || !Number.isSafeInteger(row.deletion_epoch)
    || row.deletion_epoch < 0 || typeof row.operation_ref !== "string"
    || !OPERATION_REF.test(row.operation_ref) || typeof row.eligibility_digest !== "string"
    || !DIGEST.test(row.eligibility_digest) || typeof row.registry_digest !== "string"
    || !DIGEST.test(row.registry_digest) || expectedNamespace === null
    || row.index_name !== PINECONE_DELETION_INDEX_NAME
    || row.namespace_name !== expectedNamespace) fail("invalid_input");
  return Object.freeze({ ...row }) as unknown as PineconeDeletionReceiptKey;
};

const parseReceipt = (value: unknown): PineconeStoredDeletionReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "role", "index_name", "namespace_name",
    "result", "pre_delete_count", "pre_delete_content_hash", "provider_receipt_digest",
    "receipt_digest",
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
    index_name: row.index_name,
    namespace_name: row.namespace_name,
  }));
  if ((row.result !== "disposed" && row.result !== "already_absent")
    || typeof row.pre_delete_count !== "number" || !Number.isSafeInteger(row.pre_delete_count)
    || row.pre_delete_count < 0
    || row.pre_delete_count > PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE
    || (row.result === "disposed" && row.pre_delete_count === 0)
    || (row.result === "already_absent" && row.pre_delete_count !== 0)
    || typeof row.pre_delete_content_hash !== "string" || !DIGEST.test(row.pre_delete_content_hash)
    || typeof row.provider_receipt_digest !== "string" || !DIGEST.test(row.provider_receipt_digest)
    || typeof row.receipt_digest !== "string" || !DIGEST.test(row.receipt_digest)) {
    fail("invalid_input");
  }
  const core = Object.freeze({
    ...key,
    result: row.result,
    pre_delete_count: row.pre_delete_count,
    pre_delete_content_hash: row.pre_delete_content_hash,
    provider_receipt_digest: row.provider_receipt_digest,
  });
  if (sha256({ contract_version: "pinecone-deletion-stored-receipt-v1", receipt: core })
    !== row.receipt_digest) fail("invalid_input");
  return Object.freeze({ ...core, receipt_digest: row.receipt_digest }) as PineconeStoredDeletionReceipt;
};

interface ReceiptRow extends Record<string, unknown> {
  account_id: unknown;
  deletion_epoch: unknown;
  control_revision: unknown;
  operation_ref: unknown;
  eligibility_digest: unknown;
  registry_digest: unknown;
  resource_role: unknown;
  index_name: unknown;
  namespace_name: unknown;
  result: unknown;
  pre_delete_count: unknown;
  pre_delete_content_hash: unknown;
  provider_receipt_digest: unknown;
  receipt_digest: unknown;
}

const receiptFromRow = (
  row: ReceiptRow,
  expected: PineconeDeletionReceiptKey,
): PineconeStoredDeletionReceipt => {
  let receipt: PineconeStoredDeletionReceipt;
  try {
    receipt = parseReceipt(Object.freeze({
      version: "pinecone-deletion-receipt-key-v1" as const,
      account_id: row.account_id,
      control_revision: safeInteger(row.control_revision),
      deletion_epoch: safeInteger(row.deletion_epoch),
      operation_ref: row.operation_ref,
      eligibility_digest: row.eligibility_digest,
      registry_digest: row.registry_digest,
      role: row.resource_role,
      index_name: row.index_name,
      namespace_name: row.namespace_name,
      result: row.result,
      pre_delete_count: safeInteger(
        row.pre_delete_count, PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE,
      ),
      pre_delete_content_hash: row.pre_delete_content_hash,
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
    || receipt.role !== expected.role || receipt.index_name !== expected.index_name
    || receipt.namespace_name !== expected.namespace_name) fail("persistence_failed");
  return receipt;
};

const keyFromReceipt = (receipt: PineconeStoredDeletionReceipt): PineconeDeletionReceiptKey =>
  Object.freeze({
    version: receipt.version,
    account_id: receipt.account_id,
    control_revision: receipt.control_revision,
    deletion_epoch: receipt.deletion_epoch,
    operation_ref: receipt.operation_ref,
    eligibility_digest: receipt.eligibility_digest,
    registry_digest: receipt.registry_digest,
    role: receipt.role,
    index_name: receipt.index_name,
    namespace_name: receipt.namespace_name,
  });

const valuesFor = (key: PineconeDeletionReceiptKey): readonly SqlValue[] => [
  key.account_id, key.control_revision, key.deletion_epoch, key.operation_ref,
  key.eligibility_digest, key.registry_digest, key.role, key.index_name, key.namespace_name,
];

const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : null;
};

const mapFailure = (error: unknown): PostgresPineconeDeletionReceiptError => {
  if (error instanceof PostgresPineconeDeletionReceiptError) return error;
  const code = providerCode(error);
  if (code === "40001") return new PostgresPineconeDeletionReceiptError("retryable_serialization");
  if (code === "23505") return new PostgresPineconeDeletionReceiptError("receipt_conflict");
  if (code === "P0001") return new PostgresPineconeDeletionReceiptError("terminal_coordinate_denied");
  return new PostgresPineconeDeletionReceiptError("persistence_failed");
};

const setCleanupRole = (connection: CheckedOutPostgresConnection) => connection.query({
  name: "pinecone_cleanup_receipt.set_role",
  text: "SET LOCAL ROLE omi_platform_cleanup",
  values: [],
});

export const createPostgresPineconeDeletionReceiptRepository = (
  pool: PostgresTransactionPool,
): PineconeDeletionReceiptRepository => Object.freeze({
  async load(keyValue: PineconeDeletionReceiptKey): Promise<PineconeDeletionReceiptLoad> {
    const key = parseKey(keyValue);
    try {
      return await pool.withTransaction(
        // The fixed loader takes a SHARE lock on terminal deletion evidence.
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "pinecone_cleanup_receipt.load",
            text: "SELECT * FROM omi_memory.load_pinecone_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9)",
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

  async record(receiptValue: PineconeStoredDeletionReceipt): Promise<PineconeStoredDeletionReceipt> {
    const receipt = parseReceipt(receiptValue);
    const key = keyFromReceipt(receipt);
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setCleanupRole(connection);
          const rows = await connection.query<ReceiptRow>({
            name: "pinecone_cleanup_receipt.record",
            text: "SELECT * FROM omi_memory.record_pinecone_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
            values: [
              ...valuesFor(key), receipt.result, receipt.pre_delete_count,
              receipt.pre_delete_content_hash, receipt.provider_receipt_digest,
              receipt.receipt_digest,
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
