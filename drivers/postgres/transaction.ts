import { createHash } from "node:crypto";

import {
  assertAuthorizedLedgerWriteContext,
  assertAuthorizedLedgerWriteContextCurrentAt,
  type AuthorizedLedgerWriteContext,
} from "../../apps/service/auth/authorized-context";
import type {
  DatabaseOutcome,
  OperationalTelemetryEmitter,
} from "../../core/observability/operational-telemetry";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SqlStatement,
} from "./connection";

export type PostgresRepositoryErrorCode =
  | "authorization_state_denied"
  | "expired_context"
  | "stale_epoch"
  | "destination_inactive"
  | "lifecycle_inactive"
  | "credential_inactive"
  | "grant_inactive"
  | "capability_denied"
  | "idempotency_conflict"
  | "stale_parent"
  | "retryable_serialization"
  | "transition_invalid"
  | "persistence_failed";

/** Stable, content-safe adapter error. Raw SQL/provider errors never escape. */
export class PostgresRepositoryError extends Error {
  constructor(
    readonly code: PostgresRepositoryErrorCode,
    readonly retryable = false,
  ) {
    super(code);
    this.name = "PostgresRepositoryError";
  }
}

export interface AuthorityStateRow extends Record<string, unknown> {
  readonly account_id: string;
  readonly principal_id: string;
  readonly application_id: string;
  readonly credential_id: string;
  readonly credential_generation: number;
  readonly capability: string;
  readonly grant_id: string;
  readonly grant_version: number;
  readonly account_epoch: number | null;
  readonly control_conflict_reason: string | null;
  readonly control_conflict_at_revision: number | null;
  readonly destination_activation_epoch: number | null;
  readonly destination_activation_revision: number | null;
  readonly lifecycle_state: "active" | "deletion_pending" | "deleted";
  readonly deletion_epoch: number | null;
  readonly account_generation: "legacy" | "migrating" | "new" | "rolled_back_stranded";
  readonly credential_lifecycle: "active" | "inactive" | "revoked";
  readonly grant_lifecycle: "active" | "inactive" | "revoked";
  readonly grant_enabled: boolean;
  readonly authentication_strength: string;
  readonly credential_expires_at_epoch_seconds: number | null;
  readonly control_revision: number;
  readonly control_content_hash: string;
  readonly credential_content_hash: string;
  readonly grant_content_hash: string;
  readonly db_now_epoch_seconds: number;
}

export const SET_LOCAL_AUTHORITY_CONTEXT: SqlStatement["text"] = `
SELECT
  set_config('omi.account_id', $1, true),
  set_config('omi.principal_id', $2, true),
  set_config('omi.grant_id', $3, true),
  set_config('omi.account_epoch', $4, true),
  set_config('omi.lifecycle', $5, true),
  set_config('omi.capability', $6, true)
`;

export const LOCK_AUTHORITY_STATE: SqlStatement["text"] = `
SELECT *
FROM omi_memory.lock_unfenced_authority_state($1, $2, $3, $4, $5, $6, $7)
`;

/** Exact digest minted from the persisted revisions that authorize the context. */
export const authorizationStateDigest = (row: AuthorityStateRow): string =>
  createHash("sha256").update(JSON.stringify({
    account_id: row.account_id,
    principal_id: row.principal_id,
    control_revision: row.control_revision,
    destination_activation_epoch: row.destination_activation_epoch,
    destination_activation_revision: row.destination_activation_revision,
    control_content_hash: row.control_content_hash,
    credential_id: row.credential_id,
    credential_generation: row.credential_generation,
    credential_content_hash: row.credential_content_hash,
    grant_id: row.grant_id,
    grant_version: row.grant_version,
    grant_content_hash: row.grant_content_hash,
  })).digest("hex");

const safeDatabaseInteger = (value: unknown, nullable = false): number | null => {
  if (value === null && nullable) return null;
  if (typeof value !== "number" && typeof value !== "bigint" && typeof value !== "string") {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  const numeric = Number(value);
  if (!Number.isSafeInteger(numeric) || numeric < 0) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  return numeric;
};

const databaseString = (value: unknown): string => {
  if (typeof value !== "string" || value.length === 0) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  return value;
};

const nullableDatabaseString = (value: unknown): string | null =>
  value === null ? null : databaseString(value);

const normalizeAuthorityStateRow = (row: Record<string, unknown>): AuthorityStateRow => {
  const expectedKeys = [
    "account_id", "principal_id", "application_id", "credential_id",
    "credential_generation", "capability", "grant_id", "grant_version",
    "account_epoch", "control_conflict_reason", "control_conflict_at_revision",
    "destination_activation_epoch", "destination_activation_revision",
    "lifecycle_state", "deletion_epoch", "account_generation",
    "credential_lifecycle", "grant_lifecycle", "grant_enabled",
    "authentication_strength", "credential_expires_at_epoch_seconds",
    "control_revision", "control_content_hash", "credential_content_hash",
    "grant_content_hash", "db_now_epoch_seconds",
  ].sort();
  const actualKeys = Object.keys(row).sort();
  if (actualKeys.length !== expectedKeys.length
    || actualKeys.some((key, index) => key !== expectedKeys[index])) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  const lifecycleState = databaseString(row["lifecycle_state"]);
  const accountGeneration = databaseString(row["account_generation"]);
  const credentialLifecycle = databaseString(row["credential_lifecycle"]);
  const grantLifecycle = databaseString(row["grant_lifecycle"]);
  if (!["active", "deletion_pending", "deleted"].includes(lifecycleState)
    || !["legacy", "migrating", "new", "rolled_back_stranded"].includes(accountGeneration)
    || !["active", "inactive", "revoked"].includes(credentialLifecycle)
    || !["active", "inactive", "revoked"].includes(grantLifecycle)
    || typeof row["grant_enabled"] !== "boolean") {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  return Object.freeze({
    account_id: databaseString(row["account_id"]),
    principal_id: databaseString(row["principal_id"]),
    application_id: databaseString(row["application_id"]),
    credential_id: databaseString(row["credential_id"]),
    credential_generation: safeDatabaseInteger(row["credential_generation"])!,
    capability: databaseString(row["capability"]),
    grant_id: databaseString(row["grant_id"]),
    grant_version: safeDatabaseInteger(row["grant_version"])!,
    account_epoch: safeDatabaseInteger(row["account_epoch"], true),
    control_conflict_reason: nullableDatabaseString(row["control_conflict_reason"]),
    control_conflict_at_revision: safeDatabaseInteger(row["control_conflict_at_revision"], true),
    destination_activation_epoch: safeDatabaseInteger(row["destination_activation_epoch"], true),
    destination_activation_revision: safeDatabaseInteger(row["destination_activation_revision"], true),
    lifecycle_state: lifecycleState as AuthorityStateRow["lifecycle_state"],
    deletion_epoch: safeDatabaseInteger(row["deletion_epoch"], true),
    account_generation: accountGeneration as AuthorityStateRow["account_generation"],
    credential_lifecycle: credentialLifecycle as AuthorityStateRow["credential_lifecycle"],
    grant_lifecycle: grantLifecycle as AuthorityStateRow["grant_lifecycle"],
    grant_enabled: row["grant_enabled"],
    authentication_strength: databaseString(row["authentication_strength"]),
    credential_expires_at_epoch_seconds: safeDatabaseInteger(row["credential_expires_at_epoch_seconds"], true),
    control_revision: safeDatabaseInteger(row["control_revision"])!,
    control_content_hash: databaseString(row["control_content_hash"]),
    credential_content_hash: databaseString(row["credential_content_hash"]),
    grant_content_hash: databaseString(row["grant_content_hash"]),
    db_now_epoch_seconds: safeDatabaseInteger(row["db_now_epoch_seconds"])!,
  });
};

const assertAuthorityState = (
  context: AuthorizedLedgerWriteContext,
  row: AuthorityStateRow,
): void => {
  try {
    assertAuthorizedLedgerWriteContextCurrentAt(context, row.db_now_epoch_seconds);
  } catch {
    throw new PostgresRepositoryError("expired_context");
  }
  if (row.account_id !== context.account_id) throw new PostgresRepositoryError("authorization_state_denied");
  if (row.principal_id !== context.principal_id) throw new PostgresRepositoryError("credential_inactive");
  if (row.control_conflict_reason !== null || row.control_conflict_at_revision !== null) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
  if (row.account_epoch !== context.account_epoch) throw new PostgresRepositoryError("stale_epoch");
  if (row.lifecycle_state !== context.lifecycle_state || row.deletion_epoch !== context.deletion_epoch) {
    throw new PostgresRepositoryError("lifecycle_inactive");
  }
  if (row.account_generation !== "new"
    || row.destination_activation_epoch !== context.account_epoch
    || row.destination_activation_revision !== context.destination_activation_revision) {
    throw new PostgresRepositoryError("destination_inactive");
  }
  if (row.application_id !== context.application_id
    || row.credential_id !== context.credential_id
    || row.credential_generation !== context.credential_generation
    || row.credential_lifecycle !== "active"
    || row.authentication_strength !== context.authentication_strength
    || (row.credential_expires_at_epoch_seconds !== null
      && row.credential_expires_at_epoch_seconds <= row.db_now_epoch_seconds)) {
    throw new PostgresRepositoryError("credential_inactive");
  }
  if (row.capability !== context.capability) throw new PostgresRepositoryError("capability_denied");
  if (row.grant_id !== context.grant_id
    || row.grant_version !== context.grant_version
    || row.grant_lifecycle !== "active"
    || !row.grant_enabled) {
    throw new PostgresRepositoryError("grant_inactive");
  }
  if (authorizationStateDigest(row) !== context.authorization_state_digest) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
};

export interface AuthorizedPostgresTransaction {
  readonly authority: AuthorizedLedgerWriteContext;
  readonly dbNowEpochSeconds: number;
}

/**
 * Driver-internal transaction capability.  Service composition must receive
 * only the sealed repository port; SQL access never crosses the driver.
 *
 * @internal
 */
interface AuthorizedPostgresConnectionTransaction extends AuthorizedPostgresTransaction {
  readonly connection: CheckedOutPostgresConnection;
  readonly lockedControlRevision: number;
}

const providerCode = (error: unknown): string | undefined => {
  if (!error || typeof error !== "object") return undefined;
  const code = Reflect.get(error, "code");
  return typeof code === "string" ? code : undefined;
};

export const mapPostgresFailure = (error: unknown): PostgresRepositoryError => {
  if (error instanceof PostgresRepositoryError) return error;
  if (providerCode(error) === "40001") return new PostgresRepositoryError("retryable_serialization", true);
  return new PostgresRepositoryError("persistence_failed");
};

export interface PostgresTransactionObservability {
  readonly telemetry?: OperationalTelemetryEmitter;
  readonly nowMilliseconds?: () => number;
}

const safeNowMilliseconds = (clock: () => number): number | null => {
  try {
    const value = clock();
    return Number.isSafeInteger(value) && value >= 0 ? value : null;
  } catch {
    return null;
  }
};

const boundedDurationMilliseconds = (started: number | null, finished: number | null): number => {
  if (started === null || finished === null || finished < started) return 0;
  return Math.min(finished - started, 86_400_000);
};

const databaseOutcomeFor = (error: PostgresRepositoryError): DatabaseOutcome => {
  if (error.code === "retryable_serialization") return "serialization_retryable";
  if ([
    "authorization_state_denied",
    "expired_context",
    "stale_epoch",
    "destination_inactive",
    "lifecycle_inactive",
    "credential_inactive",
    "grant_inactive",
    "capability_denied",
  ].includes(error.code)) return "stale_authority";
  return "failure";
};

const emitTransactionTelemetry = (
  observability: PostgresTransactionObservability,
  outcome: DatabaseOutcome,
  started: number | null,
): void => {
  try {
    const finished = safeNowMilliseconds(observability.nowMilliseconds ?? Date.now);
    observability.telemetry?.emit({
      version: "operational-telemetry-v1",
      family: "database",
      stage: "transaction",
      outcome,
      duration_ms: boundedDurationMilliseconds(started, finished),
      pool: null,
    });
  } catch {
    // Operational telemetry is observational and must never alter persistence.
  }
};

/** @internal Shared implementation for PostgreSQL repositories in this driver. */
export const withAuthorizedSerializableConnectionTransaction = async <Result>(
  pool: PostgresTransactionPool,
  suppliedContext: AuthorizedLedgerWriteContext,
  callback: (transaction: AuthorizedPostgresConnectionTransaction) => Promise<Result>,
  observability: PostgresTransactionObservability = {},
): Promise<Result> => {
  const started = safeNowMilliseconds(observability.nowMilliseconds ?? Date.now);
  try {
    const context = assertAuthorizedLedgerWriteContext(suppliedContext);
    const result = await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        await connection.query({
          name: "authority.set_local",
          text: SET_LOCAL_AUTHORITY_CONTEXT,
          values: [
            context.account_id,
            context.principal_id,
            context.grant_id,
            context.account_epoch,
            context.lifecycle_state,
            context.capability,
          ],
        });
        const rows = await connection.query<AuthorityStateRow>({
          name: "authority.lock_and_revalidate",
          text: LOCK_AUTHORITY_STATE,
          values: [
            context.account_id,
            context.principal_id,
            context.application_id,
            context.credential_id,
            context.credential_generation,
            context.capability,
            context.grant_id,
          ],
        });
        const rawRow = rows[0];
        if (rows.length !== 1 || !rawRow) {
          throw new PostgresRepositoryError("authorization_state_denied");
        }
        const row = normalizeAuthorityStateRow(rawRow);
        assertAuthorityState(context, row);
        const transaction: AuthorizedPostgresConnectionTransaction = Object.freeze({
          authority: context,
          dbNowEpochSeconds: row.db_now_epoch_seconds,
          lockedControlRevision: row.control_revision,
          connection,
        });
        return callback(transaction);
      },
    );
    emitTransactionTelemetry(observability, "success", started);
    return result;
  } catch (error) {
    const mapped = mapPostgresFailure(error);
    emitTransactionTelemetry(observability, databaseOutcomeFor(mapped), started);
    throw mapped;
  }
};

/**
 * Metadata-only public transaction boundary retained for callers that must
 * never receive a SQL capability.
 */
export const withAuthorizedSerializableTransaction = async <Result>(
  pool: PostgresTransactionPool,
  suppliedContext: AuthorizedLedgerWriteContext,
  callback: (transaction: AuthorizedPostgresTransaction) => Promise<Result>,
  observability: PostgresTransactionObservability = {},
): Promise<Result> => withAuthorizedSerializableConnectionTransaction(
  pool,
  suppliedContext,
  ({ authority, dbNowEpochSeconds }) => callback(Object.freeze({ authority, dbNowEpochSeconds })),
  observability,
);
