/**
 * Dependency-free PostgreSQL driver boundary.
 *
 * A future Bun.SQL or Postgres.js integration implements this small port.  The
 * authority repository never receives a pool-wide query function: every SQL
 * operation is made through the one connection supplied to the serializable
 * transaction callback.
 */

export type SqlValue = string | number | boolean | bigint | null | Uint8Array;

export interface SqlStatement {
  readonly name: string;
  readonly text: string;
  readonly values: readonly SqlValue[];
}

export interface SqlMutationResult {
  readonly rowCount: number;
}

export interface CheckedOutPostgresConnection {
  /** Opaque identity used by tests/adapters to prove one-client execution. */
  readonly connectionIdentity: object;
  query<Row extends Record<string, unknown>>(statement: SqlStatement): Promise<readonly Row[]>;
  execute(statement: SqlStatement): Promise<SqlMutationResult>;
}

export interface SerializableTransactionOptions {
  readonly isolationLevel: "serializable";
  readonly accessMode: "read write" | "read only";
  /** Optional request cancellation; adapters must roll back before reuse. */
  readonly signal?: AbortSignal;
}

export interface PostgresTransactionPool {
  /**
   * The implementation must BEGIN/COMMIT/ROLLBACK on one checked-out client,
   * discard an unsafe client after cancellation/connection failure, and never
   * return it with transaction-local settings visible.  Fake tests exercise
   * the callback contract; only the later real-PostgreSQL gate can prove pool
   * reset, cancellation, and backend termination behavior.
   */
  withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result>;
}

export type PostgresSessionAdvisoryLockOutcome<Result> =
  | Readonly<{ acquired: false }>
  | Readonly<{ acquired: true; value: Result }>;

/**
 * Session-scoped coordination for work that must not hold a database
 * transaction open (notably a provider model call). The callback receives no
 * SQL capability. Implementations must release the exact lock and reserved
 * connection only after the callback settles; a lost connection must never be
 * returned to the pool.
 */
export interface PostgresSessionAdvisoryLockPool {
  tryWithSessionAdvisoryLock<Result>(
    key: readonly [number, number],
    callback: () => Promise<Result>,
  ): Promise<PostgresSessionAdvisoryLockOutcome<Result>>;
}

export const REAL_POSTGRES_ACTIVATION = Object.freeze({
  supported: false as const,
  reasonCode: "postgres_runtime_not_qualified" as const,
});

export class UnsupportedPostgresRuntimeError extends Error {
  readonly code = "postgres_runtime_not_qualified" as const;
  constructor() {
    super("PostgreSQL runtime is not qualified");
    this.name = "UnsupportedPostgresRuntimeError";
  }
}

/** Explicit gate for later canonical service composition. */
export const requireRatifiedPostgresRuntime = (): never => {
  throw new UnsupportedPostgresRuntimeError();
};
