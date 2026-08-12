import { readFileSync } from "node:fs";

import { describe, expect, test } from "bun:test";
import type { ReservedSql, Sql } from "postgres";

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

  test("starts one serializable transaction on the callback-scoped connection", async () => {
    const calls: string[] = [];
    const reserved = {
      unsafe: async (text: string) => {
        calls.push(text);
        const rows = [{ backend_pid: 42 }];
        Object.defineProperty(rows, "count", { value: 1 });
        return rows;
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
      "begin isolation level serializable read write",
      "select pg_backend_pid() as backend_pid",
      "update example set value = $1",
      "commit",
      "release",
    ]);
    await pool.close();
    expect(calls.at(-1)).toBe("end");
  });

  test("propagates transaction callback failure and rejects ambient construction", async () => {
    const calls: string[] = [];
    const reserved = {
      unsafe: async (text: string) => { calls.push(text); return []; },
      release: () => { calls.push("release"); },
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
    expect(calls).toEqual([
      "begin isolation level serializable read write",
      "rollback",
      "release",
    ]);
    expect(() => createPostgresJsTransactionPool({ connectionString: "" }))
      .toThrow("invalid_postgres_connection_string");
  });

  test("does not release a terminated lease and uses the next reservation", async () => {
    const released: string[] = [];
    const terminated = Object.assign(new Error("provider body must remain opaque"), { code: "57P01" });
    const first = {
      unsafe: async (text: string) => {
        if (text === "select 1") throw terminated;
        return [];
      },
      release: () => { released.push("first"); },
    } as unknown as ReservedSql<Record<string, never>>;
    const second = {
      unsafe: async () => [],
      release: () => { released.push("second"); },
    } as unknown as ReservedSql<Record<string, never>>;
    const reservations = [first, second];
    const sql = {
      reserve: async () => reservations.shift()!,
      end: async () => undefined,
    } as unknown as Sql<Record<string, never>>;
    const pool = bindPostgresJsTransactionPool(sql);

    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      (connection) => connection.query({ name: "test.terminated", text: "select 1", values: [] }),
    )).rejects.toMatchObject({ code: "57P01" });
    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async () => "recovered",
    )).resolves.toBe("recovered");
    expect(released).toEqual(["second"]);
  });

  test("refuses commit when a size-one lease closes at the pre-commit checkpoint", async () => {
    let generation = 0;
    const calls: string[] = [];
    const reservations = ["first", "second"].map((name) => ({
      unsafe: async (text: string) => { calls.push(`${name}:${text}`); return []; },
      release: () => { calls.push(`${name}:release`); },
    } as unknown as ReservedSql<Record<string, never>>));
    const sql = {
      reserve: async () => reservations.shift()!,
      end: async () => undefined,
    } as unknown as Sql<Record<string, never>>;
    const pool = bindPostgresJsTransactionPool(sql, { leaseGeneration: () => generation });

    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async () => { generation += 1; },
    )).rejects.toMatchObject({ code: "CONNECTION_DESTROYED" });
    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async () => "reconnected",
    )).resolves.toBe("reconnected");
    expect(calls).toEqual([
      "first:begin isolation level serializable read write",
      "second:begin isolation level serializable read write",
      "second:commit",
      "second:release",
    ]);
  });
});
