import postgres, { type ReservedSql, type Sql } from "postgres";

import type {
  CheckedOutPostgresConnection,
  PostgresSessionAdvisoryLockPool,
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

export interface CloseablePostgresTransactionPool extends PostgresTransactionPool,
  PostgresSessionAdvisoryLockPool {
  close(): Promise<void>;
}

interface PostgresJsBindingOptions {
  /** Qualified only for a size-one pool, where every close belongs to this lease. */
  readonly leaseGeneration?: () => number;
}

interface CancellableQuery<Rows> extends PromiseLike<Rows> {
  cancel(): void;
}

type TrackQuery = <Rows>(query: CancellableQuery<Rows>) => Promise<Rows>;

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
    private readonly trackQuery: TrackQuery,
  ) {}

  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    this.assertLeaseHealthy();
    const rows = await this.trackQuery(this.sql.unsafe<Row[]>(
      statement.text,
      statement.values.map(parameter),
      { prepare: true },
    ));
    return Object.freeze([...rows]);
  }

  async execute(statement: SqlStatement): Promise<SqlMutationResult> {
    this.assertLeaseHealthy();
    const result = await this.trackQuery(this.sql.unsafe(
      statement.text,
      statement.values.map(parameter),
      { prepare: true },
    ));
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
  async tryWithSessionAdvisoryLock<Result>(
    key: readonly [number, number],
    callback: () => Promise<Result>,
  ) {
    if (!Array.isArray(key) || key.length !== 2
      || key.some((part) => !Number.isSafeInteger(part) || part < -2147483648 || part > 2147483647)
      || typeof callback !== "function") {
      throw new TypeError("invalid_postgres_session_lock_request");
    }
    const reserved = await sql.reserve();
    const leaseGeneration = binding.leaseGeneration?.();
    const assertLeaseHealthy = (): void => {
      if (leaseGeneration !== undefined && binding.leaseGeneration?.() !== leaseGeneration) {
        throw new PostgresJsLeaseLostError();
      }
    };
    let leaseDestroyed = false;
    let acquired = false;
    try {
      assertLeaseHealthy();
      const rows = await reserved.unsafe<{ acquired: boolean }[]>(
        "select pg_try_advisory_lock($1::integer, $2::integer) as acquired",
        [key[0], key[1]],
        { prepare: true },
      );
      assertLeaseHealthy();
      acquired = rows.length === 1 && rows[0]?.acquired === true;
      if (!acquired) return Object.freeze({ acquired: false as const });
      const value = await callback();
      assertLeaseHealthy();
      return Object.freeze({ acquired: true as const, value });
    } catch (error) {
      leaseDestroyed = destroysConnectionLease(error);
      throw error;
    } finally {
      if (acquired && !leaseDestroyed) {
        try {
          const rows = await reserved.unsafe<{ unlocked: boolean }[]>(
            "select pg_advisory_unlock($1::integer, $2::integer) as unlocked",
            [key[0], key[1]],
            { prepare: true },
          );
          assertLeaseHealthy();
          if (rows.length !== 1 || rows[0]?.unlocked !== true) leaseDestroyed = true;
        } catch {
          // Unlock failure makes the session lock state unknowable. Quarantine
          // the reserved connection instead of returning it to the pool.
          leaseDestroyed = true;
        }
      }
      if (!leaseDestroyed) reserved.release();
    }
  },
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    if (options.isolationLevel !== "serializable"
      || (options.accessMode !== "read write" && options.accessMode !== "read only")) {
      throw new TypeError("invalid_postgres_transaction_options");
    }
    if (options.signal !== undefined && !(options.signal instanceof AbortSignal)) {
      throw new TypeError("invalid_postgres_transaction_signal");
    }
    if (options.signal?.aborted) throw options.signal.reason;
    const reserved = await sql.reserve();
    const leaseGeneration = binding.leaseGeneration?.();
    const assertLeaseHealthy = (): void => {
      if (leaseGeneration !== undefined && binding.leaseGeneration?.() !== leaseGeneration) {
        throw new PostgresJsLeaseLostError();
      }
    };
    const identity = Object.freeze({ lease: Symbol("postgresjs-reserved-connection") });
    let leaseDestroyed = false;
    let activeQuery: { cancel(): void } | null = null;
    const abort = (): void => { activeQuery?.cancel(); };
    options.signal?.addEventListener("abort", abort, { once: true });
    const run = async <Rows>(
      query: CancellableQuery<Rows>,
    ): Promise<Rows> => {
      activeQuery = query;
      try { return await query; }
      finally { if (activeQuery === query) activeQuery = null; }
    };
    try {
      await run(reserved.unsafe(
        `begin isolation level serializable ${options.accessMode}`,
      ));
      try {
        const value = await callback(new PostgresJsCheckedOutConnection(
          identity,
          reserved,
          assertLeaseHealthy,
          run,
        ));
        assertLeaseHealthy();
        if (options.signal?.aborted) throw options.signal.reason;
        await run(reserved.unsafe("commit"));
        return value;
      } catch (error) {
        leaseDestroyed = destroysConnectionLease(error);
        if (!leaseDestroyed) {
          try {
            await run(reserved.unsafe("rollback"));
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
      options.signal?.removeEventListener("abort", abort);
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
