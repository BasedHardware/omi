import { describe, expect, test } from "bun:test";

import { createPostgresTestState } from "./postgres-test-lifecycle";
import {
  POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE,
  POSTGRES_LOGICAL_RESTORE_DRILL_DUMP,
  POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DATABASE_BYTES,
  POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DUMP_BYTES,
  runPostgresLogicalRestoreDrill,
} from "./postgres-logical-restore-drill";
import type { PostgresTestCommandResult } from "./postgres-test-resources";

const state = createPostgresTestState("/workspace/platform", () => new Uint8Array(12).fill(7));
const fingerprint = (character: string) => character.repeat(32);
const criticalTables = [
  "account_restored_terminal_fences",
  "account_stranded_rollback_recovery_manifests",
  "account_stranded_rollback_recovery_surface_receipts",
  "platform_schema_migrations",
  "postgres_restore_admission_heads",
  "postgres_restore_admission_revisions",
].map((table_name, index) => ({ table_name, row_count: index + 1, row_fingerprint: fingerprint(String(index)) }));
const receipt = (databaseBytes = 32 * 1024 * 1024) => JSON.stringify({
  server_version_num: "180004",
  database_size_bytes: databaseBytes,
  schema_table_count: 84,
  migration_count: 41,
  migration_latest_version: 41,
  critical_tables: criticalTables,
});

describe("bounded PostgreSQL logical restore drill", () => {
  test("dumps, restores, verifies, denies app-role table reads, and cleans both artifacts", () => {
    const commands: readonly string[][] = [];
    const mutable = commands as string[][];
    let receiptReads = 0;
    const run = (args: readonly string[]): PostgresTestCommandResult => {
      mutable.push([...args]);
      const joined = args.join(" ");
      if (joined.includes(" json_build_object(")) {
        receiptReads += 1;
        return { exitCode: 0, stdout: receipt(), stderr: "" };
      }
      if (joined.includes("stat --format=%s")) {
        return { exitCode: 0, stdout: "1048576", stderr: "" };
      }
      if (joined.includes("SET ROLE omi_platform_application")) {
        return { exitCode: 1, stdout: "", stderr: "permission denied" };
      }
      return { exitCode: 0, stdout: "", stderr: "" };
    };

    expect(runPostgresLogicalRestoreDrill(run, state, 41)).toEqual({
      version: "postgres-logical-restore-drill-v1",
      source_database_bytes: 32 * 1024 * 1024,
      dump_bytes: 1_048_576,
      migration_count: 41,
      schema_table_count: 84,
      critical_table_count: 6,
    });
    expect(receiptReads).toBe(2);
    expect(commands.some((args) => args.includes("pg_dump") || args.some((arg) => arg.includes("exec timeout")))).toBe(true);
    expect(commands.some((args) => args.includes("pg_restore"))).toBe(true);
    expect(commands.filter((args) => args.includes("dropdb"))).toHaveLength(2);
    expect(commands.filter((args) => args.includes("rm") && args.includes(POSTGRES_LOGICAL_RESTORE_DRILL_DUMP)))
      .toHaveLength(2);
    expect(commands.every((args) => !args.join(" ").includes("POSTGRES_PASSWORD"))).toBe(true);
  });

  test("rejects an oversized source before dump and still cleans", () => {
    const commands: string[][] = [];
    const run = (args: readonly string[]): PostgresTestCommandResult => {
      commands.push([...args]);
      if (args.join(" ").includes(" json_build_object(")) {
        return { exitCode: 0, stdout: receipt(POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DATABASE_BYTES + 1), stderr: "" };
      }
      return { exitCode: 0, stdout: "", stderr: "" };
    };
    expect(() => runPostgresLogicalRestoreDrill(run, state, 41))
      .toThrow("postgres_restore_drill_source_too_large");
    expect(commands.some((args) => args.some((arg) => arg.includes("pg_dump")))).toBe(false);
    expect(commands.filter((args) => args.includes("dropdb"))).toHaveLength(2);
  });

  test("caps dump bytes and fails closed on restored receipt drift", () => {
    const commands: string[][] = [];
    let receiptReads = 0;
    const run = (args: readonly string[]): PostgresTestCommandResult => {
      commands.push([...args]);
      const joined = args.join(" ");
      if (joined.includes(" json_build_object(")) {
        receiptReads += 1;
        const parsed = JSON.parse(receipt());
        if (receiptReads === 2) parsed.critical_tables[0].row_count += 1;
        return { exitCode: 0, stdout: JSON.stringify(parsed), stderr: "" };
      }
      if (joined.includes("stat --format=%s")) {
        return { exitCode: 0, stdout: String(POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DUMP_BYTES), stderr: "" };
      }
      return { exitCode: 0, stdout: "", stderr: "" };
    };
    expect(() => runPostgresLogicalRestoreDrill(run, state, 41))
      .toThrow("postgres_restore_drill_integrity_mismatch");
    expect(commands.filter((args) => args.includes("dropdb"))).toHaveLength(2);
  });

  test("rejects a dump over the hard post-write bound", () => {
    const run = (args: readonly string[]): PostgresTestCommandResult => {
      const joined = args.join(" ");
      if (joined.includes(" json_build_object(")) return { exitCode: 0, stdout: receipt(), stderr: "" };
      if (joined.includes("stat --format=%s")) {
        return { exitCode: 0, stdout: String(POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DUMP_BYTES + 1), stderr: "" };
      }
      return { exitCode: 0, stdout: "", stderr: "" };
    };
    expect(() => runPostgresLogicalRestoreDrill(run, state, 41))
      .toThrow("postgres_restore_drill_dump_size_invalid");
  });

  test("fails closed when exact artifact cleanup does not complete", () => {
    let cleanupCalls = 0;
    const run = (args: readonly string[]): PostgresTestCommandResult => {
      if (args.includes("dropdb")) cleanupCalls += 1;
      if (args.includes("rm")) return { exitCode: 1, stdout: "", stderr: "denied detail" };
      return { exitCode: 0, stdout: "", stderr: "" };
    };
    expect(() => runPostgresLogicalRestoreDrill(run, state, 41))
      .toThrow("postgres_restore_drill_cleanup_failed");
    expect(cleanupCalls).toBe(1);
  });
});
