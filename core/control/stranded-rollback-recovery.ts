import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  isWellFormedAccountId,
  type AccountControlProjection,
} from "./account-control";
import { DELETION_CLEANUP_SURFACES } from "./deletion-cleanup-inventory";

export const STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION =
  "stranded-rollback-recovery-v1" as const;
export const STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION =
  "stranded-rollback-source-receipt-v1" as const;
export const STRANDED_ROLLBACK_COORDINATE_VERSION =
  "stranded-rollback-coordinate-v1" as const;
export const STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS = 30 * 24 * 60 * 60;

/**
 * ADR-014 defines stranded data as the already-enumerated destination data,
 * not a second physical store. The legacy generation is the one excluded
 * surface because rollback resumes it as product authority.
 */
export const STRANDED_ROLLBACK_RECOVERY_SURFACES = Object.freeze(
  DELETION_CLEANUP_SURFACES.filter((surface) => surface !== "legacy_generation_data"),
);
export type StrandedRollbackRecoverySurface =
  typeof STRANDED_ROLLBACK_RECOVERY_SURFACES[number];

export interface StrandedRollbackCoordinate {
  readonly version: typeof STRANDED_ROLLBACK_COORDINATE_VERSION;
  readonly account_id: string;
  readonly control_revision: number;
  readonly account_epoch: number;
  readonly database_generation_digest: string;
  readonly cutover_frontier_digest: string;
  readonly rollback_frontier_digest: string;
  readonly cutover_at_epoch_seconds: number;
  readonly rolled_back_at_epoch_seconds: number;
  readonly recovery_deadline_epoch_seconds: number;
}

export interface StrandedRollbackSourceReceipt {
  readonly version: typeof STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION;
  readonly manifest_contract_version: typeof STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION;
  readonly scanner_contract_version: string;
  readonly account_id: string;
  readonly control_revision: number;
  readonly account_epoch: number;
  readonly database_generation_digest: string;
  readonly surface: StrandedRollbackRecoverySurface;
  readonly source_frontier_digest: string;
  readonly source_fence_state: "held" | "released";
  readonly source_fence_receipt_digest: string;
  readonly record_count: number;
  readonly record_set_digest: string;
}

export interface StrandedRollbackRecoveryInput {
  readonly control_projection: AccountControlProjection;
  readonly rollback_coordinate: StrandedRollbackCoordinate;
  readonly source_receipts: readonly StrandedRollbackSourceReceipt[];
  readonly observed_at_epoch_seconds: number;
}

export type StrandedRollbackRecoveryBlocker =
  | "control_not_rolled_back_stranded"
  | "source_missing"
  | "source_fence_not_held";

export interface StrandedRollbackRecoveryReport {
  readonly version: typeof STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION;
  readonly status: "blocked" | "recoverable" | "disposition_due";
  readonly supplied_source_count: number;
  readonly required_source_count: number;
  readonly missing_surfaces: readonly StrandedRollbackRecoverySurface[];
  readonly unfenced_surfaces: readonly StrandedRollbackRecoverySurface[];
  readonly total_record_count: number;
  readonly blockers: readonly StrandedRollbackRecoveryBlocker[];
  readonly manifest_digest: string | null;
}

export interface VerifiedStrandedRollbackRecoveryManifest {
  readonly version: typeof STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION;
  readonly account_id: string;
  readonly control_revision: number;
  readonly account_epoch: number;
  readonly database_generation_digest: string;
  readonly cutover_frontier_digest: string;
  readonly rollback_frontier_digest: string;
  readonly cutover_at_epoch_seconds: number;
  readonly rolled_back_at_epoch_seconds: number;
  readonly recovery_deadline_epoch_seconds: number;
  readonly source_receipts: readonly StrandedRollbackSourceReceipt[];
  readonly rows: readonly Readonly<{
    readonly surface: StrandedRollbackRecoverySurface;
    readonly record_count: number;
    readonly record_set_digest: string;
  }>[];
  readonly manifest_digest: string;
}

export interface StrandedRollbackRecoveryVerification {
  readonly report: StrandedRollbackRecoveryReport;
  /** Process-local proof only; persistence must reverify source receipts. */
  readonly verified_manifest: VerifiedStrandedRollbackRecoveryManifest | null;
}

export type StrandedRollbackRecoveryInputErrorCode =
  | "invalid_input"
  | "invalid_control_projection"
  | "invalid_rollback_coordinate"
  | "rollback_coordinate_mismatch"
  | "invalid_source_receipts"
  | "invalid_source_receipt"
  | "duplicate_source_receipt"
  | "source_coordinate_mismatch";

export class StrandedRollbackRecoveryInputError extends TypeError {
  constructor(readonly code: StrandedRollbackRecoveryInputErrorCode) {
    super(code);
    this.name = "StrandedRollbackRecoveryInputError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const VERSION_TOKEN = /^[a-z0-9][a-z0-9._:-]{0,127}$/;
const MAX_RECORD_COUNT = 1_000_000_000;
const manifestBrand = new WeakSet<object>();

const fail = (code: StrandedRollbackRecoveryInputErrorCode): never => {
  throw new StrandedRollbackRecoveryInputError(code);
};
const safeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const digest = (value: unknown): value is string =>
  typeof value === "string" && DIGEST.test(value);
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: StrandedRollbackRecoveryInputErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    result[key] = descriptor.value;
  }
  return result;
};

const exactArray = (
  value: unknown,
  maximum: number,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail("invalid_source_receipts");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== value.length + 1) fail("invalid_source_receipts");
  const result: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      fail("invalid_source_receipts");
    }
    result.push(descriptor.value);
  }
  return result;
};

const parseControl = (value: unknown): AccountControlProjection => {
  const row = exactRecord(value, [
    "account_id", "control_revision", "account_generation", "account_epoch",
    "lifecycle_state", "deletion_epoch", "activation", "conflict",
  ], "invalid_control_projection");
  if (!isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || typeof row.account_generation !== "string"
    || !["legacy", "migrating", "new", "rolled_back_stranded"].includes(row.account_generation)
    || (row.account_epoch !== null && !safeInteger(row.account_epoch))
    || typeof row.lifecycle_state !== "string"
    || !["active", "deletion_pending", "deleted"].includes(row.lifecycle_state)
    || (row.deletion_epoch !== null && !safeInteger(row.deletion_epoch))) {
    fail("invalid_control_projection");
  }
  if (row.activation !== null) {
    const activation = exactRecord(row.activation, ["activated_epoch", "at_control_revision"],
      "invalid_control_projection");
    if (!safeInteger(activation.activated_epoch) || !safeInteger(activation.at_control_revision)) {
      fail("invalid_control_projection");
    }
    row.activation = Object.freeze({ ...activation });
  }
  if (row.conflict !== null) fail("invalid_control_projection");
  return Object.freeze({ ...row }) as unknown as AccountControlProjection;
};

const parseCoordinate = (value: unknown): StrandedRollbackCoordinate => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "account_epoch",
    "database_generation_digest", "cutover_frontier_digest", "rollback_frontier_digest",
    "cutover_at_epoch_seconds", "rolled_back_at_epoch_seconds",
    "recovery_deadline_epoch_seconds",
  ], "invalid_rollback_coordinate");
  if (row.version !== STRANDED_ROLLBACK_COORDINATE_VERSION
    || !isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !safeInteger(row.account_epoch) || !digest(row.database_generation_digest)
    || !digest(row.cutover_frontier_digest) || !digest(row.rollback_frontier_digest)
    || !safeInteger(row.cutover_at_epoch_seconds) || !safeInteger(row.rolled_back_at_epoch_seconds)
    || !safeInteger(row.recovery_deadline_epoch_seconds)
    || row.cutover_at_epoch_seconds > row.rolled_back_at_epoch_seconds
    || row.recovery_deadline_epoch_seconds
      !== row.rolled_back_at_epoch_seconds + STRANDED_ROLLBACK_RECOVERY_WINDOW_SECONDS
    || !Number.isSafeInteger(row.recovery_deadline_epoch_seconds)) {
    fail("invalid_rollback_coordinate");
  }
  return Object.freeze({ ...row }) as unknown as StrandedRollbackCoordinate;
};

const parseReceipt = (
  value: unknown,
  coordinate: StrandedRollbackCoordinate,
): StrandedRollbackSourceReceipt => {
  const row = exactRecord(value, [
    "version", "manifest_contract_version", "scanner_contract_version", "account_id",
    "control_revision", "account_epoch", "database_generation_digest", "surface",
    "source_frontier_digest", "source_fence_state", "source_fence_receipt_digest",
    "record_count", "record_set_digest",
  ], "invalid_source_receipt");
  if (row.version !== STRANDED_ROLLBACK_SOURCE_RECEIPT_VERSION
    || row.manifest_contract_version !== STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION
    || typeof row.scanner_contract_version !== "string"
    || !VERSION_TOKEN.test(row.scanner_contract_version)
    || !STRANDED_ROLLBACK_RECOVERY_SURFACES.includes(row.surface as never)
    || !digest(row.source_frontier_digest)
    || (row.source_fence_state !== "held" && row.source_fence_state !== "released")
    || !digest(row.source_fence_receipt_digest) || !safeInteger(row.record_count)
    || row.record_count > MAX_RECORD_COUNT || !digest(row.record_set_digest)) {
    fail("invalid_source_receipt");
  }
  if (row.account_id !== coordinate.account_id
    || row.control_revision !== coordinate.control_revision
    || row.account_epoch !== coordinate.account_epoch
    || row.database_generation_digest !== coordinate.database_generation_digest) {
    fail("source_coordinate_mismatch");
  }
  return Object.freeze({ ...row }) as unknown as StrandedRollbackSourceReceipt;
};

export const verifyStrandedRollbackRecovery = (
  value: unknown,
): StrandedRollbackRecoveryVerification => {
  const input = exactRecord(value, [
    "control_projection", "rollback_coordinate", "source_receipts", "observed_at_epoch_seconds",
  ], "invalid_input");
  const control = parseControl(input.control_projection);
  const coordinate = parseCoordinate(input.rollback_coordinate);
  if (!safeInteger(input.observed_at_epoch_seconds)
    || input.observed_at_epoch_seconds < coordinate.rolled_back_at_epoch_seconds) fail("invalid_input");
  if (control.account_id !== coordinate.account_id
    || control.control_revision !== coordinate.control_revision
    || control.account_epoch !== coordinate.account_epoch) fail("rollback_coordinate_mismatch");
  const receipts = exactArray(
    input.source_receipts, STRANDED_ROLLBACK_RECOVERY_SURFACES.length,
  ).map((receipt) => parseReceipt(receipt, coordinate));
  const bySurface = new Map<StrandedRollbackRecoverySurface, StrandedRollbackSourceReceipt>();
  for (const receipt of receipts) {
    if (bySurface.has(receipt.surface)) fail("duplicate_source_receipt");
    bySurface.set(receipt.surface, receipt);
  }
  const missing = STRANDED_ROLLBACK_RECOVERY_SURFACES.filter((surface) => !bySurface.has(surface));
  const unfenced = STRANDED_ROLLBACK_RECOVERY_SURFACES.filter((surface) =>
    bySurface.get(surface)?.source_fence_state === "released");
  const controlReady = control.account_generation === "rolled_back_stranded"
    && control.lifecycle_state === "active" && control.deletion_epoch === null
    && control.account_epoch !== null && control.activation === null;
  const blockers: StrandedRollbackRecoveryBlocker[] = [];
  if (!controlReady) blockers.push("control_not_rolled_back_stranded");
  if (missing.length > 0) blockers.push("source_missing");
  if (unfenced.length > 0) blockers.push("source_fence_not_held");
  const rows = STRANDED_ROLLBACK_RECOVERY_SURFACES.flatMap((surface) => {
    const receipt = bySurface.get(surface);
    return receipt === undefined ? [] : [Object.freeze({
      surface,
      record_count: receipt.record_count,
      record_set_digest: receipt.record_set_digest,
    })];
  });
  const totalRecordCount = rows.reduce((sum, row) => sum + row.record_count, 0);
  if (!Number.isSafeInteger(totalRecordCount)) fail("invalid_source_receipt");
  let manifest: VerifiedStrandedRollbackRecoveryManifest | null = null;
  if (blockers.length === 0) {
    const manifestCore = Object.freeze({
      version: STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
      account_id: coordinate.account_id,
      control_revision: coordinate.control_revision,
      account_epoch: coordinate.account_epoch,
      database_generation_digest: coordinate.database_generation_digest,
      cutover_frontier_digest: coordinate.cutover_frontier_digest,
      rollback_frontier_digest: coordinate.rollback_frontier_digest,
      cutover_at_epoch_seconds: coordinate.cutover_at_epoch_seconds,
      rolled_back_at_epoch_seconds: coordinate.rolled_back_at_epoch_seconds,
      recovery_deadline_epoch_seconds: coordinate.recovery_deadline_epoch_seconds,
      source_receipts: STRANDED_ROLLBACK_RECOVERY_SURFACES.map((surface) => bySurface.get(surface)),
    });
    const manifestDigest = sha256(manifestCore);
    manifest = Object.freeze({
      version: STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
      account_id: coordinate.account_id,
      control_revision: coordinate.control_revision,
      account_epoch: coordinate.account_epoch,
      database_generation_digest: coordinate.database_generation_digest,
      cutover_frontier_digest: coordinate.cutover_frontier_digest,
      rollback_frontier_digest: coordinate.rollback_frontier_digest,
      cutover_at_epoch_seconds: coordinate.cutover_at_epoch_seconds,
      rolled_back_at_epoch_seconds: coordinate.rolled_back_at_epoch_seconds,
      recovery_deadline_epoch_seconds: coordinate.recovery_deadline_epoch_seconds,
      source_receipts: Object.freeze(STRANDED_ROLLBACK_RECOVERY_SURFACES.map(
        (surface) => bySurface.get(surface)!,
      )),
      rows: Object.freeze(rows),
      manifest_digest: manifestDigest,
    });
    manifestBrand.add(manifest);
  }
  const manifestDigest = manifest?.manifest_digest ?? null;
  const report = Object.freeze({
    version: STRANDED_ROLLBACK_RECOVERY_CONTRACT_VERSION,
    status: blockers.length > 0 ? "blocked" as const
      : input.observed_at_epoch_seconds < coordinate.recovery_deadline_epoch_seconds
        ? "recoverable" as const : "disposition_due" as const,
    supplied_source_count: receipts.length,
    required_source_count: STRANDED_ROLLBACK_RECOVERY_SURFACES.length,
    missing_surfaces: Object.freeze(missing),
    unfenced_surfaces: Object.freeze(unfenced),
    total_record_count: totalRecordCount,
    blockers: Object.freeze(blockers),
    manifest_digest: manifestDigest,
  });
  return Object.freeze({ report, verified_manifest: manifest });
};

export const isVerifiedStrandedRollbackRecoveryManifest = (
  value: unknown,
): value is VerifiedStrandedRollbackRecoveryManifest =>
  value !== null && typeof value === "object" && manifestBrand.has(value);
