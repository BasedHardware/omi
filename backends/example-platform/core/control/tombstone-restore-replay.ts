import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "./account-control";

export const TERMINAL_REPLAY_MANIFEST_VERSION = "terminal-replay-manifest-v1" as const;
export const TERMINAL_SET_SOURCE_RECEIPT_VERSION = "terminal-set-source-receipt-v1" as const;
export const TERMINAL_FEED_FENCE_VERSION = "terminal-feed-fence-v1" as const;
export const TERMINAL_APPLICATION_OUTCOME_VERSION = "terminal-application-outcome-v1" as const;
export const TOMBSTONE_REPLAY_REPORT_VERSION = "tombstone-replay-report-v1" as const;
export const TOMBSTONE_REPLAY_CHECKPOINT_VERSION = "tombstone-replay-checkpoint-v1" as const;
export const MAX_TERMINAL_REPLAY_RECORDS = 10_000;

const DIGEST = /^[0-9a-f]{64}$/;
const MAX_COORDINATE_LENGTH = 256;

export type RestoreScope = "legacy" | "postgresql";

export interface TerminalReplayManifestRecord {
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly terminal_record_digest: string;
}

export interface TerminalReplayManifest {
  readonly version: typeof TERMINAL_REPLAY_MANIFEST_VERSION;
  readonly source_snapshot_digest: string;
  readonly source_high_watermark: number;
  readonly captured_at_epoch_seconds: number;
  readonly records: readonly TerminalReplayManifestRecord[];
  readonly manifest_digest: string;
}

export interface TerminalSetSourceReceipt {
  readonly version: typeof TERMINAL_SET_SOURCE_RECEIPT_VERSION;
  readonly sink_contract_version: string;
  readonly source_snapshot_digest: string;
  readonly source_high_watermark: number;
  readonly record_count: number;
  readonly manifest_digest: string;
  readonly retention_locked_sink_receipt_digest: string;
}

export interface RestoreCoordinate {
  readonly restore_id: string;
  readonly restore_scope: RestoreScope;
  readonly restored_snapshot_digest: string;
  readonly restore_completed_at_epoch_seconds: number;
}

export interface TerminalFeedFence {
  readonly version: typeof TERMINAL_FEED_FENCE_VERSION;
  readonly state: "held" | "released";
  readonly restore_id: string;
  readonly restore_scope: RestoreScope;
  readonly source_snapshot_digest: string;
  readonly source_high_watermark: number;
  readonly fence_receipt_digest: string;
}

export type TerminalApplicationResult =
  | "applied"
  | "already_absent"
  | "retryable_error"
  | "terminal_error";

export type TerminalApplicationErrorCode =
  | "target_unavailable"
  | "target_write_failed"
  | "target_conflict"
  | "target_verification_failed";

export interface TerminalApplicationOutcome {
  readonly version: typeof TERMINAL_APPLICATION_OUTCOME_VERSION;
  readonly restore_id: string;
  readonly restore_scope: RestoreScope;
  readonly restored_snapshot_digest: string;
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly terminal_record_digest: string;
  readonly result: TerminalApplicationResult;
  readonly target_receipt_digest: string | null;
  readonly error_code: TerminalApplicationErrorCode | null;
}

export type TombstoneReplayBlocker =
  | "terminal_set_predates_restore"
  | "terminal_feed_not_held"
  | "application_missing"
  | "application_retryable_error"
  | "application_terminal_error";

export interface TombstoneReplayCheckpoint {
  readonly version: typeof TOMBSTONE_REPLAY_CHECKPOINT_VERSION;
  readonly restore_id: string;
  readonly restore_scope: RestoreScope;
  readonly restored_snapshot_digest: string;
  readonly restore_completed_at_epoch_seconds: number;
  readonly source_snapshot_digest: string;
  readonly source_high_watermark: number;
  readonly manifest_digest: string;
  readonly terminal_source_receipt_binding_digest: string;
  readonly application_set_digest: string;
  readonly traffic_fence_receipt_digest: string;
  readonly checkpoint_digest: string;
}

export interface TombstoneReplayReport {
  readonly version: typeof TOMBSTONE_REPLAY_REPORT_VERSION;
  readonly restore_id: string;
  readonly restore_scope: RestoreScope;
  readonly restored_snapshot_digest: string;
  readonly source_snapshot_digest: string;
  readonly source_high_watermark: number;
  readonly manifest_digest: string;
  readonly record_count: number;
  readonly successful_count: number;
  readonly missing_count: number;
  readonly retryable_error_count: number;
  readonly terminal_error_count: number;
  readonly blockers: readonly TombstoneReplayBlocker[];
  /** Present only when lifecycle replay does not fence. It grants no authority. */
  readonly checkpoint: TombstoneReplayCheckpoint | null;
}

export interface TombstoneReplayVerificationInput {
  readonly restore: RestoreCoordinate;
  readonly manifest: TerminalReplayManifest;
  readonly source_receipt: TerminalSetSourceReceipt;
  readonly traffic_fence: TerminalFeedFence | null;
  readonly applications: readonly TerminalApplicationOutcome[];
}

export type TombstoneReplayInputErrorCode =
  | "invalid_input"
  | "invalid_restore_coordinate"
  | "invalid_manifest"
  | "manifest_over_budget"
  | "application_over_budget"
  | "duplicate_manifest_account"
  | "manifest_digest_mismatch"
  | "invalid_source_receipt"
  | "source_receipt_mismatch"
  | "invalid_traffic_fence"
  | "invalid_application_outcome"
  | "duplicate_application_outcome"
  | "application_not_in_manifest"
  | "application_coordinate_mismatch";

export class TombstoneReplayInputError extends TypeError {
  readonly code: TombstoneReplayInputErrorCode;

  constructor(code: TombstoneReplayInputErrorCode) {
    super(code);
    this.name = "TombstoneReplayInputError";
    this.code = code;
  }
}

const fail = (code: TombstoneReplayInputErrorCode): never => {
  throw new TombstoneReplayInputError(code);
};

type PlainRecord = Record<string, unknown>;

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: TombstoneReplayInputErrorCode,
): PlainRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string") || ownKeys.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  for (const descriptor of Object.values(descriptors)) {
    if (!("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as PlainRecord;
};

const plainArray = (
  value: unknown,
  maxLength: number,
  code: TombstoneReplayInputErrorCode,
  overBudgetCode: TombstoneReplayInputErrorCode = code,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    fail(code);
  }
  const arrayValue = value as unknown[];
  if (arrayValue.length > maxLength) fail(overBudgetCode);
  const descriptors = Object.getOwnPropertyDescriptors(arrayValue);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string") || ownKeys.length !== arrayValue.length + 1
    || !Object.prototype.hasOwnProperty.call(descriptors, "length")) fail(code);
  for (let index = 0; index < arrayValue.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return arrayValue;
};

const safeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const boundedCoordinate = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= MAX_COORDINATE_LENGTH
  && /^[\x21-\x7e]+$/.test(value);

const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);

const restoreScope = (value: unknown): value is RestoreScope => value === "legacy" || value === "postgresql";

const sha256 = (value: unknown): string =>
  createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");

const compareRecord = (
  left: TerminalReplayManifestRecord,
  right: TerminalReplayManifestRecord,
): number => (left.account_id < right.account_id ? -1 : left.account_id > right.account_id ? 1 : 0)
  || left.deletion_epoch - right.deletion_epoch
  || left.control_revision - right.control_revision
  || (left.terminal_record_digest < right.terminal_record_digest
    ? -1 : left.terminal_record_digest > right.terminal_record_digest ? 1 : 0);

const parseManifestRecord = (value: unknown): TerminalReplayManifestRecord => {
  const row = exactRecord(value, [
    "account_id",
    "control_revision",
    "deletion_epoch",
    "terminal_record_digest",
  ], "invalid_manifest");
  if (!isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !safeInteger(row.deletion_epoch) || !digest(row.terminal_record_digest)) fail("invalid_manifest");
  return Object.freeze({
    account_id: row.account_id,
    control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch,
    terminal_record_digest: row.terminal_record_digest,
  }) as TerminalReplayManifestRecord;
};

const normalizeManifestRecords = (value: unknown): readonly TerminalReplayManifestRecord[] => {
  const values = plainArray(
    value,
    MAX_TERMINAL_REPLAY_RECORDS,
    "invalid_manifest",
    "manifest_over_budget",
  );
  const records = values.map(parseManifestRecord).sort(compareRecord);
  for (let index = 1; index < records.length; index += 1) {
    if (records[index - 1]!.account_id === records[index]!.account_id) fail("duplicate_manifest_account");
  }
  return Object.freeze(records);
};

const manifestCore = (
  sourceSnapshotDigest: string,
  sourceHighWatermark: number,
  capturedAt: number,
  records: readonly TerminalReplayManifestRecord[],
) => ({
  version: TERMINAL_REPLAY_MANIFEST_VERSION,
  source_snapshot_digest: sourceSnapshotDigest,
  source_high_watermark: sourceHighWatermark,
  captured_at_epoch_seconds: capturedAt,
  records,
});

export const buildTerminalReplayManifest = (inputValue: unknown): TerminalReplayManifest => {
  const input = exactRecord(inputValue, [
    "source_snapshot_digest",
    "source_high_watermark",
    "captured_at_epoch_seconds",
    "records",
  ], "invalid_manifest");
  if (!digest(input.source_snapshot_digest) || !safeInteger(input.source_high_watermark)
    || !safeInteger(input.captured_at_epoch_seconds)) fail("invalid_manifest");
  const sourceSnapshotDigest = input.source_snapshot_digest as string;
  const sourceHighWatermark = input.source_high_watermark as number;
  const capturedAt = input.captured_at_epoch_seconds as number;
  const records = normalizeManifestRecords(input.records);
  const core = manifestCore(
    sourceSnapshotDigest,
    sourceHighWatermark,
    capturedAt,
    records,
  );
  return Object.freeze({ ...core, manifest_digest: sha256(core) });
};

const parseManifest = (value: unknown): TerminalReplayManifest => {
  const row = exactRecord(value, [
    "version",
    "source_snapshot_digest",
    "source_high_watermark",
    "captured_at_epoch_seconds",
    "records",
    "manifest_digest",
  ], "invalid_manifest");
  if (row.version !== TERMINAL_REPLAY_MANIFEST_VERSION || !digest(row.source_snapshot_digest)
    || !safeInteger(row.source_high_watermark) || !safeInteger(row.captured_at_epoch_seconds)
    || !digest(row.manifest_digest)) fail("invalid_manifest");
  const sourceSnapshotDigest = row.source_snapshot_digest as string;
  const sourceHighWatermark = row.source_high_watermark as number;
  const capturedAt = row.captured_at_epoch_seconds as number;
  const manifestDigest = row.manifest_digest as string;
  const records = normalizeManifestRecords(row.records);
  const core = manifestCore(
    sourceSnapshotDigest,
    sourceHighWatermark,
    capturedAt,
    records,
  );
  if (sha256(core) !== manifestDigest) fail("manifest_digest_mismatch");
  return Object.freeze({ ...core, manifest_digest: manifestDigest });
};

const parseRestore = (value: unknown): RestoreCoordinate => {
  const row = exactRecord(value, [
    "restore_id",
    "restore_scope",
    "restored_snapshot_digest",
    "restore_completed_at_epoch_seconds",
  ], "invalid_restore_coordinate");
  if (!boundedCoordinate(row.restore_id) || !restoreScope(row.restore_scope)
    || !digest(row.restored_snapshot_digest)
    || !safeInteger(row.restore_completed_at_epoch_seconds)) fail("invalid_restore_coordinate");
  return Object.freeze({
    restore_id: row.restore_id as string,
    restore_scope: row.restore_scope as RestoreScope,
    restored_snapshot_digest: row.restored_snapshot_digest as string,
    restore_completed_at_epoch_seconds: row.restore_completed_at_epoch_seconds as number,
  });
};

const parseSourceReceipt = (value: unknown): TerminalSetSourceReceipt => {
  const row = exactRecord(value, [
    "version",
    "sink_contract_version",
    "source_snapshot_digest",
    "source_high_watermark",
    "record_count",
    "manifest_digest",
    "retention_locked_sink_receipt_digest",
  ], "invalid_source_receipt");
  if (row.version !== TERMINAL_SET_SOURCE_RECEIPT_VERSION
    || !boundedCoordinate(row.sink_contract_version) || !digest(row.source_snapshot_digest)
    || !safeInteger(row.source_high_watermark) || !safeInteger(row.record_count)
    || row.record_count > MAX_TERMINAL_REPLAY_RECORDS || !digest(row.manifest_digest)
    || !digest(row.retention_locked_sink_receipt_digest)) fail("invalid_source_receipt");
  return value as TerminalSetSourceReceipt;
};

const parseFence = (value: unknown): TerminalFeedFence | null => {
  if (value === null) return null;
  const row = exactRecord(value, [
    "version",
    "state",
    "restore_id",
    "restore_scope",
    "source_snapshot_digest",
    "source_high_watermark",
    "fence_receipt_digest",
  ], "invalid_traffic_fence");
  if (row.version !== TERMINAL_FEED_FENCE_VERSION || (row.state !== "held" && row.state !== "released")
    || !boundedCoordinate(row.restore_id) || !restoreScope(row.restore_scope)
    || !digest(row.source_snapshot_digest) || !safeInteger(row.source_high_watermark)
    || !digest(row.fence_receipt_digest)) fail("invalid_traffic_fence");
  return value as TerminalFeedFence;
};

const RETRYABLE_CODES: ReadonlySet<string> = new Set([
  "target_unavailable",
  "target_write_failed",
]);
const TERMINAL_CODES: ReadonlySet<string> = new Set([
  "target_conflict",
  "target_verification_failed",
]);

const parseApplication = (value: unknown): TerminalApplicationOutcome => {
  const row = exactRecord(value, [
    "version",
    "restore_id",
    "restore_scope",
    "restored_snapshot_digest",
    "account_id",
    "control_revision",
    "deletion_epoch",
    "terminal_record_digest",
    "result",
    "target_receipt_digest",
    "error_code",
  ], "invalid_application_outcome");
  if (row.version !== TERMINAL_APPLICATION_OUTCOME_VERSION || !boundedCoordinate(row.restore_id)
    || !restoreScope(row.restore_scope) || !digest(row.restored_snapshot_digest)
    || !isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !safeInteger(row.deletion_epoch) || !digest(row.terminal_record_digest)
    || !(["applied", "already_absent", "retryable_error", "terminal_error"] as const)
      .includes(row.result as never)) fail("invalid_application_outcome");
  const success = row.result === "applied" || row.result === "already_absent";
  const retryable = row.result === "retryable_error";
  const terminal = row.result === "terminal_error";
  if ((success && (!digest(row.target_receipt_digest) || row.error_code !== null))
    || (!success && row.target_receipt_digest !== null)
    || (retryable && (typeof row.error_code !== "string" || !RETRYABLE_CODES.has(row.error_code)))
    || (terminal && (typeof row.error_code !== "string" || !TERMINAL_CODES.has(row.error_code)))) {
    fail("invalid_application_outcome");
  }
  return value as TerminalApplicationOutcome;
};

const applicationSort = (
  left: TerminalApplicationOutcome,
  right: TerminalApplicationOutcome,
): number => left.account_id < right.account_id ? -1 : left.account_id > right.account_id ? 1 : 0;

const checkpointCore = (
  restore: RestoreCoordinate,
  manifest: TerminalReplayManifest,
  sourceReceiptBindingDigest: string,
  applicationSetDigest: string,
  fence: TerminalFeedFence,
) => ({
  version: TOMBSTONE_REPLAY_CHECKPOINT_VERSION,
  restore_id: restore.restore_id,
  restore_scope: restore.restore_scope,
  restored_snapshot_digest: restore.restored_snapshot_digest,
  restore_completed_at_epoch_seconds: restore.restore_completed_at_epoch_seconds,
  source_snapshot_digest: manifest.source_snapshot_digest,
  source_high_watermark: manifest.source_high_watermark,
  manifest_digest: manifest.manifest_digest,
  terminal_source_receipt_binding_digest: sourceReceiptBindingDigest,
  application_set_digest: applicationSetDigest,
  traffic_fence_receipt_digest: fence.fence_receipt_digest,
});

export const verifyTombstoneRestoreReplay = (inputValue: unknown): TombstoneReplayReport => {
  const input = exactRecord(inputValue, [
    "restore",
    "manifest",
    "source_receipt",
    "traffic_fence",
    "applications",
  ], "invalid_input");
  const restore = parseRestore(input.restore);
  const manifest = parseManifest(input.manifest);
  const sourceReceipt = parseSourceReceipt(input.source_receipt);
  const trafficFence = parseFence(input.traffic_fence);
  const applicationValues = plainArray(
    input.applications,
    MAX_TERMINAL_REPLAY_RECORDS,
    "invalid_application_outcome",
    "application_over_budget",
  );
  const applications = applicationValues.map(parseApplication).sort(applicationSort);

  if (sourceReceipt.source_snapshot_digest !== manifest.source_snapshot_digest
    || sourceReceipt.source_high_watermark !== manifest.source_high_watermark
    || sourceReceipt.record_count !== manifest.records.length
    || sourceReceipt.manifest_digest !== manifest.manifest_digest) fail("source_receipt_mismatch");

  const recordsByAccount = new Map(manifest.records.map((record) => [record.account_id, record]));
  const applicationsByAccount = new Map<string, TerminalApplicationOutcome>();
  for (const application of applications) {
    if (applicationsByAccount.has(application.account_id)) fail("duplicate_application_outcome");
    const record = recordsByAccount.get(application.account_id);
    if (record === undefined) fail("application_not_in_manifest");
    if (application.restore_id !== restore.restore_id
      || application.restore_scope !== restore.restore_scope
      || application.restored_snapshot_digest !== restore.restored_snapshot_digest
      || application.control_revision !== record.control_revision
      || application.deletion_epoch !== record.deletion_epoch
      || application.terminal_record_digest !== record.terminal_record_digest) {
      fail("application_coordinate_mismatch");
    }
    applicationsByAccount.set(application.account_id, application);
  }

  const fenceHeld = trafficFence !== null
    && trafficFence.state === "held"
    && trafficFence.restore_id === restore.restore_id
    && trafficFence.restore_scope === restore.restore_scope
    && trafficFence.source_snapshot_digest === manifest.source_snapshot_digest
    && trafficFence.source_high_watermark === manifest.source_high_watermark;
  const capturedAfterRestore = manifest.captured_at_epoch_seconds
    >= restore.restore_completed_at_epoch_seconds;
  let successfulCount = 0;
  let retryableErrorCount = 0;
  let terminalErrorCount = 0;
  for (const application of applications) {
    if (application.result === "applied" || application.result === "already_absent") successfulCount += 1;
    else if (application.result === "retryable_error") retryableErrorCount += 1;
    else terminalErrorCount += 1;
  }
  const missingCount = manifest.records.length - applications.length;
  const blockers: TombstoneReplayBlocker[] = [];
  if (!capturedAfterRestore) blockers.push("terminal_set_predates_restore");
  if (!fenceHeld) blockers.push("terminal_feed_not_held");
  if (missingCount > 0) blockers.push("application_missing");
  if (retryableErrorCount > 0) blockers.push("application_retryable_error");
  if (terminalErrorCount > 0) blockers.push("application_terminal_error");

  let checkpoint: TombstoneReplayCheckpoint | null = null;
  if (blockers.length === 0 && trafficFence !== null) {
    const sourceReceiptBindingDigest = sha256({
      version: sourceReceipt.version,
      sink_contract_version: sourceReceipt.sink_contract_version,
      source_snapshot_digest: sourceReceipt.source_snapshot_digest,
      source_high_watermark: sourceReceipt.source_high_watermark,
      record_count: sourceReceipt.record_count,
      manifest_digest: sourceReceipt.manifest_digest,
      retention_locked_sink_receipt_digest: sourceReceipt.retention_locked_sink_receipt_digest,
    });
    const successfulApplications = applications.map((application) => ({
      account_id: application.account_id,
      control_revision: application.control_revision,
      deletion_epoch: application.deletion_epoch,
      terminal_record_digest: application.terminal_record_digest,
      result: application.result,
      target_receipt_digest: application.target_receipt_digest,
    }));
    const applicationSetDigest = sha256({
      version: "terminal-application-set-v1",
      restore_id: restore.restore_id,
      restore_scope: restore.restore_scope,
      restored_snapshot_digest: restore.restored_snapshot_digest,
      applications: successfulApplications,
    });
    const core = checkpointCore(
      restore,
      manifest,
      sourceReceiptBindingDigest,
      applicationSetDigest,
      trafficFence,
    );
    checkpoint = Object.freeze({ ...core, checkpoint_digest: sha256(core) });
  }

  return Object.freeze({
    version: TOMBSTONE_REPLAY_REPORT_VERSION,
    restore_id: restore.restore_id,
    restore_scope: restore.restore_scope,
    restored_snapshot_digest: restore.restored_snapshot_digest,
    source_snapshot_digest: manifest.source_snapshot_digest,
    source_high_watermark: manifest.source_high_watermark,
    manifest_digest: manifest.manifest_digest,
    record_count: manifest.records.length,
    successful_count: successfulCount,
    missing_count: missingCount,
    retryable_error_count: retryableErrorCount,
    terminal_error_count: terminalErrorCount,
    blockers: Object.freeze(blockers),
    checkpoint,
  });
};
