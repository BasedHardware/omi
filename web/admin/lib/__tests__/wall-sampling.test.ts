import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  activityQuery,
  cohortQuery,
  deviceFunnelQuery,
  mauOffsetsQuery,
  weeklyGrowthQuery,
} from "../wall-posthog";
import { SAMPLE_PCT_SQL, SAMPLE_WEIGHT_SQL } from "../posthog-sampling";

// Memory Created, Device Session Ended and Recording Started are kept for a
// stable 2% of distinct IDs since 2026-11-23 (contracts/analytics/posthog.json).
const end = new Date("2026-11-23T00:00:00Z");

describe("readers of sampled product events (SCA-3665)", () => {
  it("weights capture-only actors and counts foreground or MCP actors once", () => {
    const sql = activityQuery(end, 7, "active", 1);
    expect(sql).toContain(
      `if(countIf(cap)>0,maxIf(${SAMPLE_PCT_SQL},cap),0) cap_pct`
    );
    expect(sql).toContain("0 captures,1 fgn,0 cap_pct");
    expect(sql).toContain("sum(if(fg_any>0,1,100/pct_any))");
    expect(sql).not.toMatch(/SELECT period,p,count\(\)/);
  });

  it("weights every saved actor, since saved status is itself sampled", () => {
    expect(activityQuery(end, 7, "saved", 1)).toContain("sum(100/pct_any)");
    expect(activityQuery(end, 7, "assistant", 1)).toContain(
      "SELECT period,p,count()"
    );
  });

  it("uses the same per-actor population weight in weekly growth and activity", () => {
    const sql = weeklyGrowthQuery(end, 1);
    expect(sql).toContain("if(sum(fgn)>0,1,100/max(cap_pct)) weight");
    expect(sql).toContain("groupArray(tuple(period,primary,n,weight))");
    expect(sql).toContain("round(sum(tupleElement(t,6)))");
  });

  it("weights MAU offsets per window", () => {
    const sql = mauOffsetsQuery(end, [0, 3]);
    expect(sql).toContain(`if(fg,100,${SAMPLE_PCT_SQL}) pct`);
    expect(sql).toContain("true seen,100 pct FROM mcp_days");
    expect(sql).toContain(
      "100/arrayMax(arrayMap(s -> tupleElement(s,4),hits))"
    );
  });

  it("weights capture outcomes in cohorts and the device funnel", () => {
    expect(cohortQuery(end, 7, 1)).toContain(
      "toInt64(round(sumIf(100/capture_pct,capture>0))) captured"
    );
    const funnel = deviceFunnelQuery(end);
    expect(funnel).toContain("sumIf(100/conv1_pct,conv1)");
    expect(funnel).toContain("sumIf(100/conv7_pct,conv7)");
  });

  it("weights viral-metrics Memory Created counts", () => {
    const route = readFileSync(
      "app/api/omi/stats/viral-metrics/route.ts",
      "utf8"
    );
    expect(route).toContain("${SAMPLE_PCT_SQL} as m_pct");
    expect(route).toContain("sumIf(100 / mem_pct, memories_in_window > 0)");
    const template = route.split("// 16. Memory Created")[1].split("`")[1];
    const sql = template
      .replace("${SAMPLE_PCT_SQL}", SAMPLE_PCT_SQL)
      .replace("${SAMPLE_WEIGHT_SQL}", SAMPLE_WEIGHT_SQL)
      .replace("${os}", "")
      .replace("toDate(now()) - interval ${days} day", "'2026-11-23'")
      .replace("toDate(now())", "'2026-11-25'")
      .replace(/properties\.(\w+)/g, "$1");
    const code = `
import json, sqlite3, sys
db = sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE events (timestamp TEXT, person_id TEXT, distinct_id TEXT, event TEXT,
    omi_sample_pct REAL, memory_result TEXT, memory_discarded INTEGER);
INSERT INTO events VALUES
    ('2026-11-23 01:00:00', 'a', 'a', 'Memory Created', NULL, 'saved', NULL),
    ('2026-11-23 02:00:00', 'a', 'a', 'Memory Created', 2, 'saved', NULL),
    ('2026-11-23 03:00:00', NULL, 'b', 'Memory Created', 2, 'saved', NULL),
    ('2026-11-23 04:00:00', NULL, 'b', 'Memory Created', 2, 'saved', NULL),
    ('2026-11-23 05:00:00', NULL, 'b', 'Memory Created', NULL, 'discarded', NULL),
    ('2026-11-24 01:00:00', 'a', 'a', 'Memory Created', 2, 'saved', NULL);
""")
db.create_function("toDate", 1, lambda v: v[:10])
db.create_function("toInt64", 1, int)
db.create_function("toFloat", 1, lambda v: v)
db.create_function("greatest", 2, max)
print(json.dumps(db.execute(sys.stdin.read()).fetchall()))
`;
    const rows = execFileSync("python3", ["-c", code], {
      input: sql,
      encoding: "utf8",
    });
    expect(JSON.parse(rows)).toEqual([
      ["2026-11-23", 51, 151],
      ["2026-11-24", 50, 50],
    ]);
    expect(SAMPLE_WEIGHT_SQL).toBe(`100 / ${SAMPLE_PCT_SQL}`);
  });
});
