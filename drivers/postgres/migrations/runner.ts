import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import type { Sql } from "postgres";

import { POSTGRES_MIGRATIONS, type PostgresMigrationManifestEntry } from "./manifest";

export type PostgresMigrationErrorCode =
  | "unsupported_postgres_server_version"
  | "postgres_migration_checksum_mismatch"
  | "postgres_migration_history_conflict"
  | "postgres_migration_failed";

export class PostgresMigrationError extends Error {
  constructor(readonly code: PostgresMigrationErrorCode) {
    super(code);
    this.name = "PostgresMigrationError";
  }
}

export interface PostgresMigrationRunResult {
  readonly serverMajor: 18;
  readonly appliedVersions: readonly number[];
  readonly skippedVersions: readonly number[];
}

interface LoadedMigration extends PostgresMigrationManifestEntry {
  readonly sql: string;
}

const loadMigrations = (
  manifest: readonly PostgresMigrationManifestEntry[],
  readBytes: (entry: PostgresMigrationManifestEntry) => Uint8Array,
): readonly LoadedMigration[] => Object.freeze(manifest.map((entry) => {
  const bytes = readBytes(entry);
  if (createHash("sha256").update(bytes).digest("hex") !== entry.sha256) {
    throw new PostgresMigrationError("postgres_migration_checksum_mismatch");
  }
  return Object.freeze({ ...entry, sql: new TextDecoder("utf-8", { fatal: true }).decode(bytes) });
}));

const defaultReadBytes = (entry: PostgresMigrationManifestEntry): Uint8Array =>
  readFileSync(new URL(entry.fileName, import.meta.url));

export const runPostgresMigrations = async (
  sql: Sql<Record<string, never>>,
  options: {
    readonly manifest?: readonly PostgresMigrationManifestEntry[];
    readonly readBytes?: (entry: PostgresMigrationManifestEntry) => Uint8Array;
  } = {},
): Promise<PostgresMigrationRunResult> => {
  let loaded: readonly LoadedMigration[];
  try {
    loaded = loadMigrations(
      options.manifest ?? POSTGRES_MIGRATIONS,
      options.readBytes ?? defaultReadBytes,
    );
  } catch (error) {
    if (error instanceof PostgresMigrationError) throw error;
    throw new PostgresMigrationError("postgres_migration_failed");
  }

  try {
    const versionRows = await sql.unsafe<{ server_version_num: string }[]>("SHOW server_version_num");
    const serverVersion = Number(versionRows[0]?.server_version_num);
    if (!Number.isSafeInteger(serverVersion) || serverVersion < 180_000 || serverVersion >= 190_000) {
      throw new PostgresMigrationError("unsupported_postgres_server_version");
    }

    return await sql.begin("isolation level serializable read write", async (transaction) => {
      await transaction.unsafe("SELECT pg_advisory_xact_lock($1, $2)", [1_869_442_409, 1]);
      const applied: number[] = [];
      const skipped: number[] = [];
      for (const migration of loaded) {
        const relation = await transaction.unsafe<{ migration_table: string | null }[]>(
          "SELECT to_regclass('omi_memory.platform_schema_migrations')::text AS migration_table",
        );
        const existing = relation[0]?.migration_table === null
          ? []
          : await transaction.unsafe<{ name: string; sha256: string }[]>(
            "SELECT name, sha256 FROM omi_memory.platform_schema_migrations WHERE version = $1",
            [migration.version],
          );
        const receipt = existing[0];
        if (receipt) {
          if (receipt.name !== migration.name || receipt.sha256 !== migration.sha256) {
            throw new PostgresMigrationError("postgres_migration_history_conflict");
          }
          skipped.push(migration.version);
          continue;
        }
        await transaction.unsafe(migration.sql, [], { prepare: false });
        await transaction.unsafe(
          `INSERT INTO omi_memory.platform_schema_migrations (version, name, sha256)
           VALUES ($1, $2, $3)`,
          [migration.version, migration.name, migration.sha256],
        );
        applied.push(migration.version);
      }
      return Object.freeze({
        serverMajor: 18 as const,
        appliedVersions: Object.freeze(applied),
        skippedVersions: Object.freeze(skipped),
      });
    });
  } catch (error) {
    if (error instanceof PostgresMigrationError) throw error;
    throw new PostgresMigrationError("postgres_migration_failed");
  }
};
