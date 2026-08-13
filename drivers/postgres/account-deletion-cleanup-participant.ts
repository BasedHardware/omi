import { createHash } from "node:crypto";

import {
  DELETION_DISPOSAL_GROUPS,
  DELETION_INVENTORY_CONTRACT_VERSION,
  DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
  type DeletionCleanupSurface,
  type DeletionInventorySourceReceipt,
} from "../../core/control/deletion-cleanup-inventory";
import type { DeletionCleanupDispositionReceipt } from
  "../../apps/service/workers/account-deletion-cleanup";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
} from "./connection";
import { POSTGRES_DELETION_SURFACE_TABLES } from "./deletion-surface-registry";

export type PostgresDeletionCleanupSurface = keyof typeof POSTGRES_DELETION_SURFACE_TABLES;

export interface PostgresDeletionCleanupCoordinate {
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
}

export interface HeldPostgresDeletionCleanupSession {
  scanOwned(): Promise<readonly DeletionInventorySourceReceipt[]>;
  dispose(
    surfaces: readonly PostgresDeletionCleanupSurface[],
  ): Promise<readonly DeletionCleanupDispositionReceipt[]>;
}

export interface PostgresDeletionCleanupParticipant {
  withHeldDatabaseFence<T>(
    coordinate: PostgresDeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldPostgresDeletionCleanupSession) => Promise<T>,
  ): Promise<T>;
}

export class PostgresDeletionCleanupError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "terminal_coordinate_denied"
    | "surface_denied"
    | "receipt_conflict"
    | "retryable_serialization"
    | "persistence_failed") {
    super(code);
    this.name = "PostgresDeletionCleanupError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION = /^opref1_[0-9a-f]{64}$/;
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const safeInteger = (value: unknown): number => {
  if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) value = Number(value);
  if (typeof value === "bigint") value = Number(value);
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new PostgresDeletionCleanupError("persistence_failed");
  }
  return value;
};

const providerCode = (error: unknown): string | null => {
  if (error === null || typeof error !== "object") return null;
  const value = Reflect.get(error, "code");
  return typeof value === "string" ? value : null;
};

const mapFailure = (error: unknown): PostgresDeletionCleanupError => {
  if (error instanceof PostgresDeletionCleanupError) return error;
  if (providerCode(error) === "40001") {
    return new PostgresDeletionCleanupError("retryable_serialization");
  }
  if (providerCode(error) === "23505") return new PostgresDeletionCleanupError("receipt_conflict");
  if (providerCode(error) === "P0001") {
    return new PostgresDeletionCleanupError("terminal_coordinate_denied");
  }
  return new PostgresDeletionCleanupError("persistence_failed");
};

const ownedSurfaces = Object.freeze(Object.keys(
  POSTGRES_DELETION_SURFACE_TABLES,
) as PostgresDeletionCleanupSurface[]);
const ownedSet = new Set<string>(ownedSurfaces);
const allowedGroups = DELETION_DISPOSAL_GROUPS
  .filter((group) => group.every((surface) => ownedSet.has(surface)))
  .map((group) => JSON.stringify(group));

const validateCoordinate = (coordinate: PostgresDeletionCleanupCoordinate): void => {
  if (coordinate === null || typeof coordinate !== "object" || Array.isArray(coordinate)
    || typeof coordinate.account_id !== "string" || coordinate.account_id.length === 0
    || !Number.isSafeInteger(coordinate.control_revision) || coordinate.control_revision < 0
    || !Number.isSafeInteger(coordinate.deletion_epoch) || coordinate.deletion_epoch < 0) {
    throw new PostgresDeletionCleanupError("invalid_input");
  }
};

const assertGroup = (
  surfaces: readonly PostgresDeletionCleanupSurface[],
): readonly PostgresDeletionCleanupSurface[] => {
  const encoded = JSON.stringify(surfaces);
  if (!allowedGroups.includes(encoded)) throw new PostgresDeletionCleanupError("surface_denied");
  return surfaces;
};

interface LockRow extends Record<string, unknown> {
  terminal_content_hash: unknown;
  export_content_hash: unknown;
  backend_pid: unknown;
  database_now: unknown;
}

interface ScanRow extends Record<string, unknown> {
  table_name: unknown;
  row_count: unknown;
}

interface DispositionRow extends Record<string, unknown> {
  surface: unknown;
  result: unknown;
  affected_count: unknown;
  completed_at: unknown;
}

const lockedSession = async (
  connection: CheckedOutPostgresConnection,
  coordinate: PostgresDeletionCleanupCoordinate,
  operationRef: string,
  eligibilityDigest: string,
  lock: LockRow,
  callback: (session: HeldPostgresDeletionCleanupSession) => Promise<unknown>,
): Promise<unknown> => {
  const terminalHash = lock.terminal_content_hash;
  const exportHash = lock.export_content_hash;
  const backendPid = safeInteger(lock.backend_pid);
  if (typeof terminalHash !== "string" || !DIGEST.test(terminalHash)
    || typeof exportHash !== "string" || !DIGEST.test(exportHash)) {
    throw new PostgresDeletionCleanupError("persistence_failed");
  }
  let active = true;
  const pending = new Set<Promise<unknown>>();
  let pendingFailure: unknown;
  let hasPendingFailure = false;
  const track = <T>(operation: () => Promise<T>): Promise<T> => {
    if (!active) return Promise.reject(
      new PostgresDeletionCleanupError("persistence_failed"),
    );
    const promise = operation();
    pending.add(promise);
    void promise.catch((error: unknown) => {
      if (!hasPendingFailure) pendingFailure = error;
      hasPendingFailure = true;
    }).finally(() => pending.delete(promise));
    return promise;
  };
  const session: HeldPostgresDeletionCleanupSession = Object.freeze({
    scanOwned() {
      return track(async () => {
        const receipts: DeletionInventorySourceReceipt[] = [];
        for (const surface of ownedSurfaces) {
          const rows = await connection.query<ScanRow>({
            name: "cleanup.scan_surface",
            text: "SELECT * FROM omi_memory.scan_deleted_account_surface($1)",
            values: [surface],
          });
          const expectedTables = [...POSTGRES_DELETION_SURFACE_TABLES[surface]].sort();
          const normalized = rows.map((row) => ({
            table_name: typeof row.table_name === "string" ? row.table_name : "",
            row_count: safeInteger(row.row_count),
          })).sort((left, right) => left.table_name.localeCompare(right.table_name));
          if (normalized.length !== expectedTables.length
            || normalized.some((row, index) => row.table_name !== expectedTables[index])) {
            throw new PostgresDeletionCleanupError("persistence_failed");
          }
          const remaining = normalized.reduce((sum, row) => sum + row.row_count, 0);
          receipts.push(Object.freeze({
            version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
            inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
            scanner_contract_version: "postgres-account-surface-v1",
            account_id: coordinate.account_id,
            control_revision: coordinate.control_revision,
            deletion_epoch: coordinate.deletion_epoch,
            surface,
            source_frontier_digest: sha256({ terminalHash, exportHash, surface, normalized }),
            source_authorization_digest: eligibilityDigest,
            scan_fence_state: "held",
            scan_fence_receipt_digest: sha256({
              version: "postgres-cleanup-fence-v1", backendPid, coordinate,
              operationRef, eligibilityDigest,
            }),
            remaining_count: remaining,
            remaining_set_digest: sha256({ surface, rows: normalized }),
          }));
        }
        return Object.freeze(receipts);
      });
    },
    dispose(surfaces: readonly PostgresDeletionCleanupSurface[]) {
      return track(async () => {
        const group = assertGroup(surfaces);
        const rows = await connection.query<DispositionRow>({
          name: "cleanup.dispose_group",
          text: "SELECT * FROM omi_memory.dispose_deleted_account_surfaces($1, $2, $3)",
          values: [JSON.stringify(group), operationRef, eligibilityDigest],
        });
        if (rows.length !== group.length) {
          throw new PostgresDeletionCleanupError("persistence_failed");
        }
        return Object.freeze(group.map((surface) => {
          const row = rows.find((candidate) => candidate.surface === surface);
          if (!row || (row.result !== "disposed" && row.result !== "already_absent")) {
            throw new PostgresDeletionCleanupError("persistence_failed");
          }
          const affected = safeInteger(row.affected_count);
          return Object.freeze({
            version: "deletion-cleanup-disposition-v1" as const,
            surface: surface as DeletionCleanupSurface,
            result: row.result,
            receipt_digest: sha256({
              version: "postgres-deletion-surface-receipt-v1",
              coordinate, operationRef, eligibilityDigest, surface,
              result: row.result, affected, completed_at: String(row.completed_at),
            }),
          });
        }));
      });
    },
  });
  let result: unknown;
  let callbackFailure: unknown;
  let hasCallbackFailure = false;
  try {
    result = await callback(session);
  } catch (error) {
    callbackFailure = error;
    hasCallbackFailure = true;
  } finally {
    active = false;
    while (pending.size > 0) await Promise.allSettled([...pending]);
  }
  if (hasCallbackFailure) throw callbackFailure;
  if (hasPendingFailure) throw pendingFailure;
  return result;
};

export const createPostgresDeletionCleanupParticipant = (
  pool: PostgresTransactionPool,
): PostgresDeletionCleanupParticipant => Object.freeze({
  async withHeldDatabaseFence<T>(
    coordinate: PostgresDeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldPostgresDeletionCleanupSession) => Promise<T>,
  ): Promise<T> {
    validateCoordinate(coordinate);
    if (!OPERATION.test(operationRef) || !DIGEST.test(eligibilityDigest)
      || typeof callback !== "function") throw new PostgresDeletionCleanupError("invalid_input");
    try {
      return await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read write" },
        async (connection) => {
          await connection.query({
            name: "cleanup.set_role",
            text: "SET LOCAL ROLE omi_platform_cleanup",
            values: [],
          });
          const rows = await connection.query<LockRow>({
            name: "cleanup.lock_terminal",
            text: "SELECT * FROM omi_memory.lock_deleted_account_cleanup($1, $2, $3, $4)",
            values: [
              coordinate.account_id, coordinate.control_revision,
              coordinate.deletion_epoch, eligibilityDigest,
            ],
          });
          if (rows.length !== 1) throw new PostgresDeletionCleanupError("terminal_coordinate_denied");
          return lockedSession(
            connection, coordinate, operationRef, eligibilityDigest, rows[0]!, callback,
          ) as Promise<T>;
        },
      );
    } catch (error) {
      throw mapFailure(error);
    }
  },
});
