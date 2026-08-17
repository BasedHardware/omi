import { createHash } from "node:crypto";

import { expect, test } from "bun:test";

import { PostgresMigrationError, runPostgresMigrations } from "./runner";

test("migration bytes are checked before any PostgreSQL call", async () => {
  let calls = 0;
  const sql = {
    unsafe: async () => { calls += 1; return []; },
  } as never;
  await expect(runPostgresMigrations(sql, {
    manifest: [{ version: 1, name: "one", fileName: "0001-one.sql", sha256: "0".repeat(64) }],
    readBytes: () => new TextEncoder().encode("SELECT 1"),
  })).rejects.toEqual(new PostgresMigrationError("postgres_migration_checksum_mismatch"));
  expect(calls).toBe(0);
});

test("unsupported PostgreSQL major is refused before a transaction begins", async () => {
  let transactions = 0;
  const sql = {
    unsafe: async () => [{ server_version_num: "170009" }],
    begin: async () => { transactions += 1; },
  } as never;
  const bytes = new TextEncoder().encode("SELECT 1");
  await expect(runPostgresMigrations(sql, {
    manifest: [{
      version: 1,
      name: "one",
      fileName: "0001-one.sql",
      sha256: createHash("sha256").update(bytes).digest("hex"),
    }],
    readBytes: () => bytes,
  })).rejects.toEqual(new PostgresMigrationError("unsupported_postgres_server_version"));
  expect(transactions).toBe(0);
});
