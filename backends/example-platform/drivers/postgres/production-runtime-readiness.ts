import { isProxy } from "node:util/types";

import type { CheckedOutPostgresConnection, PostgresTransactionPool } from "./connection";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";

export interface PostgresProductionRuntimeReadiness {
  readonly check: () => Promise<boolean>;
}

interface ReadinessRow extends Record<string, unknown> {
  readonly server_version_num: unknown;
  readonly database_generation_released: unknown;
  readonly migration_version: unknown;
  readonly migration_name: unknown;
  readonly migration_sha256: unknown;
}

interface ReadinessBinding {
  readonly pool: PostgresTransactionPool;
  readonly expectedDatabaseGenerationDigest: string;
  readonly check: () => Promise<boolean>;
}

const BINDINGS = new WeakMap<object, ReadinessBinding>();
const DIGEST = /^[0-9a-f]{64}$/;
const ROW_KEYS = Object.freeze([
  "server_version_num",
  "database_generation_released",
  "migration_version",
  "migration_name",
  "migration_sha256",
] as const);

const fail = (): never => { throw new TypeError("invalid PostgreSQL production readiness options"); };

const dataMethod = <Result>(value: object, key: PropertyKey): ((...args: never[]) => Result) => {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (!descriptor || !("value" in descriptor) || typeof descriptor.value !== "function"
    || isProxy(descriptor.value)) fail();
  return (descriptor as PropertyDescriptor & { value: (...args: never[]) => Result }).value;
};

const exactRow = (value: unknown): ReadinessRow => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== ROW_KEYS.length
    || ROW_KEYS.some((key) => !Object.hasOwn(descriptors, key))) fail();
  const row: Record<string, unknown> = {};
  for (const key of ROW_KEYS) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail();
    row[key] = descriptor.value;
  }
  return row as ReadinessRow;
};

const safePositiveInteger = (value: unknown): number | null => {
  if (typeof value === "number") {
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  }
  if (typeof value !== "string" || !/^[1-9][0-9]*$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
};

const inspect = async (
  connection: CheckedOutPostgresConnection,
  expectedDatabaseGenerationDigest: string,
): Promise<boolean> => {
  const rows = await connection.query<ReadinessRow>({
    name: "production_runtime_readiness.inspect",
    text: "SELECT * FROM omi_memory.inspect_production_runtime_readiness($1)",
    values: [expectedDatabaseGenerationDigest],
  });
  if (!Array.isArray(rows) || rows.length !== POSTGRES_MIGRATIONS.length) return false;
  for (let index = 0; index < rows.length; index += 1) {
    const row = exactRow(rows[index]);
    const expected = POSTGRES_MIGRATIONS[index];
    if (row.server_version_num !== "180004"
      || row.database_generation_released !== true
      || safePositiveInteger(row.migration_version) !== expected?.version
      || row.migration_name !== expected.name
      || row.migration_sha256 !== expected.sha256) return false;
  }
  return true;
};

export const createPostgresProductionRuntimeReadiness = (
  pool: PostgresTransactionPool,
  expectedDatabaseGenerationDigest: string,
): PostgresProductionRuntimeReadiness => {
  if (pool === null || typeof pool !== "object" || isProxy(pool)
    || !DIGEST.test(expectedDatabaseGenerationDigest)) fail();
  const withTransaction = dataMethod<Promise<boolean>>(pool, "withTransaction").bind(pool) as
    PostgresTransactionPool["withTransaction"];
  const check = async (): Promise<boolean> => {
    try {
      return await withTransaction(
        { isolationLevel: "serializable", accessMode: "read only" },
        (connection) => inspect(connection, expectedDatabaseGenerationDigest),
      );
    } catch {
      return false;
    }
  };
  const readiness = Object.freeze({ check });
  BINDINGS.set(readiness, Object.freeze({
    pool,
    expectedDatabaseGenerationDigest,
    check,
  }));
  return readiness;
};

/** @internal Production-process construction fence; does not mint readiness. */
export const bindPostgresProductionRuntimeReadiness = (
  value: unknown,
  expectedPool: PostgresTransactionPool,
  expectedDatabaseGenerationDigest: string,
): (() => Promise<boolean>) => {
  if (value === null || typeof value !== "object" || isProxy(value)) fail();
  const bindingValue = BINDINGS.get(value as object);
  if (bindingValue === undefined) return fail();
  const binding: ReadinessBinding = bindingValue;
  if (binding.pool !== expectedPool
    || binding.expectedDatabaseGenerationDigest !== expectedDatabaseGenerationDigest) fail();
  return binding.check;
};
