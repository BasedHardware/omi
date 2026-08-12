import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, test } from "bun:test";

import { POSTGRES_MIGRATIONS } from "./manifest";

const directory = new URL("./", import.meta.url);

describe("PostgreSQL migration manifest", () => {
  test("is an immutable, ordered, gap-free P2/P3/P4/P5 manifest", () => {
    expect(Object.isFrozen(POSTGRES_MIGRATIONS)).toBe(true);
    expect(POSTGRES_MIGRATIONS.map((migration) => migration.version))
      .toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]);
    expect(new Set(POSTGRES_MIGRATIONS.map((migration) => migration.name)).size)
      .toBe(POSTGRES_MIGRATIONS.length);
    for (const migration of POSTGRES_MIGRATIONS) {
      expect(Object.isFrozen(migration)).toBe(true);
      expect(migration.fileName).toBe(`${String(migration.version).padStart(4, "0")}-${migration.name}.sql`);
      expect(migration.sha256).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  test("covers every SQL file and pins its exact bytes", () => {
    const sqlFiles = readdirSync(directory)
      .filter((fileName) => fileName.endsWith(".sql"))
      .sort();
    expect(POSTGRES_MIGRATIONS.map((migration) => migration.fileName)).toEqual(sqlFiles);

    for (const migration of POSTGRES_MIGRATIONS) {
      const bytes = readFileSync(new URL(migration.fileName, directory));
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(migration.sha256);
    }
  });
});
