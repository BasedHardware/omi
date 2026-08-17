import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import type {
  StoredStrandedRollbackRecoveryManifest,
  StrandedRollbackRecoveryManifestKey,
  StrandedRollbackRecoveryManifestLoad,
  StrandedRollbackRecoveryManifestRepository,
} from "../../apps/service/workers/stranded-rollback-recovery-manifest-repository";
import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
  STRANDED_ROLLBACK_RECOVERY_SURFACES,
  STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION,
  isVerifiedStrandedRollbackRecoveryManifest,
  type StrandedRollbackSourceReceipt,
  type VerifiedStrandedRollbackRecoveryManifest,
} from "../../core/control/stranded-rollback-recovery";
import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";

export class PostgresStrandedRollbackRecoveryManifestError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "control_denied"
    | "manifest_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresStrandedRollbackRecoveryManifestError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const VERSION_TOKEN = /^[a-z0-9][a-z0-9._:-]{0,127}$/;
const fail = (code: PostgresStrandedRollbackRecoveryManifestError["code"]): never => {
  throw new PostgresStrandedRollbackRecoveryManifestError(code);
};
const digest = (value: unknown): value is string =>
  typeof value === "string" && DIGEST.test(value);
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const safeInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): number => {
  if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) value = Number(value);
  if (typeof value === "bigint") value = Number(value);
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0 || value > maximum) {
    fail("persistence_failed");
  }
  return value;
};

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

const parseKey = (value: unknown): StrandedRollbackRecoveryManifestKey => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "account_epoch",
    "database_generation_digest", "manifest_digest",
  ]);
  if (row.version !== "stranded-rollback-recovery-manifest-key-v1"
    || !isWellFormedAccountId(row.account_id)
    || typeof row.control_revision !== "number" || !Number.isSafeInteger(row.control_revision)
    || row.control_revision < 0 || typeof row.account_epoch !== "number"
    || !Number.isSafeInteger(row.account_epoch) || row.account_epoch < 0
    || !digest(row.database_generation_digest) || !digest(row.manifest_digest)) fail("invalid_input");
  return Object.freeze({ ...row }) as unknown as StrandedRollbackRecoveryManifestKey;
};

const surfaceReceipt = (receipt: StrandedRollbackSourceReceipt): Readonly<Record<string, unknown>> => {
  if (receipt.version !== STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION
    || receipt.manifest_contract_version !== STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION
    || !STRANDED_ROLLBACK_RECOVERY_SURFACES.includes(receipt.surface)
    || !VERSION_TOKEN.test(receipt.scanner_contract_version)
    || !digest(receipt.source_frontier_digest)
    || receipt.source_fence_state !== "held" || !digest(receipt.source_fence_receipt_digest)
    || !Number.isSafeInteger(receipt.record_count) || receipt.record_count < 0
    || receipt.record_count > 1_000_000_000 || !digest(receipt.record_set_digest)) {
    fail("invalid_input");
  }
  const core = Object.freeze({
    surface: receipt.surface,
    scanner_contract_version: receipt.scanner_contract_version,
    source_frontier_digest: receipt.source_frontier_digest,
    source_fence_receipt_digest: receipt.source_fence_receipt_digest,
    record_count: receipt.record_count,
    record_set_digest: receipt.record_set_digest,
  });
  return Object.freeze({
    ...core,
    receipt_digest: sha256({
      contract_version: "stored-stranded-rollback-source-receipt-v1",
      receipt: core,
    }),
  });
};

const normalizedManifest = (manifest: VerifiedStrandedRollbackRecoveryManifest) => {
  if (!isVerifiedStrandedRollbackRecoveryManifest(manifest)
    || manifest.source_receipts.length !== STRANDED_ROLLBACK_RECOVERY_SURFACES.length
    || manifest.rows.length !== STRANDED_ROLLBACK_RECOVERY_SURFACES.length) fail("invalid_input");
  const receipts = STRANDED_ROLLBACK_RECOVERY_SURFACES.map((surface, index) => {
    const receipt = manifest.source_receipts[index];
    const row = manifest.rows[index];
    if (receipt?.surface !== surface || row?.surface !== surface
      || receipt.record_count !== row.record_count
      || receipt.record_set_digest !== row.record_set_digest
      || receipt.account_id !== manifest.account_id
      || receipt.control_revision !== manifest.control_revision
      || receipt.account_epoch !== manifest.account_epoch
      || receipt.database_generation_digest !== manifest.database_generation_digest) fail("invalid_input");
    return surfaceReceipt(receipt);
  });
  const totalRecordCount = manifest.rows.reduce((sum, row) => sum + row.record_count, 0);
  if (!Number.isSafeInteger(totalRecordCount)) fail("invalid_input");
  const persistenceCore = Object.freeze({
    version: "stored-stranded-rollback-recovery-manifest-v1" as const,
    account_id: manifest.account_id,
    control_revision: manifest.control_revision,
    account_epoch: manifest.account_epoch,
    database_generation_digest: manifest.database_generation_digest,
    cutover_frontier_digest: manifest.cutover_frontier_digest,
    rollback_frontier_digest: manifest.rollback_frontier_digest,
    cutover_at_epoch_seconds: manifest.cutover_at_epoch_seconds,
    rolled_back_at_epoch_seconds: manifest.rolled_back_at_epoch_seconds,
    recovery_deadline_epoch_seconds: manifest.recovery_deadline_epoch_seconds,
    surface_count: STRANDED_ROLLBACK_RECOVERY_SURFACES.length,
    total_record_count: totalRecordCount,
    manifest_digest: manifest.manifest_digest,
  });
  return Object.freeze({
    stored: Object.freeze({
      ...persistenceCore,
      persistence_receipt_digest: sha256({
        contract_version: "stranded-rollback-persistence-receipt-v1",
        manifest: persistenceCore,
      }),
    }),
    receipts: Object.freeze(receipts),
  });
};

interface ManifestRow extends Record<string, unknown> {
  classification?: unknown;
  account_id: unknown;
  control_revision: unknown;
  account_epoch: unknown;
  database_generation_digest: unknown;
  cutover_frontier_digest: unknown;
  rollback_frontier_digest: unknown;
  cutover_at_epoch_seconds: unknown;
  rolled_back_at_epoch_seconds: unknown;
  recovery_deadline_epoch_seconds: unknown;
  surface_count: unknown;
  total_record_count: unknown;
  manifest_digest: unknown;
  persistence_receipt_digest: unknown;
}

const MANIFEST_ROW_KEYS = [
  "account_id", "control_revision", "account_epoch", "database_generation_digest",
  "cutover_frontier_digest", "rollback_frontier_digest", "cutover_at_epoch_seconds",
  "rolled_back_at_epoch_seconds", "recovery_deadline_epoch_seconds", "surface_count",
  "total_record_count", "manifest_digest", "persistence_receipt_digest",
] as const;

const exactProviderRow = (value: unknown, classification: boolean): ManifestRow => {
  const keys = classification ? ["classification", ...MANIFEST_ROW_KEYS] : MANIFEST_ROW_KEYS;
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("persistence_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    fail("persistence_failed");
  }
  const row: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      fail("persistence_failed");
    }
    row[key] = descriptor.value;
  }
  return row as ManifestRow;
};

const parseRow = (
  value: unknown,
  key: StrandedRollbackRecoveryManifestKey,
  classification = false,
): StoredStrandedRollbackRecoveryManifest => {
  const row = exactProviderRow(value, classification);
  const stored = Object.freeze({
    version: "stored-stranded-rollback-recovery-manifest-v1" as const,
    account_id: row.account_id,
    control_revision: safeInteger(row.control_revision),
    account_epoch: safeInteger(row.account_epoch),
    database_generation_digest: row.database_generation_digest,
    cutover_frontier_digest: row.cutover_frontier_digest,
    rollback_frontier_digest: row.rollback_frontier_digest,
    cutover_at_epoch_seconds: safeInteger(row.cutover_at_epoch_seconds),
    rolled_back_at_epoch_seconds: safeInteger(row.rolled_back_at_epoch_seconds),
    recovery_deadline_epoch_seconds: safeInteger(row.recovery_deadline_epoch_seconds),
    surface_count: safeInteger(row.surface_count, STRANDED_ROLLBACK_RECOVERY_SURFACES.length),
    total_record_count: safeInteger(row.total_record_count, 11_000_000_000),
    manifest_digest: row.manifest_digest,
    persistence_receipt_digest: row.persistence_receipt_digest,
  });
  if (stored.account_id !== key.account_id || stored.control_revision !== key.control_revision
    || stored.account_epoch !== key.account_epoch
    || stored.database_generation_digest !== key.database_generation_digest
    || stored.manifest_digest !== key.manifest_digest
    || stored.surface_count !== STRANDED_ROLLBACK_RECOVERY_SURFACES.length
    || !digest(stored.cutover_frontier_digest) || !digest(stored.rollback_frontier_digest)
    || !digest(stored.persistence_receipt_digest)) fail("persistence_failed");
  const { persistence_receipt_digest: ignored, ...core } = stored;
  void ignored;
  if (sha256({ contract_version: "stranded-rollback-persistence-receipt-v1", manifest: core })
    !== stored.persistence_receipt_digest) fail("persistence_failed");
  return stored as StoredStrandedRollbackRecoveryManifest;
};

const setRestoreRole = (connection: CheckedOutPostgresConnection) => connection.query({
  name: "stranded_rollback_recovery_manifest.set_role",
  text: "SET LOCAL ROLE omi_platform_restore",
  values: [],
});
const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : null;
};
const mapFailure = (error: unknown): PostgresStrandedRollbackRecoveryManifestError => {
  if (error instanceof PostgresStrandedRollbackRecoveryManifestError) return error;
  const code = providerCode(error);
  if (code === "40001") return new PostgresStrandedRollbackRecoveryManifestError("retryable_serialization");
  if (code === "23505") return new PostgresStrandedRollbackRecoveryManifestError("manifest_conflict");
  if (code === "P0001") return new PostgresStrandedRollbackRecoveryManifestError("control_denied");
  return new PostgresStrandedRollbackRecoveryManifestError("persistence_failed");
};

export const createPostgresStrandedRollbackRecoveryManifestRepository = (
  pool: PostgresTransactionPool,
): StrandedRollbackRecoveryManifestRepository => Object.freeze({
  async record(manifest): Promise<Readonly<{
    readonly kind: "stored" | "replayed";
    readonly manifest: StoredStrandedRollbackRecoveryManifest;
  }>> {
    const normalized = normalizedManifest(manifest);
    const key: StrandedRollbackRecoveryManifestKey = Object.freeze({
      version: "stranded-rollback-recovery-manifest-key-v1",
      account_id: normalized.stored.account_id,
      control_revision: normalized.stored.control_revision,
      account_epoch: normalized.stored.account_epoch,
      database_generation_digest: normalized.stored.database_generation_digest,
      manifest_digest: normalized.stored.manifest_digest,
    });
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setRestoreRole(connection);
          const rows = await connection.query<ManifestRow>({
            name: "stranded_rollback_recovery_manifest.record",
            text: "SELECT * FROM omi_memory.record_stranded_rollback_recovery_manifest($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)",
            values: [
              normalized.stored.account_id, normalized.stored.control_revision,
              normalized.stored.account_epoch, normalized.stored.database_generation_digest,
              normalized.stored.cutover_frontier_digest, normalized.stored.rollback_frontier_digest,
              normalized.stored.cutover_at_epoch_seconds, normalized.stored.rolled_back_at_epoch_seconds,
              normalized.stored.recovery_deadline_epoch_seconds, normalized.stored.manifest_digest,
              normalized.stored.persistence_receipt_digest, normalized.receipts,
            ],
          });
          if (rows.length !== 1) fail("persistence_failed");
          const returned = exactProviderRow(rows[0], true);
          if (returned.classification !== "stored"
            && returned.classification !== "replayed") fail("persistence_failed");
          return Object.freeze({
            kind: returned.classification,
            manifest: parseRow(returned, key, true),
          });
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
  async load(keyValue): Promise<StrandedRollbackRecoveryManifestLoad> {
    const key = parseKey(keyValue);
    try {
      return await pool.withTransaction(
        // The named loader revalidates the exact lifecycle head under FOR SHARE.
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await setRestoreRole(connection);
          const rows = await connection.query<ManifestRow>({
            name: "stranded_rollback_recovery_manifest.load",
            text: "SELECT * FROM omi_memory.load_stranded_rollback_recovery_manifest($1,$2,$3,$4,$5)",
            values: [key.account_id, key.control_revision, key.account_epoch,
              key.database_generation_digest, key.manifest_digest],
          });
          if (rows.length === 0) return Object.freeze({ kind: "missing" as const });
          if (rows.length !== 1) fail("persistence_failed");
          return Object.freeze({ kind: "found" as const, manifest: parseRow(rows[0]!, key) });
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
});
