// Opt-in, read-only aggregate smoke check for the v3 series queries.
// Logs only aggregate counts and timings; no identities leave HogQL.
import { it, expect } from "vitest";
import {
  activityQuery,
  mauOffsetsQuery,
  queryPosthog,
  retentionCurveQuery,
  weeklyGrowthQuery,
} from "../wall-posthog";
import { shiftDay, utcDay } from "../qualified-activity";

const live = process.env.OMI_TV_LIVE_CHECK !== "1";
const end = utcDay(new Date());
async function timed(name: string, sql: string) {
  const started = Date.now();
  const rows = await queryPosthog(sql);
  console.info(name, `${(Date.now() - started) / 1000}s`, JSON.stringify(rows));
  return rows;
}

it.skipIf(live)(
  "weekly growth people equal the snapshot activity query for the same periods",
  async () => {
    const [growth, snapshot] = await Promise.all([
      timed("growth", weeklyGrowthQuery(end, 2)),
      timed("snapshot", activityQuery(end, 7, "active", 2)),
    ]);
    const people = (rows: unknown[][], period: number) =>
      rows
        .filter((r) => r[0] === period && !String(r[1]).startsWith("__"))
        .reduce((s, r) => s + Number(r[2]), 0);
    for (const period of [0, 1])
      expect(people(growth, period)).toBe(people(snapshot, period));
  },
  600_000
);

it.skipIf(live)(
  "MAU offsets and the retention curve compile and return aggregates",
  async () => {
    const [mau, snapshot] = await Promise.all([
      timed("mau", mauOffsetsQuery(end, [0, 1])),
      timed("mau-snapshot", activityQuery(end, 30, "active", 1)),
    ]);
    expect(Number(mau.find((r) => r[0] === 0)?.[1])).toBe(
      snapshot
        .filter((r) => r[0] === 0 && !String(r[1]).startsWith("__"))
        .reduce((s, r) => s + Number(r[2]), 0)
    );
    const curve = await timed(
      "curve",
      retentionCurveQuery(shiftDay(end, -7), 2, end)
    );
    expect(curve.length).toBeGreaterThan(0);
  },
  600_000
);
