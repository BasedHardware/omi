import postgres, { type ReservedSql, type Sql } from "postgres";

import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
  SqlMutationResult,
  SqlStatement,
  SqlValue,
} from "./connection";

export const POSTGRES_JS_VERSION = "3.4.9" as const;

export interface PostgresJsPoolOptions {
  /** Explicit by design: the adapter never reads DATABASE_URL or another ambient URL. */
  readonly connectionString: string;
  readonly maxConnections?: number;
  readonly idleTimeoutSeconds?: number;
  readonly connectTimeoutSeconds?: number;
}

export interface CloseablePostgresTransactionPool extends PostgresTransactionPool {
  close(): Promise<void>;
}

interface PostgresJsBindingOptions {
  /** Qualified only for a size-one pool, where every close belongs to this lease. */
  readonly leaseGeneration?: () => number;
}

const boundedInteger = (
  value: number | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number => value === undefined
  ? fallback
  : Number.isSafeInteger(value) && value >= minimum && value <= maximum
    ? value
    : (() => { throw new TypeError("invalid_postgres_pool_option"); })();

const parameter = (value: SqlValue): string | number | boolean | null | Buffer =>
  typeof value === "bigint" ? value.toString(10)
    : value instanceof Uint8Array ? Buffer.from(value) : value;

class PostgresJsCheckedOutConnection implements CheckedOutPostgresConnection {
  constructor(
    readonly connectionIdentity: object,
    private readonly sql: ReservedSql<Record<string, never>>,
    private readonly assertLeaseHealthy: () => void,
  ) {}

  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    this.assertLeaseHealthy();
    const rows = await this.sql.unsafe<Row[]>(
      statement.text,
      statement.values.map(parameter),
      { prepare: true },
    );
    return Object.freeze([...rows]);
  }

  async execute(statement: SqlStatement): Promise<SqlMutationResult> {
    this.assertLeaseHealthy();
    const result = await this.sql.unsafe(
      statement.text,
      statement.values.map(parameter),
      { prepare: true },
    );
    return Object.freeze({ rowCount: result.count });
  }
}

const providerCode = (error: unknown): string | undefined => {
  if (!error || typeof error !== "object") return undefined;
  const code = Reflect.get(error, "code");
  return typeof code === "string" ? code : undefined;
};

const destroysConnectionLease = (error: unknown): boolean => [
  "57P01", // admin_shutdown / pg_terminate_backend
  "57P02", // crash_shutdown
  "57P03", // cannot_connect_now during shutdown/recovery
  "08000", "08003", "08006", "08001", "08004", "08007", "08P01",
  "CONNECTION_CLOSED", "CONNECTION_DESTROYED", "CONNECT_TIMEOUT",
].includes(providerCode(error) ?? "");

class PostgresJsLeaseLostError extends Error {
  readonly code = "CONNECTION_DESTROYED" as const;
  constructor() {
    super("postgres_connection_lease_lost");
    this.name = "PostgresJsLeaseLostError";
  }
}

/**
 * Binds the existing driver-neutral transaction port to Postgres.js.
 * The adapter reserves one physical lease and owns BEGIN/COMMIT/ROLLBACK itself.
 * This is intentionally more explicit than Postgres.js `begin()`: after a backend
 * termination, `begin()` attempts a rollback on the dead socket. Under Bun that can
 * surface as a deferred socket write and poison a size-one pool. A destroyed lease is
 * never released back to the open queue; Postgres.js reconnects its closed slot for
 * the next reservation.
 */
export const bindPostgresJsTransactionPool = (
  sql: Sql<Record<string, never>>,
  binding: PostgresJsBindingOptions = {},
): CloseablePostgresTransactionPool => Object.freeze({
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    if (options.isolationLevel !== "serializable" || options.accessMode !== "read write") {
      throw new TypeError("invalid_postgres_transaction_options");
    }
    const reserved = await sql.reserve();
    const leaseGeneration = binding.leaseGeneration?.();
    const assertLeaseHealthy = (): void => {
      if (leaseGeneration !== undefined && binding.leaseGeneration?.() !== leaseGeneration) {
        throw new PostgresJsLeaseLostError();
      }
    };
    const identity = Object.freeze({ lease: Symbol("postgresjs-reserved-connection") });
    let leaseDestroyed = false;
    try {
      await reserved.unsafe("begin isolation level serializable read write");
      try {
        const value = await callback(new PostgresJsCheckedOutConnection(
          identity,
          reserved,
          assertLeaseHealthy,
        ));
        assertLeaseHealthy();
        await reserved.unsafe("commit");
        return value;
      } catch (error) {
        leaseDestroyed = destroysConnectionLease(error);
        if (!leaseDestroyed) {
          try {
            await reserved.unsafe("rollback");
          } catch (rollbackError) {
            leaseDestroyed = destroysConnectionLease(rollbackError);
          }
        }
        throw error;
      }
    } catch (error) {
      leaseDestroyed ||= destroysConnectionLease(error);
      throw error;
    } finally {
      if (!leaseDestroyed) reserved.release();
    }
  },
  async close(): Promise<void> {
    await sql.end({ timeout: 5 });
  },
});

export const createPostgresJsTransactionPool = (
  options: PostgresJsPoolOptions,
): CloseablePostgresTransactionPool => {
  if (typeof options.connectionString !== "string" || options.connectionString.length === 0) {
    throw new TypeError("invalid_postgres_connection_string");
  }
  const maxConnections = boundedInteger(options.maxConnections, 10, 1, 100);
  let leaseGeneration = 0;
  const sql = postgres(options.connectionString, {
    max: maxConnections,
    idle_timeout: boundedInteger(options.idleTimeoutSeconds, 20, 1, 600),
    connect_timeout: boundedInteger(options.connectTimeoutSeconds, 10, 1, 60),
    prepare: true,
    onclose: () => { leaseGeneration += 1; },
  });
  return bindPostgresJsTransactionPool(
    sql,
    maxConnections === 1 ? { leaseGeneration: () => leaseGeneration } : {},
  );
};
