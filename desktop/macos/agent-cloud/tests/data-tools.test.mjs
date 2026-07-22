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
  topWindows,
} from "../data-tools.mjs";

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
