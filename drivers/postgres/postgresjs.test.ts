import { readFileSync } from "node:fs";

import { describe, expect, test } from "bun:test";
import type { ReservedSql, Sql, TransactionSql } from "postgres";

import { REAL_POSTGRES_ACTIVATION, type CheckedOutPostgresConnection } from "./connection";
import {
  POSTGRES_JS_VERSION,
  bindPostgresJsTransactionPool,
  createPostgresJsTransactionPool,
} from "./postgresjs";

describe("Postgres.js transaction adapter", () => {
  test("pins the approved client version and registry integrity", () => {
    const packageJson = JSON.parse(readFileSync(
      new URL("./node_modules/postgres/package.json", import.meta.url), "utf8",
    )) as { version?: unknown };
    const lock = readFileSync(new URL("../../bun.lock", import.meta.url), "utf8");
    expect(packageJson.version).toBe(POSTGRES_JS_VERSION);
    expect(lock).toContain('"postgres": ["postgres@3.4.9"');
    expect(lock).toContain("sha512-GD3qdB0x1z9xgFI6cdRD6xu2Sp2WCOEoe3mtnyB5Ee0XrrL5Pe+e4CCnJrRMnL1zYtRDZmQQVbvOttLnKDLnaw==");
    expect(REAL_POSTGRES_ACTIVATION).toEqual({
      supported: false,
      reasonCode: "postgres_runtime_not_qualified",
    });
  });

  test("reserves one connection, starts one serializable transaction, and always releases", async () => {
    const calls: string[] = [];
    const transaction = {
      unsafe: async (text: string) => {
        calls.push(text);
        const rows = [{ backend_pid: 42 }];
        Object.defineProperty(rows, "count", { value: 1 });
        return rows;
      },
    } as unknown as TransactionSql<Record<string, never>>;
    const reserved = {
      begin: async (options: string, callback: (sql: TransactionSql<Record<string, never>>) => Promise<unknown>) => {
        calls.push(options);
        return callback(transaction);
      },
      release: () => { calls.push("release"); },
    } as unknown as ReservedSql<Record<string, never>>;
    const sql = {
      reserve: async () => reserved,
      end: async () => { calls.push("end"); },
    } as unknown as Sql<Record<string, never>>;
    const pool = bindPostgresJsTransactionPool(sql);
    let seen: object | undefined;

    const result = await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        seen = connection.connectionIdentity;
        expect(await connection.query<{ backend_pid: number }>({
          name: "test.backend_pid", text: "select pg_backend_pid() as backend_pid", values: [],
        })).toEqual([{ backend_pid: 42 }]);
        expect(await connection.execute({
          name: "test.update", text: "update example set value = $1", values: [new Uint8Array([1])],
        })).toEqual({ rowCount: 1 });
        return "committed";
      },
    );

    expect(result).toBe("committed");
    expect(seen).toBeDefined();
    expect(calls).toEqual([
      "isolation level serializable read write",
      "select pg_backend_pid() as backend_pid",
      "update example set value = $1",
      "release",
    ]);
    await pool.close();
    expect(calls.at(-1)).toBe("end");
  });

  test("releases the reserved connection after callback failure and rejects ambient construction", async () => {
    let releases = 0;
    const reserved = {
      begin: async (_options: string, callback: (sql: TransactionSql<Record<string, never>>) => Promise<unknown>) =>
        callback({} as TransactionSql<Record<string, never>>),
      release: () => { releases += 1; },
    } as unknown as ReservedSql<Record<string, never>>;
    const sql = {
      reserve: async () => reserved,
      end: async () => undefined,
    } as unknown as Sql<Record<string, never>>;
    const pool = bindPostgresJsTransactionPool(sql);

    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async () => { throw new Error("callback failed"); },
    )).rejects.toThrow("callback failed");
    expect(releases).toBe(1);
    expect(() => createPostgresJsTransactionPool({ connectionString: "" }))
      .toThrow("invalid_postgres_connection_string");
  });
});
