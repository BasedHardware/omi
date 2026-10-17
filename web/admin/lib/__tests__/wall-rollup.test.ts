import { afterEach, expect, it, vi } from "vitest";
import {
  anonymize,
  closedDay,
  dailyExtractQuery,
  extractDay,
  hashId,
  keyId,
  PAGE_SIZE,
} from "../wall-rollup-extract";
import { preferRollup, readRollup } from "../wall-rollup";
import { rollupSql, RollupRequest } from "../wall-rollup-sql";
import { assembleSeries, legJobs, SeriesSources } from "../wall-series";
import { datesForRun } from "../../jobs/omi-tv-rollup/writer";
import type { WallPayload } from "../wall-metrics";

const key = "test-only-secret-of-at-least-32-bytes";
const day = "2026-10-12",
  end = new Date("2026-10-13T00:00Z");
const feature = (cursor = "z", kind = "marker"): unknown[] => [
  "raw-person-never-persist",
  kind,
  "ios",
  "2026-09-01 12:00:00",
  "2026-10-12 23:59:00",
  "2026-10-12 23:59:00",
  day,
  41,
  false,
  "",
  false,
  false,
  1,
  cursor,
];
afterEach(() => vi.unstubAllEnvs());

it("hashes resolved person IDs with a domain-separated key; raw IDs never persist", () => {
  const row = anonymize(day, feature(), key);
  expect(row.actor).toMatch(/^[a-f0-9]{64}$/);
  expect(JSON.stringify(row)).not.toContain("raw-person");
  expect(hashId(key, "x")).not.toBe(hashId(key, "x", "row"));
  expect(keyId(key)).not.toBe(keyId(key + "rotation"));
  expect(() => hashId("", "x")).toThrow();
  expect(row.latest).toBe("2026-10-12T23:59:00.000Z");
  expect(() => closedDay("2026-02-30")).toThrow();
  expect(() => closedDay("2026-10-13", end)).toThrow();
});
it("preserves microseconds for exact recency and signup-window boundaries", () => {
  const r = feature("u", "identity");
  r[3] = "2026-10-01 12:00:00.900001";
  r[4] = "2026-10-01 12:00:00.900002";
  r[5] = "2026-10-08 12:00:00.100001";
  const row = anonymize(day, r, key);
  expect(row.anchor).toBe("2026-10-01T12:00:00.900001Z");
  expect(row.first_at).toBe("2026-10-01T12:00:00.900002Z");
  expect(row.latest).toBe("2026-10-08T12:00:00.100001Z");
  expect(dailyExtractQuery(day, "", "activity")).toContain(
    "dateDiff('microsecond',anchor,qt)/86400000000"
  );
});
it("keeps profileless identity observations instead of aborting the day", () => {
  const personless = feature("n", "identity");
  personless[3] = null;
  const row = anonymize(day, personless, key);
  expect(row.anchor).toBeNull();
  expect(row.kind).toBe("identity");
  // HogQL's stringified null ("null") and epoch sentinels must also stay null.
  const textNull = feature("t", "identity");
  textNull[3] = "null";
  expect(anonymize(day, textNull, key).anchor).toBeNull();
  const epoch = feature("e", "identity");
  epoch[3] = "1970-01-01 00:00:00";
  expect(anonymize(day, epoch, key).anchor).toBeNull();
});
it("growth freshness derives only from app activity anchors, never identity rows", () => {
  const growth = rollupSql({ kind: "growth", end, periods: 1 });
  expect(growth.query).toContain(
    "anchors AS (SELECT actor,MIN(anchor) anchor FROM data WHERE kind='activity' GROUP BY actor)"
  );
  expect(growth.query).not.toContain(
    "kind='identity' GROUP BY actor),\n      labelled"
  );
});
it("extracts closed days with a one-day MCP probe and keyset pages, never OFFSET", () => {
  const sql = dailyExtractQuery(day, "a'\\b");
  const starts = Array.from(
    sql.matchAll(/timestamp >= toDateTime\('([^']+)'/g)
  ).map((m) => m[1]);
  expect(new Set(starts)).toEqual(new Set(["2026-10-12 00:00:00"]));
  expect(sql).toContain("timestamp < toDateTime('2026-10-13 00:00:00'");
  expect(sql).toContain(`LIMIT ${PAGE_SIZE}`);
  expect(sql).not.toContain("OFFSET");
  expect(sql).not.toContain("email");
  expect(sql).toContain("person.created_at");
});
it("does not accept truncated/default-capped, nonadvancing or unreceipted days", async () => {
  const empty = { results: [], sourceRefreshedAt: end.toISOString() };
  const query = vi.fn(async (sql: string) =>
    sql.includes("'marker' kind")
      ? { results: [feature()], sourceRefreshedAt: end.toISOString() }
      : empty
  );
  expect((await extractDay(day, key, query)).rows).toHaveLength(1);
  await expect(extractDay(day, key, async () => empty)).rejects.toThrow(
    "receipt missing"
  );
  await expect(
    extractDay(day, key, async () => ({
      results: [feature("z", "identity"), feature("a", "identity")],
      sourceRefreshedAt: end.toISOString(),
    }))
  ).rejects.toThrow("cursor");
  await expect(
    extractDay(day, key, async () => ({ results: [], sourceRefreshedAt: "" }))
  ).rejects.toThrow("watermark");
});
it("finishes multi-page extraction with a shared page budget across feature kinds", async () => {
  const page = Array.from({ length: PAGE_SIZE }, (_, i) =>
    feature(String(i).padStart(8, "0"), "identity")
  );
  const query = vi
    .fn(async (sql: string) => ({
      results: sql.includes("'marker' kind") ? [feature()] : [],
      sourceRefreshedAt: end.toISOString(),
    }))
    .mockResolvedValueOnce({
      results: page,
      sourceRefreshedAt: end.toISOString(),
    });
  const result = await extractDay(day, key, query);
  expect(result.pages).toBe(6);
  expect(query.mock.calls[1][0]).toContain("00004999");
}, 60_000); // Full production-size page under background CPU/IO scheduling.
it("daily repair is capped and explicit backfills always extract exactly one day", () => {
  expect(datesForRun(end, new Set())).toEqual([
    "2026-10-12",
    "2026-10-11",
    "2026-10-10",
    "2026-09-29",
    "2026-09-30",
  ]);
  expect(datesForRun(end, new Set(), day)).toEqual([day]);
  expect(() => datesForRun(end, new Set(), "2026-10-13")).toThrow();
});
it("requires every receipt for the exact version and key epoch, otherwise uses existing HogQL", async () => {
  vi.stubEnv("OMI_TV_ROLLUP_ENABLED", "1");
  vi.stubEnv("CRON_SECRET", key);
  const request: RollupRequest = { kind: "activity", end, days: 7, periods: 1 };
  const query = vi
    .fn()
    .mockResolvedValue([
      [{ covered: 30, rows: ['[0,"ios",12]'], refreshed: end.toISOString() }],
    ]);
  const got = await readRollup(request, { query });
  expect(got?.[0]).toEqual([0, "ios", 12]);
  expect(query.mock.calls[0][0].params.keyId).toBe(keyId(key));
  query.mockResolvedValueOnce([[{ covered: 29, rows: ['[0,"ios",12]'] }]]);
  const fallback = vi.fn().mockResolvedValue([[0, "ios", 99]]);
  expect(
    await preferRollup((r) => readRollup(r, { query }), request, fallback)
  ).toEqual([[0, "ios", 99]]);
  expect(fallback).toHaveBeenCalledOnce();
  const noFallback = vi.fn();
  await preferRollup(async () => got, request, noFallback);
  expect(noFallback).not.toHaveBeenCalled();
});
it("caps the rollup status lookup at one second and keeps filling the cache", async () => {
  vi.stubEnv("OMI_TV_ROLLUP_ENABLED", "1");
  vi.stubEnv("CRON_SECRET", key);
  const { rollupStatus } = await import("../wall-rollup");
  let release: ((rows: unknown) => void) | undefined;
  const slow = {
    query: () =>
      new Promise<[Record<string, unknown>[]]>((resolve) => {
        release = (rows) => resolve([rows as Record<string, unknown>[]]);
      }),
  } as unknown as import("../wall-rollup").RollupDb;
  const started = Date.now();
  const first = await rollupStatus(slow);
  expect(Date.now() - started).toBeLessThan(2_000);
  expect(first.through).toBeNull();
  expect(["slow", "unavailable", "no completed days"]).toContain(first.reason);
  // The background lookup still populates the cache once it finishes.
  release?.([{ through: "2026-10-11" }]);
  await new Promise((r) => setTimeout(r, 20));
  const second = await rollupStatus(slow);
  expect(second.through).toBe("2026-10-11");
  expect(second.reason).toBeNull();
});
it("coalesces concurrent status cache misses into one shared lookup", async () => {
  vi.stubEnv("OMI_TV_ROLLUP_ENABLED", "1");
  vi.stubEnv("CRON_SECRET", key);
  vi.resetModules();
  const { rollupStatus: fresh } = await import("../wall-rollup");
  let queries = 0;
  let release: ((rows: unknown) => void) | undefined;
  const slow = {
    query: () =>
      new Promise<[Record<string, unknown>[]]>((resolve) => {
        queries++;
        release = (rows) => resolve([rows as Record<string, unknown>[]]);
      }),
  } as unknown as import("../wall-rollup").RollupDb;
  // Five concurrent misses during a >1s slowdown must share one BigQuery query.
  const calls = Array.from({ length: 5 }, () => fresh(slow));
  await new Promise((r) => setTimeout(r, 1_100));
  expect(queries).toBe(1);
  release?.([{ through: "2026-10-11" }]);
  for (const r of await Promise.all(calls)) expect(r.reason).toBe("slow");
  await new Promise((r) => setTimeout(r, 20));
  // Once the shared flight settles, the cache serves everyone without querying.
  const settled = await fresh(slow);
  expect(settled.through).toBe("2026-10-11");
  expect(settled.reason).toBeNull();
  expect(queries).toBe(1);
});
it("guards cohort lookback, exact signup-relative bins, entry platform, and frozen retention platform", () => {
  const cohort = rollupSql({ kind: "cohort", end, maturity: 37, periods: 6 });
  expect(+cohort.start).toBe(+end - (37 + 42 + 180) * 86400000);
  expect(cohort.query).toContain("first_event>=a");
  expect(cohort.query).toContain("age_day BETWEEN 0 AND 6");
  expect(cohort.query).toContain("age_day BETWEEN 7 AND 36");
  expect(cohort.query).toContain("first_at,p");
  const established = rollupSql({ kind: "established", end, periods: 6 });
  expect(established.query).toContain("ORDER BY prior_days DESC");
  expect(established.query).toContain("LOGICAL_OR(w1) AND LOGICAL_OR(w2)");
});
it("all PostHog legs can choose rollups; v2 snapshot wins the last point and split", async () => {
  const query = vi
    .fn()
    .mockRejectedValue(new Error("HogQL should not run with coverage"));
  const rollup = vi.fn().mockResolvedValue(
    Object.assign(
      [
        [0, "ios", 100, 300, 50, 10],
        [0, "__days_3", 100, 0, 0, 0],
      ],
      { sourceRefreshedAt: end.toISOString() }
    )
  );
  const sources = { query, rollup } as unknown as SeriesSources;
  const jobs = legJobs(sources, end);
  for (const leg of [
    "growth",
    "activationHistory",
    "captureSource",
    "retainedHistory",
    "establishedHistory",
    "curve",
    "mauPrior",
    "mauDaily",
  ] as const)
    await jobs[leg]();
  expect(query).not.toHaveBeenCalled();
  const snapshot = {
    metrics: [
      {
        id: "growth.wau",
        value: 23,
        split: { macos: 3, mobile: 20, other: 0 },
        trend: [
          { date: day, value: 23, split: { macos: 3, mobile: 20, other: 0 } },
        ],
      },
    ],
  } as unknown as WallPayload;
  const frames = assembleSeries(
    "growth",
    { growth: await rollup() },
    snapshot,
    end
  );
  expect(frames.weekly.at(-1)).toMatchObject({
    total: 23,
    macos: 3,
    mobile: 20,
    other: 0,
  });
});

it("publishes a day and receipt atomically, and never issues replacement SQL after a failed load", async () => {
  const { Writable } = await import("stream");
  const { writeDay } = await import("../../jobs/omi-tv-rollup/writer");
  vi.stubEnv("CRON_SECRET", key);
  const data = {
    rows: [anonymize(day, feature(), key)],
    refreshedAt: end.toISOString(),
    pages: 1,
  };
  const create = vi.fn().mockResolvedValue([]),
    drop = vi.fn().mockResolvedValue([]);
  const query = vi.fn().mockResolvedValue([]);
  let fail = false;
  const table = {
    create,
    delete: drop,
    getMetadata: async () => [{ schema: { fields: [] } }],
    createWriteStream: () => {
      const stream = new Writable({
        write(_chunk, _encoding, done) {
          done();
        },
        final(done) {
          if (fail) done(new Error("load failed"));
          else {
            stream.emit("complete");
            done();
          }
        },
      });
      return stream;
    },
  };
  const bq = {
    dataset: () => ({ table: () => table }),
    query,
  } as unknown as import("@google-cloud/bigquery").BigQuery;
  await writeDay(bq, day, async () => data);
  const sql = query.mock.calls[0][0].query;
  expect(sql).toContain("BEGIN TRANSACTION;");
  expect(sql).toContain("COMMIT TRANSACTION;");
  expect(sql).toContain(".person_day` WHERE day=@day");
  expect(sql).toContain(".coverage` WHERE day=@day");
  expect(sql).not.toContain("raw-person");
  query.mockClear();
  fail = true;
  await expect(writeDay(bq, day, async () => data)).rejects.toThrow(
    "load failed"
  );
  expect(query).not.toHaveBeenCalled();
  expect(drop).toHaveBeenCalledTimes(2);
});
