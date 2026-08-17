import { readFileSync } from "node:fs";

import { describe, expect, test } from "bun:test";

import { DELETION_DISPOSAL_GROUPS } from "../../core/control/deletion-cleanup-inventory";
import { POSTGRES_MIGRATIONS } from "../../drivers/postgres/migrations/manifest";
import {
  POSTGRES_DELETION_SURFACE_TABLES,
  POSTGRES_RETAINED_DELETION_SAFETY_TABLES,
  POSTGRES_RETAINED_RESTORE_SAFETY_TABLES,
} from "./deletion-surface-registry";

const directory = new URL("../../drivers/postgres/migrations/", import.meta.url);
const migrationSql = POSTGRES_MIGRATIONS.map((migration) => ({
  ...migration,
  sql: readFileSync(new URL(migration.fileName, directory), "utf8"),
}));
const allSql = migrationSql.map((migration) => migration.sql).join("\n");

interface TableDefinition {
  readonly name: string;
  readonly body: string;
}

const tableDefinitions = (sql: string): readonly TableDefinition[] => {
  const definitions: TableDefinition[] = [];
  const start = /CREATE TABLE omi_memory\.([a-z0-9_]+)\s*\(/g;
  for (let match = start.exec(sql); match; match = start.exec(sql)) {
    let depth = 1;
    let cursor = start.lastIndex;
    let quoted = false;
    for (; cursor < sql.length && depth > 0; cursor += 1) {
      const character = sql[cursor]!;
      if (character === "'" && sql[cursor - 1] !== "\\") quoted = !quoted;
      if (quoted) continue;
      if (character === "(") depth += 1;
      if (character === ")") depth -= 1;
    }
    if (depth !== 0) throw new Error(`unterminated CREATE TABLE ${match[1]}`);
    definitions.push({ name: match[1]!, body: sql.slice(start.lastIndex, cursor - 1) });
    start.lastIndex = cursor;
  }
  return definitions;
};

const tables = tableDefinitions(allSql);

describe("deletion-surface registry against the live PostgreSQL schema", () => {
  test("classifies every PostgreSQL table once for deletion or retained safety", () => {
    const disposalRows = Object.entries(POSTGRES_DELETION_SURFACE_TABLES)
      .flatMap(([surface, names]) => names.map((name) => ({ surface, name })));
    const allClassified = [
      ...disposalRows.map((row) => row.name),
      ...POSTGRES_RETAINED_DELETION_SAFETY_TABLES,
      ...POSTGRES_RETAINED_RESTORE_SAFETY_TABLES,
    ];
    expect(new Set(allClassified).size).toBe(allClassified.length);
    expect([...allClassified].sort()).toEqual(tables.map((table) => table.name).sort());
    expect(disposalRows.some((row) => row.surface === "authoritative_memory")).toBe(true);
    expect(disposalRows.some((row) => row.surface === "account_access")).toBe(true);
    expect(POSTGRES_RETAINED_DELETION_SAFETY_TABLES)
      .toContain("account_terminal_deletion_exports");
    expect(disposalRows.map((row) => row.name))
      .not.toContain("account_terminal_deletion_exports");
    expect(POSTGRES_RETAINED_RESTORE_SAFETY_TABLES)
      .toEqual([
        "postgres_restore_replay_checkpoint_candidates",
        "postgres_restore_admission_revisions",
        "postgres_restore_admission_heads",
      ]);
  });

  test("keeps the cleanup security-definer registry identical to the typed registry", () => {
    const cleanupSql = [...migrationSql].reverse().find((migration) =>
      /CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION omi_memory\.cleanup_surface_tables\(/.test(migration.sql),
    )?.sql;
    expect(cleanupSql).toBeDefined();
    const block = cleanupSql!.match(
      /CREATE OR REPLACE FUNCTION omi_memory\.cleanup_surface_tables\(p_surface text\)[\s\S]*?FROM \(VALUES([\s\S]*?)\) AS mapping\(surface, table_name\)/,
    );
    expect(block).not.toBeNull();
    const sqlRows = [...block![1]!.matchAll(/\('([a-z0-9_]+)', '([a-z0-9_]+)'\)/g)]
      .map((match) => ({ surface: match[1]!, table: match[2]! }))
      .sort((left, right) => `${left.surface}:${left.table}`.localeCompare(
        `${right.surface}:${right.table}`,
      ));
    const typedRows = Object.entries(POSTGRES_DELETION_SURFACE_TABLES)
      .flatMap(([surface, names]) => names.map((table) => ({ surface, table })))
      .sort((left, right) => `${left.surface}:${left.table}`.localeCompare(
        `${right.surface}:${right.table}`,
      ));
    expect(sqlRows).toEqual(typedRows);
  });

  test("orders every cross-surface foreign key child before its parent", () => {
    const tableSurface = new Map(Object.entries(POSTGRES_DELETION_SURFACE_TABLES)
      .flatMap(([surface, names]) => names.map((name) => [name, surface] as const)));
    const surfaceGroup = new Map(DELETION_DISPOSAL_GROUPS.flatMap((group, index) =>
      group.map((surface) => [surface, index] as const)));
    expect(new Set(DELETION_DISPOSAL_GROUPS.flat()).size)
      .toBe(DELETION_DISPOSAL_GROUPS.flat().length);
    for (const table of tables) {
      const childSurface = tableSurface.get(table.name);
      const parents = [...table.body.matchAll(/REFERENCES omi_memory\.([a-z0-9_]+)/g)]
        .map((match) => match[1]!);
      for (const parent of parents) {
        const parentSurface = tableSurface.get(parent);
        if (childSurface === undefined && parentSurface !== undefined) {
          throw new Error(`retained table ${table.name} references disposable ${parent}`);
        }
        if (childSurface === undefined || parentSurface === undefined) continue;
        const childGroup = surfaceGroup.get(childSurface as never);
        const parentGroup = surfaceGroup.get(parentSurface as never);
        if (childGroup === undefined || parentGroup === undefined) {
          throw new Error(`unranked surface ${childSurface} -> ${parentSurface}`);
        }
        expect(childGroup, `${table.name} -> ${parent}`).toBeLessThanOrEqual(parentGroup);
      }
    }
  });
});
