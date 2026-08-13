import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool, SqlStatement } from "./connection";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import type { CloseablePostgresTransactionPool } from "./postgresjs";
import {
  bindPostgresProductionRuntimeReadiness,
  createPostgresProductionRuntimeReadiness,
} from "./production-runtime-readiness";

type Row = Record<string, unknown>;

const rows = (): Row[] => POSTGRES_MIGRATIONS.map((migration) => ({
  server_version_num: "180004",
  database_generation_released: true,
  migration_version: String(migration.version),
  migration_name: migration.name,
  migration_sha256: migration.sha256,
}));

const fixture = (load: () => Promise<readonly Row[]> = async () => rows()) => {
  const transactions: unknown[] = [];
  const statements: SqlStatement[] = [];
  const identity = Object.freeze({ pool: "readiness" });
  const pool: CloseablePostgresTransactionPool = Object.freeze({
    async withTransaction<Result>(options: Parameters<PostgresTransactionPool["withTransaction"]>[0], callback: (
      connection: Parameters<Parameters<PostgresTransactionPool["withTransaction"]>[1]>[0],
    ) => Promise<Result>): Promise<Result> {
      transactions.push(options);
      return callback({
        connectionIdentity: identity,
        query: async <Value extends Row>(statement: SqlStatement) => {
          statements.push(statement);
          return await load() as readonly Value[];
        },
        execute: async () => { throw new Error("readiness_is_read_only"); },
      });
    },
    tryWithSessionAdvisoryLock: async () => { throw new Error("not_used"); },
    close: async () => undefined,
  });
  return { pool, transactions, statements };
};

describe("PostgreSQL production runtime readiness", () => {
  test("accepts only the exact server, released generation, and complete compiled manifest", async () => {
    const value = fixture();
    const readiness = createPostgresProductionRuntimeReadiness(value.pool, "d".repeat(64));
    await expect(readiness.check()).resolves.toBe(true);
    expect(value.transactions).toEqual([{ isolationLevel: "serializable", accessMode: "read only" }]);
    expect(value.statements).toEqual([{
      name: "production_runtime_readiness.inspect",
      text: "SELECT * FROM omi_memory.inspect_production_runtime_readiness($1)",
      values: ["d".repeat(64)],
    }]);
    expect(bindPostgresProductionRuntimeReadiness(
      readiness, value.pool, "d".repeat(64),
    )).toBe(readiness.check);
  });

  test("fails closed for every server, release, and migration-history mismatch", async () => {
    const variants: Row[][] = [];
    const wrongServer = rows(); wrongServer[0]!.server_version_num = "180005"; variants.push(wrongServer);
    const unreleased = rows(); unreleased[0]!.database_generation_released = false; variants.push(unreleased);
    variants.push(rows().slice(1));
    const extra = rows(); extra.push({ ...extra.at(-1)!, migration_version: "36" }); variants.push(extra);
    const changedName = rows(); changedName[1]!.migration_name = "changed"; variants.push(changedName);
    const changedHash = rows(); changedHash[1]!.migration_sha256 = "f".repeat(64); variants.push(changedHash);
    const reordered = rows(); [reordered[0], reordered[1]] = [reordered[1]!, reordered[0]!]; variants.push(reordered);
    const duplicate = rows(); duplicate[1] = { ...duplicate[0]! }; variants.push(duplicate);

    for (const candidate of variants) {
      const value = fixture(async () => candidate);
      await expect(createPostgresProductionRuntimeReadiness(
        value.pool, "d".repeat(64),
      ).check()).resolves.toBe(false);
    }
  });

  test("contains provider failures and rejects hostile result rows without invoking accessors", async () => {
    const failed = fixture(async () => { throw new Error("private provider body"); });
    await expect(createPostgresProductionRuntimeReadiness(
      failed.pool, "d".repeat(64),
    ).check()).resolves.toBe(false);

    let getterCalls = 0;
    const hostile = rows();
    hostile[0] = Object.defineProperty({ ...hostile[0] }, "migration_name", {
      enumerable: true,
      get() { getterCalls += 1; return POSTGRES_MIGRATIONS[0]!.name; },
    });
    const hostileFixture = fixture(async () => hostile);
    await expect(createPostgresProductionRuntimeReadiness(
      hostileFixture.pool, "d".repeat(64),
    ).check()).resolves.toBe(false);
    expect(getterCalls).toBe(0);

    const proxied = rows(); proxied[0] = new Proxy(proxied[0]!, {});
    const proxyFixture = fixture(async () => proxied);
    await expect(createPostgresProductionRuntimeReadiness(
      proxyFixture.pool, "d".repeat(64),
    ).check()).resolves.toBe(false);
  });

  test("rejects invalid generation coordinates, forged ports, and foreign serving pools", () => {
    const first = fixture();
    const second = fixture();
    expect(() => createPostgresProductionRuntimeReadiness(first.pool, "not-a-digest")).toThrow();
    const readiness = createPostgresProductionRuntimeReadiness(first.pool, "d".repeat(64));
    expect(() => bindPostgresProductionRuntimeReadiness(
      readiness, second.pool, "d".repeat(64),
    )).toThrow();
    expect(() => bindPostgresProductionRuntimeReadiness(
      readiness, first.pool, "e".repeat(64),
    )).toThrow();
    expect(() => bindPostgresProductionRuntimeReadiness(
      { check: async () => true }, first.pool, "d".repeat(64),
    )).toThrow();
    expect(() => bindPostgresProductionRuntimeReadiness(
      new Proxy(readiness, {}), first.pool, "d".repeat(64),
    )).toThrow();
  });
});
