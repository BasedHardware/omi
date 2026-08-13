import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  TERMINAL_APPLICATION_OUTCOME_VERSION,
  type RestoreCoordinate,
  type TerminalApplicationOutcome,
  type TerminalReplayManifestRecord,
} from "../../core/control/tombstone-restore-replay";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
} from "./connection";

export interface HeldPostgresTombstoneRestoreTarget {
  apply(record: TerminalReplayManifestRecord): Promise<TerminalApplicationOutcome>;
}

export interface PostgresTombstoneRestoreTarget {
  withHeldTarget<T>(
    restore: RestoreCoordinate,
    callback: (target: HeldPostgresTombstoneRestoreTarget) => Promise<T>,
  ): Promise<T>;
  /** Per-record compatibility seam for the route-free restore coordinator. */
  applyTerminalRecord(request: Readonly<{
    restore: RestoreCoordinate;
    terminal_record: TerminalReplayManifestRecord;
  }>): Promise<TerminalApplicationOutcome>;
}

export class PostgresTombstoneRestoreTargetError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "restore_coordinate_denied"
    | "target_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresTombstoneRestoreTargetError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const MICROS = /^(?:0|[1-9][0-9]*)$/;
const MAX_COORDINATE_LENGTH = 256;

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactPlainRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) {
    throw new PostgresTombstoneRestoreTargetError("invalid_input");
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string") || ownKeys.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    throw new PostgresTombstoneRestoreTargetError("invalid_input");
  }
  for (const descriptor of Object.values(descriptors)) {
    if (!("value" in descriptor) || !descriptor.enumerable) {
      throw new PostgresTombstoneRestoreTargetError("invalid_input");
    }
  }
  return value as Record<string, unknown>;
};

const safeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const validateRestore = (value: unknown): RestoreCoordinate => {
  const row = exactPlainRecord(value, [
    "restore_id", "restore_scope", "restored_snapshot_digest",
    "restore_completed_at_epoch_seconds",
  ]);
  if (typeof row.restore_id !== "string" || row.restore_id.length === 0
    || row.restore_id.length > MAX_COORDINATE_LENGTH || !/^[\x21-\x7e]+$/.test(row.restore_id)
    || row.restore_scope !== "postgresql" || typeof row.restored_snapshot_digest !== "string"
    || !DIGEST.test(row.restored_snapshot_digest)
    || !safeInteger(row.restore_completed_at_epoch_seconds)) {
    throw new PostgresTombstoneRestoreTargetError("invalid_input");
  }
  return Object.freeze({
    restore_id: row.restore_id,
    restore_scope: "postgresql",
    restored_snapshot_digest: row.restored_snapshot_digest,
    restore_completed_at_epoch_seconds: row.restore_completed_at_epoch_seconds,
  });
};

const validateRecord = (value: unknown): TerminalReplayManifestRecord => {
  const row = exactPlainRecord(value, [
    "account_id", "control_revision", "deletion_epoch", "terminal_record_digest",
  ]);
  if (!isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !safeInteger(row.deletion_epoch) || typeof row.terminal_record_digest !== "string"
    || !DIGEST.test(row.terminal_record_digest)) {
    throw new PostgresTombstoneRestoreTargetError("invalid_input");
  }
  return Object.freeze({
    account_id: row.account_id,
    control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch,
    terminal_record_digest: row.terminal_record_digest,
  });
};

const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(error, "code");
  return descriptor && "value" in descriptor && typeof descriptor.value === "string"
    ? descriptor.value : null;
};

const mapFailure = (error: unknown): PostgresTombstoneRestoreTargetError => {
  if (error instanceof PostgresTombstoneRestoreTargetError) return error;
  if (providerCode(error) === "40001") {
    return new PostgresTombstoneRestoreTargetError("retryable_serialization");
  }
  if (providerCode(error) === "23505") {
    return new PostgresTombstoneRestoreTargetError("target_conflict");
  }
  if (providerCode(error) === "P0001" || providerCode(error) === "22023") {
    return new PostgresTombstoneRestoreTargetError("restore_coordinate_denied");
  }
  return new PostgresTombstoneRestoreTargetError("persistence_failed");
};

interface HoldRow extends Record<string, unknown> {
  backend_pid: unknown;
  database_now: unknown;
}

interface ApplyRow extends Record<string, unknown> {
  result: unknown;
  applied_at_epoch_micros: unknown;
}

const heldSession = async <T>(
  connection: CheckedOutPostgresConnection,
  restore: RestoreCoordinate,
  callback: (target: HeldPostgresTombstoneRestoreTarget) => Promise<T>,
): Promise<T> => {
  let active = true;
  const pending = new Set<Promise<unknown>>();
  let pendingFailure: unknown;
  let hasPendingFailure = false;
  const track = <Result>(operation: () => Promise<Result>): Promise<Result> => {
    if (!active) {
      return Promise.reject(new PostgresTombstoneRestoreTargetError("persistence_failed"));
    }
    const promise = operation();
    pending.add(promise);
    void promise.catch((error: unknown) => {
      if (!hasPendingFailure) pendingFailure = error;
      hasPendingFailure = true;
    }).finally(() => pending.delete(promise));
    return promise;
  };
  const target: HeldPostgresTombstoneRestoreTarget = Object.freeze({
    apply(value: TerminalReplayManifestRecord) {
      return track(async () => {
        const record = validateRecord(value);
        const rows = await connection.query<ApplyRow>({
          name: "restore_target.apply_terminal_fence",
          text: "SELECT * FROM omi_memory.apply_postgres_restore_terminal_fence($1, $2, $3, $4)",
          values: [
            record.account_id, record.control_revision,
            record.deletion_epoch, record.terminal_record_digest,
          ],
        });
        const row = rows[0];
        if (rows.length !== 1 || row === undefined
          || (row.result !== "applied" && row.result !== "already_absent")
          || typeof row.applied_at_epoch_micros !== "string"
          || !MICROS.test(row.applied_at_epoch_micros)) {
          throw new PostgresTombstoneRestoreTargetError("persistence_failed");
        }
        const targetReceiptDigest = sha256({
          version: "postgres-restore-target-receipt-v1",
          restore,
          terminal: record,
          result: row.result,
          applied_at_epoch_micros: row.applied_at_epoch_micros,
        });
        return Object.freeze({
          version: TERMINAL_APPLICATION_OUTCOME_VERSION,
          restore_id: restore.restore_id,
          restore_scope: restore.restore_scope,
          restored_snapshot_digest: restore.restored_snapshot_digest,
          account_id: record.account_id,
          control_revision: record.control_revision,
          deletion_epoch: record.deletion_epoch,
          terminal_record_digest: record.terminal_record_digest,
          result: row.result,
          target_receipt_digest: targetReceiptDigest,
          error_code: null,
        });
      });
    },
  });

  let callbackResult!: T;
  let callbackFailure: unknown;
  let hasCallbackFailure = false;
  try {
    callbackResult = await callback(target);
  } catch (error) {
    callbackFailure = error;
    hasCallbackFailure = true;
  } finally {
    active = false;
    while (pending.size > 0) await Promise.allSettled([...pending]);
  }
  if (hasCallbackFailure) throw callbackFailure;
  if (hasPendingFailure) throw pendingFailure;
  return callbackResult;
};

export const createPostgresTombstoneRestoreTarget = (
  pool: PostgresTransactionPool,
): PostgresTombstoneRestoreTarget => {
  const withHeldTarget = async <T>(
    restoreValue: RestoreCoordinate,
    callback: (target: HeldPostgresTombstoneRestoreTarget) => Promise<T>,
  ): Promise<T> => {
    const restore = validateRestore(restoreValue);
    if (typeof callback !== "function" || isProxy(callback)) {
      throw new PostgresTombstoneRestoreTargetError("invalid_input");
    }
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await connection.query({
            name: "restore_target.set_role",
            text: "SET LOCAL ROLE omi_platform_restore",
            values: [],
          });
          const rows = await connection.query<HoldRow>({
            name: "restore_target.hold",
            text: "SELECT * FROM omi_memory.hold_postgres_restore_target($1, $2, $3, $4)",
            values: [
              restore.restore_id, restore.restore_scope, restore.restored_snapshot_digest,
              restore.restore_completed_at_epoch_seconds,
            ],
          });
          if (rows.length !== 1) {
            throw new PostgresTombstoneRestoreTargetError("restore_coordinate_denied");
          }
          return heldSession(connection, restore, callback);
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  };
  return Object.freeze({
    withHeldTarget,
    async applyTerminalRecord(requestValue: unknown) {
      const request = exactPlainRecord(requestValue, ["restore", "terminal_record"]);
      // Detach both nested coordinates before the transaction/pool boundary.
      // The coordinator may retain and mutate its original request after this
      // method's first await; neither tenant nor terminal bytes may follow it.
      const restore = validateRestore(request.restore);
      const terminalRecord = validateRecord(request.terminal_record);
      return withHeldTarget(
        restore,
        async (target) => target.apply(terminalRecord),
      );
    },
  });
};
