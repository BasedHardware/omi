import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import Database from "better-sqlite3";
import { afterEach, describe, expect, it } from "vitest";

import {
  activityCounts,
  appUsageMatrix,
  emptyRangeStatement,
  formatAppUsage,
  resolveRange,
  topWindows, runSqlBatch, executeReadOnlyQuery, truncateToolResult } from "../data-tools.mjs";

const dirs = [];
afterEach(() => { while (dirs.length) rmSync(dirs.pop(), { recursive: true, force: true }); });

function seededDb() {
  const dir = mkdtempSync(join(tmpdir(), "omi-data-tools-"));
  dirs.push(dir);
  const db = new Database(join(dir, "t.db"));
  db.exec(`
    CREATE TABLE screenshots (timestamp TEXT, appName TEXT, windowTitle TEXT);
    CREATE TABLE transcription_sessions (startedAt TEXT, deleted INT DEFAULT 0, discarded INT DEFAULT 0);
    CREATE TABLE action_items (createdAt TEXT, deleted INT DEFAULT 0);
    INSERT INTO screenshots VALUES
      ('2026-07-14 09:00:00', 'Warp', 'build logs'),
      ('2026-07-14 09:10:00', 'Warp', 'build logs'),
      ('2026-07-14 10:00:00', 'Chrome', 'docs'),
      ('2026-07-15 11:00:00', 'Cursor', 'agent.mjs');
    INSERT INTO transcription_sessions (startedAt) VALUES ('2026-07-14 12:00:00');
    INSERT INTO action_items (createdAt) VALUES ('2026-07-15 13:00:00');
  `);
  return db;
}

describe("resolveRange", () => {
  it("resolves explicit dates with an exclusive end", () => {
    const r = resolveRange({ start_date: "2026-07-15" });
    expect(r).toMatchObject({ start: "2026-07-15", endExclusive: "2026-07-16", spanDays: 1 });
    const r2 = resolveRange({ start_date: "2026-07-10", end_date: "2026-07-16" });
    expect(r2).toMatchObject({ endExclusive: "2026-07-17", spanDays: 7 });
  });

  it("rejects malformed and inverted dates", () => {
    expect(() => resolveRange({ start_date: "July 15" })).toThrow(/YYYY-MM-DD/);
    expect(() => resolveRange({ start_date: "2026-07-15'; DROP TABLE x;--" })).toThrow(/YYYY-MM-DD/);
    expect(() => resolveRange({ start_date: "2026-07-16", end_date: "2026-07-15" })).toThrow(/precede/);
  });
});

describe("activityCounts + emptyRangeStatement", () => {
  it("is authoritative and explicit for an empty range", () => {
    const db = seededDb();
    const range = resolveRange({ start_date: "2026-07-20" });
    const statement = emptyRangeStatement(range, activityCounts(db, range));
    expect(statement).toContain("no activity recorded");
    expect(statement).toContain("do not run further queries");
    db.close();
  });

  it("returns null when any activity exists", () => {
    const db = seededDb();
    const range = resolveRange({ start_date: "2026-07-15" });
    expect(emptyRangeStatement(range, activityCounts(db, range))).toBeNull();
    db.close();
  });
});

describe("appUsageMatrix", () => {
  it("returns per-day breakdown and sorted totals in one shape", () => {
    const db = seededDb();
    const range = resolveRange({ start_date: "2026-07-14", end_date: "2026-07-15" });
    const m = appUsageMatrix(db, range);
    expect(m.totals[0]).toEqual({ appName: "Warp", captures: 2 });
    expect(m.days.map((d) => d.day)).toEqual(["2026-07-14", "2026-07-15"]);
    const text = formatAppUsage(range, m);
    expect(text).toContain("2026-07-14");
    expect(text).toContain("Warp 2");
    db.close();
  });
});

describe("topWindows", () => {
  it("lists top window titles for top apps", () => {
    const db = seededDb();
    const range = resolveRange({ start_date: "2026-07-14" });
    const per = topWindows(db, range);
    expect(per[0].appName).toBe("Warp");
    expect(per[0].windows[0]).toMatchObject({ windowTitle: "build logs", captures: 2 });
    db.close();
  });
});

describe("runSqlBatch", () => {
  it("labels each result in order", () => {
    const out = runSqlBatch((sql) => `rows-for:${sql}`, ["SELECT 1", "SELECT 2"]);
    expect(out).toContain("-- [1] SELECT 1\nrows-for:SELECT 1");
    expect(out).toContain("-- [2] SELECT 2\nrows-for:SELECT 2");
  });

  it("isolates per-query errors so one bad statement never voids the batch", () => {
    const out = runSqlBatch(
      (sql) => {
        if (sql.includes("BAD")) throw new Error("no such table");
        return "ok";
      },
      ["SELECT good", "SELECT BAD", "SELECT good2"],
    );
    expect(out).toContain('-- [2] SELECT BAD\n{"error":"no such table"}');
    expect(out).toContain("-- [3] SELECT good2\nok");
  });
});

describe("executeReadOnlyQuery", () => {
  it("allows CTE reads that the old prefix guard rejected", () => {
    const db = seededDb();
    const out = JSON.parse(
      executeReadOnlyQuery(db, "WITH w AS (SELECT appName FROM screenshots) SELECT appName, COUNT(*) c FROM w GROUP BY appName"),
    );
    expect(out.error).toBeUndefined();
    expect(out.rows.length).toBeGreaterThan(0);
    db.close();
  });

  it("rejects writes even when wrapped in a CTE", () => {
    const db = seededDb();
    const out = JSON.parse(
      executeReadOnlyQuery(db, "WITH w AS (SELECT 1) INSERT INTO screenshots (timestamp, appName) VALUES ('x','y')"),
    );
    expect(out.error).toContain("read-only");
    db.close();
  });

  it("caps rows via iteration even when a subquery contains LIMIT", () => {
    const db = seededDb();
    db.exec("CREATE TABLE nums (n INT)");
    const ins = db.prepare("INSERT INTO nums VALUES (?)");
    for (let i = 0; i < 300; i++) ins.run(i);
    const out = JSON.parse(
      executeReadOnlyQuery(db, "SELECT * FROM nums WHERE n IN (SELECT n FROM nums LIMIT 300)", 200),
    );
    expect(out.count).toBe(200);
    expect(out.truncated).toBe(true);
    db.close();
  });

  it("does not false-positive on user data containing keyword-like words", () => {
    const db = seededDb();
    const out = JSON.parse(
      executeReadOnlyQuery(db, "SELECT * FROM screenshots WHERE windowTitle LIKE '%create%' OR windowTitle LIKE '%alter%'"),
    );
    expect(out.error).toBeUndefined();
    db.close();
  });

  it("rejects multi-statement strings via prepare", () => {
    const db = seededDb();
    const out = JSON.parse(executeReadOnlyQuery(db, "SELECT 1; SELECT 2"));
    expect(out.error).toBeTruthy();
    db.close();
  });
});

describe("truncateToolResult", () => {
  it("passes small results through untouched", () => {
    const out = truncateToolResult("small", "execute_sql");
    expect(out).toEqual({ text: "small", truncated: false });
  });

  it("truncates oversized results with a re-run marker", () => {
    const out = truncateToolResult("x".repeat(50_000), "playwright_snapshot", 10_000);
    expect(out.truncated).toBe(true);
    expect(out.originalChars).toBe(50_000);
    expect(out.text.length).toBeLessThanOrEqual(10_000);
    expect(out.text).toContain("truncated: 50000 chars total");
  });
});
