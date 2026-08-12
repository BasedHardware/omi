import postgres, { type Sql, type TransactionSql } from "postgres";

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
    private readonly sql: TransactionSql<Record<string, never>>,
  ) {}

  async query<Row extends Record<string, unknown>>(
    statement: SqlStatement,
  ): Promise<readonly Row[]> {
    const rows = await this.sql.unsafe<Row[]>(
      statement.text,
      statement.values.map(parameter),
      { prepare: true },
    );
    return Object.freeze([...rows]);
  }

  async execute(statement: SqlStatement): Promise<SqlMutationResult> {
    const result = await this.sql.unsafe(
      statement.text,
      statement.values.map(parameter),
      { prepare: true },
    );
    return Object.freeze({ rowCount: result.count });
  }
}

/**
 * Binds the existing driver-neutral transaction port to Postgres.js.
 * `reserve()` supplies one physical pool lease; `begin()` scopes SET LOCAL and
 * rollback/commit to that exact lease. No transaction SQL escapes the callback.
 */
export const bindPostgresJsTransactionPool = (
  sql: Sql<Record<string, never>>,
): CloseablePostgresTransactionPool => Object.freeze({
  async withTransaction<Result>(
    options: SerializableTransactionOptions,
    callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
  ): Promise<Result> {
    if (options.isolationLevel !== "serializable" || options.accessMode !== "read write") {
      throw new TypeError("invalid_postgres_transaction_options");
    }
    const reserved = await sql.reserve();
    const identity = Object.freeze({ lease: Symbol("postgresjs-reserved-connection") });
    try {
      const wrapped = await reserved.begin("isolation level serializable read write", async (transaction) => ({
        value: await callback(new PostgresJsCheckedOutConnection(identity, transaction)),
      }));
      return wrapped.value;
    } finally {
      reserved.release();
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
  const sql = postgres(options.connectionString, {
    max: boundedInteger(options.maxConnections, 10, 1, 100),
    idle_timeout: boundedInteger(options.idleTimeoutSeconds, 20, 1, 600),
    connect_timeout: boundedInteger(options.connectTimeoutSeconds, 10, 1, 60),
    prepare: true,
  });
  return bindPostgresJsTransactionPool(sql);
};
