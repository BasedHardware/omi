import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import postgres, { type Sql } from "postgres";

import type { CheckedOutPostgresConnection } from "./connection";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;

realTest("PostgreSQL 18.4 real adapter qualification scaffold", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(() => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    const parsed = new URL(explicitTestUrl);
    if (parsed.hostname !== "127.0.0.1" || parsed.protocol !== "postgres:") {
      throw new Error("postgres_test_not_loopback_only");
    }
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
  });

  afterAll(async () => {
    await pool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("runs the pinned server, creates only the test role, and reapplies all migrations as no-ops", async () => {
    const version = await ownerSql.unsafe<{ server_version_num: string }[]>("SHOW server_version_num");
    expect(Number(version[0]?.server_version_num)).toBe(180004);
    expect(process.env["OMI_TEST_POSTGRES_IMAGE"]).toBe(
      "postgres:18.4-bookworm@sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382",
    );
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
      END
      $role$
    `, [], { prepare: false });

    const first = await runPostgresMigrations(ownerSql);
    const second = await runPostgresMigrations(ownerSql);
    expect([...first.appliedVersions, ...first.skippedVersions]).toEqual(
      POSTGRES_MIGRATIONS.map((entry) => entry.version),
    );
    expect(second.appliedVersions).toEqual([]);
    expect(second.skippedVersions).toEqual(POSTGRES_MIGRATIONS.map((entry) => entry.version));
  }, 120_000);

  test("one reserved connection owns the transaction and SET LOCAL clears after rollback", async () => {
    let firstBackend: number | undefined;
    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number }>({
          name: "qualification.backend_and_local",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        set_config('omi.account_id', $1, true) AS local_account`,
          values: ["account:qualification"],
        });
        firstBackend = rows[0]?.backend_pid;
        throw new Error("force rollback");
      },
    )).rejects.toThrow("force rollback");

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number; local_account: string | null }>({
          name: "qualification.local_cleared",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        expect(rows[0]?.backend_pid).toBe(firstBackend);
        expect(rows[0]?.local_account).toBeNull();
      },
    );
  });
});
