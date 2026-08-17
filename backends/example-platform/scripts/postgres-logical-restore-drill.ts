import type { PostgresTestState } from "./postgres-test-lifecycle";
import type { PostgresTestCommandRunner } from "./postgres-test-resources";

export const POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE = "omi_restore_drill" as const;
export const POSTGRES_LOGICAL_RESTORE_DRILL_DUMP = "/tmp/omi-memory-restore-drill.dump" as const;
export const POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DATABASE_BYTES = 512 * 1024 * 1024;
export const POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DUMP_BYTES = 64 * 1024 * 1024;

const DUMP_FILE_BLOCK_LIMIT = POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DUMP_BYTES / 512;

interface CriticalTableReceipt {
  readonly table_name: string;
  readonly row_count: number;
  readonly row_fingerprint: string;
}

interface LogicalRestoreReceipt {
  readonly server_version_num: string;
  readonly database_size_bytes: number;
  readonly schema_table_count: number;
  readonly migration_count: number;
  readonly migration_latest_version: number;
  readonly critical_tables: readonly CriticalTableReceipt[];
}

export interface PostgresLogicalRestoreDrillResult {
  readonly version: "postgres-logical-restore-drill-v1";
  readonly source_database_bytes: number;
  readonly dump_bytes: number;
  readonly migration_count: number;
  readonly schema_table_count: number;
  readonly critical_table_count: number;
}

const fail = (code: string): never => { throw new Error(code); };

const RECEIPT_SQL = String.raw`WITH critical_tables AS (
  SELECT 'account_restored_terminal_fences'::text AS table_name,
         count(*)::bigint AS row_count,
         md5(coalesce(string_agg(to_jsonb(row_value)::text, E'\n'
           ORDER BY to_jsonb(row_value)::text), '')) AS row_fingerprint
  FROM omi_memory.account_restored_terminal_fences AS row_value
  UNION ALL
  SELECT 'account_stranded_rollback_recovery_manifests', count(*)::bigint,
         md5(coalesce(string_agg(to_jsonb(row_value)::text, E'\n'
           ORDER BY to_jsonb(row_value)::text), ''))
  FROM omi_memory.account_stranded_rollback_recovery_manifests AS row_value
  UNION ALL
  SELECT 'account_stranded_rollback_recovery_surface_receipts', count(*)::bigint,
         md5(coalesce(string_agg(to_jsonb(row_value)::text, E'\n'
           ORDER BY to_jsonb(row_value)::text), ''))
  FROM omi_memory.account_stranded_rollback_recovery_surface_receipts AS row_value
  UNION ALL
  SELECT 'platform_schema_migrations', count(*)::bigint,
         md5(coalesce(string_agg(to_jsonb(row_value)::text, E'\n'
           ORDER BY to_jsonb(row_value)::text), ''))
  FROM omi_memory.platform_schema_migrations AS row_value
  UNION ALL
  SELECT 'postgres_restore_admission_heads', count(*)::bigint,
         md5(coalesce(string_agg(to_jsonb(row_value)::text, E'\n'
           ORDER BY to_jsonb(row_value)::text), ''))
  FROM omi_memory.postgres_restore_admission_heads AS row_value
  UNION ALL
  SELECT 'postgres_restore_admission_revisions', count(*)::bigint,
         md5(coalesce(string_agg(to_jsonb(row_value)::text, E'\n'
           ORDER BY to_jsonb(row_value)::text), ''))
  FROM omi_memory.postgres_restore_admission_revisions AS row_value
)
SELECT json_build_object(
  'server_version_num', current_setting('server_version_num'),
  'database_size_bytes', pg_database_size(current_database()),
  'schema_table_count', (
    SELECT count(*)::bigint FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname = 'omi_memory' AND relation.relkind IN ('r', 'p')
  ),
  'migration_count', (SELECT count(*)::bigint FROM omi_memory.platform_schema_migrations),
  'migration_latest_version', (SELECT max(version)::bigint FROM omi_memory.platform_schema_migrations),
  'critical_tables', (SELECT json_agg(critical_tables ORDER BY table_name) FROM critical_tables)
)::text`;

const dockerExec = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
  args: readonly string[],
) => run(["docker", "exec", state.containerName, ...args]);

const psql = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
  database: string,
  sql: string,
) => dockerExec(run, state, [
  "psql", "--username", "omi_test", "--dbname", database, "--no-password",
  "--set", "ON_ERROR_STOP=1", "--tuples-only", "--no-align", "--command", sql,
]);

const plainRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
  && Object.getPrototypeOf(value) === Object.prototype;

const safeCount = (value: unknown): value is number =>
  Number.isSafeInteger(value) && (value as number) >= 0;

const parseReceipt = (stdout: string): LogicalRestoreReceipt => {
  let value: unknown;
  try { value = JSON.parse(stdout); } catch { return fail("postgres_restore_drill_receipt_invalid"); }
  if (!plainRecord(value)
    || Object.keys(value).sort().join("\0") !== [
      "critical_tables", "database_size_bytes", "migration_count", "migration_latest_version",
      "schema_table_count", "server_version_num",
    ].sort().join("\0")
    || value["server_version_num"] !== "180004"
    || !safeCount(value["database_size_bytes"])
    || !safeCount(value["schema_table_count"])
    || !safeCount(value["migration_count"])
    || !safeCount(value["migration_latest_version"])
    || !Array.isArray(value["critical_tables"])) {
    return fail("postgres_restore_drill_receipt_invalid");
  }
  const critical = value["critical_tables"];
  if (critical.length !== 6) return fail("postgres_restore_drill_receipt_invalid");
  let previous = "";
  for (const entry of critical) {
    if (!plainRecord(entry)
      || Object.keys(entry).sort().join("\0") !== ["row_count", "row_fingerprint", "table_name"].join("\0")
      || typeof entry["table_name"] !== "string" || entry["table_name"] <= previous
      || !safeCount(entry["row_count"])
      || typeof entry["row_fingerprint"] !== "string"
      || !/^[0-9a-f]{32}$/.test(entry["row_fingerprint"])) {
      return fail("postgres_restore_drill_receipt_invalid");
    }
    previous = entry["table_name"];
  }
  return value as unknown as LogicalRestoreReceipt;
};

const receiptFor = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
  database: string,
): LogicalRestoreReceipt => {
  const result = psql(run, state, database, RECEIPT_SQL);
  if (result.exitCode !== 0) return fail("postgres_restore_drill_receipt_failed");
  return parseReceipt(result.stdout);
};

const integrityProjection = (receipt: LogicalRestoreReceipt): string => JSON.stringify({
  server_version_num: receipt.server_version_num,
  schema_table_count: receipt.schema_table_count,
  migration_count: receipt.migration_count,
  migration_latest_version: receipt.migration_latest_version,
  critical_tables: receipt.critical_tables,
});

const cleanup = (run: PostgresTestCommandRunner, state: PostgresTestState): void => {
  const database = dockerExec(run, state, [
    "dropdb", "--username", "omi_test", "--no-password", "--if-exists", "--force",
    POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE,
  ]);
  const dump = dockerExec(run, state, ["rm", "-f", POSTGRES_LOGICAL_RESTORE_DRILL_DUMP]);
  if (database.exitCode !== 0 || dump.exitCode !== 0) {
    return fail("postgres_restore_drill_cleanup_failed");
  }
};

export const runPostgresLogicalRestoreDrill = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
  expectedMigrationCount: number,
): PostgresLogicalRestoreDrillResult => {
  if (!Number.isSafeInteger(expectedMigrationCount) || expectedMigrationCount < 1) {
    return fail("postgres_restore_drill_manifest_invalid");
  }
  cleanup(run, state);
  try {
    const source = receiptFor(run, state, "omi_test");
    if (source.database_size_bytes > POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DATABASE_BYTES) {
      return fail("postgres_restore_drill_source_too_large");
    }
    if (source.migration_count !== expectedMigrationCount
      || source.migration_latest_version !== expectedMigrationCount
      || source.schema_table_count < expectedMigrationCount
      || source.critical_tables.some((entry) => entry.row_count < 1)) {
      return fail("postgres_restore_drill_source_unqualified");
    }

    const dump = dockerExec(run, state, [
      "sh", "-ceu",
      `umask 077; ulimit -f ${DUMP_FILE_BLOCK_LIMIT}; exec timeout --signal=TERM 120 pg_dump`
        + ` --username omi_test --dbname omi_test --no-password --format=custom --compress=0`
        + ` --no-owner --file=${POSTGRES_LOGICAL_RESTORE_DRILL_DUMP}`,
    ]);
    if (dump.exitCode !== 0) return fail("postgres_restore_drill_dump_failed");
    const size = dockerExec(run, state, [
      "stat", "--format=%s", POSTGRES_LOGICAL_RESTORE_DRILL_DUMP,
    ]);
    const dumpBytes = Number(size.stdout);
    if (size.exitCode !== 0 || !Number.isSafeInteger(dumpBytes) || dumpBytes < 1
      || dumpBytes > POSTGRES_LOGICAL_RESTORE_DRILL_MAX_DUMP_BYTES) {
      return fail("postgres_restore_drill_dump_size_invalid");
    }

    const created = dockerExec(run, state, [
      "createdb", "--username", "omi_test", "--no-password", "--template", "template0",
      POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE,
    ]);
    if (created.exitCode !== 0) return fail("postgres_restore_drill_database_create_failed");
    const restored = dockerExec(run, state, [
      "timeout", "--signal=TERM", "180", "pg_restore", "--username", "omi_test", "--no-password",
      "--dbname", POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE, "--exit-on-error",
      "--single-transaction", "--no-owner", POSTGRES_LOGICAL_RESTORE_DRILL_DUMP,
    ]);
    if (restored.exitCode !== 0) return fail("postgres_restore_drill_restore_failed");

    const target = receiptFor(run, state, POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE);
    if (integrityProjection(target) !== integrityProjection(source)) {
      return fail("postgres_restore_drill_integrity_mismatch");
    }
    const denied = psql(run, state, POSTGRES_LOGICAL_RESTORE_DRILL_DATABASE,
      "SET ROLE omi_platform_application; SELECT account_id FROM omi_memory.account_restored_terminal_fences LIMIT 1");
    if (denied.exitCode === 0) return fail("postgres_restore_drill_privilege_mismatch");

    return Object.freeze({
      version: "postgres-logical-restore-drill-v1",
      source_database_bytes: source.database_size_bytes,
      dump_bytes: dumpBytes,
      migration_count: source.migration_count,
      schema_table_count: source.schema_table_count,
      critical_table_count: source.critical_tables.length,
    });
  } finally {
    cleanup(run, state);
  }
};
