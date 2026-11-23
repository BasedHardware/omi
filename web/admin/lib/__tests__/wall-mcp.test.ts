import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { computeWall } from "../wall-metrics";
import { wallPresentation } from "../wall-presentation";
import { activityQuery } from "../wall-posthog";
import {
  MCP_ACTIVITY_VERSION,
  MCP_MARKER_MISSING,
  MCP_MARKER_STATUS_ROW,
} from "../wall-mcp";
const now = new Date("2026-10-15T12:00Z");
const fail = async () => {
  throw new Error("fixture source absent");
};
async function wall(markerRows: number, mcpOnly: number) {
  return computeWall(
    {
      query: async (sql) =>
        Object.assign(
          sql.includes("mcp_raw")
            ? [
                [0, "macos", 3, markerRows],
                [0, "ios", 2, markerRows],
                ...(mcpOnly ? [[0, "integrations", mcpOnly, markerRows]] : []),
              ]
            : [],
          { sourceRefreshedAt: now.toISOString() }
        ),
      shopify: fail,
      stripe: fail,
      billing: fail,
    },
    now
  );
}
it("adds the disjoint MCP-only bucket once and presents it as a fourth activity split", async () => {
  const p = await wall(12, 4);
  for (const id of ["growth.wau", "engagement.dau", "engagement.mau"]) {
    const m = p.metrics.find((m) => m.id === id)!;
    expect(m.value).toBe(9);
    expect(m.split).toEqual({ macos: 3, mobile: 2, other: 0, mcp: 4 });
    expect(
      Object.values(m.split).reduce<number>((s, n) => s + (n || 0), 0)
    ).toBe(m.value);
    expect(m.definitionVersion).toBe(MCP_ACTIVITY_VERSION);
  }
  const view = wallPresentation(p, now);
  expect(view.tiles.growth_wau).toMatchObject({ mcp: "4" });
  expect(
    String((view.tiles.growth_wau as { cardSvg: string }).cardSvg)
  ).toContain("MCP-only");
  expect(
    p.metrics.find((m) => m.id === "engagement.saved_creators")?.split.mcp
  ).toBeUndefined();
});
it("distinguishes a missing marker from a deployed marker with zero qualifying people", async () => {
  const missing = wallPresentation(await wall(0, 0), now).tiles.growth_wau;
  expect(missing).toMatchObject({
    value: 5,
    mcp: "—",
    mcpReason: MCP_MARKER_MISSING,
  });
  expect((missing as { footnote: string }).footnote).toContain(
    MCP_MARKER_MISSING
  );
  expect(
    wallPresentation(await wall(1, 0), now).tiles.growth_wau
  ).toMatchObject({ value: 5, mcp: "0" });
});
it("pins v2 per-success input, UTC day threshold and app-first attribution", () => {
  const sql = activityQuery(new Date("2026-10-15"), 7);
  expect(sql).toContain("MCP Tool Use Succeeded");
  expect(sql).toContain("properties.schema_version))=2");
  expect(sql).toContain("initiator IN ('user','unknown')");
  expect(sql).toContain("intDiv(toUnixTimestamp(timestamp),86400)");
  expect(sql).toContain("HAVING sum(calls)>=2");
  expect(sql).toContain("ORDER BY (p!='integrations') DESC");
  expect(sql).not.toContain("MCP Tool Call");
  expect(sql).not.toContain("MCP Active");
  for (const kind of ["saved", "assistant"] as const)
    expect(activityQuery(new Date("2026-10-15"), 1, kind)).not.toContain(
      "mcp_raw"
    );
});

it("reads the schema-2 emitter's closed properties rather than diagnostic client_name", () => {
  const emitter = readFileSync("../../backend/utils/mcp_analytics.py", "utf8")
    .split("def emit_mcp_tool_use_succeeded(")[1]
    .split("def schedule_mcp_tool_call(")[0];
  const properties = emitter.split("properties={")[1].split("},")[0];
  const keys = Array.from(properties.matchAll(/^\s*"([^"]+)":/gm)).map(
    (m) => m[1]
  );
  expect(keys.sort()).toEqual([
    "$process_person_profile",
    "client",
    "initiator",
    "op_type",
    "schema_version",
    "source_platform",
    "surface",
    "tool",
  ]);
  const raw = activityQuery(new Date("2026-10-15"), 1)
    .split("mcp_raw AS (")[1]
    .split("FROM events")[0];
  expect(
    Array.from(raw.matchAll(/JSONExtractString\(properties,'(\w+)'\)/g))
      .map((m) => m[1])
      .sort()
  ).toEqual(["client", "initiator", "tool"]);
  expect(raw).not.toContain("client_name");
  for (const [, key] of Array.from(
    raw.matchAll(/JSONExtractString\(properties,'(\w+)'\)/g)
  ))
    expect(keys).toContain(key);
});

it("carries marker presence without letting a status-only row enter any period's counts", async () => {
  const p = await computeWall(
    {
      query: async (sql) =>
        Object.assign(
          sql.includes("mcp_raw") ? [[-1, MCP_MARKER_STATUS_ROW, 0, 1]] : [],
          { sourceRefreshedAt: now.toISOString() }
        ),
      shopify: fail,
      stripe: fail,
      billing: fail,
    },
    now
  );
  for (const id of ["growth.wau", "engagement.dau", "engagement.mau"]) {
    const m = p.metrics.find((m) => m.id === id)!;
    expect(m.value).toBeNull();
    expect(m.prev).toBeNull();
    expect(m.split.mcp).toBe(0);
    expect(m.mcpReason).not.toBe(MCP_MARKER_MISSING);
  }
});

it("falls back to the server's daily rollup only where raw rows are absent (SCA-3665)", () => {
  const sql = activityQuery(new Date("2026-10-15"), 7);
  expect(sql).toContain("event='MCP Daily Activity'");
  expect(sql).toContain("properties.schema_version))=1");
  // Snapshots for the last day arrive after it ends: read one day past the window.
  expect(sql).toContain("timestamp < toDateTime('2026-10-16 00:00:00', 'UTC')");
  expect(sql).toContain("1 prio FROM mcp_raw_stats");
  expect(sql).toContain("0 prio FROM mcp_roll_stats");
  // The source with more qualifying calls wins (raw on a tie), so the day the
  // raw stream is switched off mid-day reads the complete rollup.
  expect(sql).toContain("argMax(c,tuple(c,prio)) calls");
  // A snapshot of only scheduled-agent calls still proves the marker is live.
  expect(sql).toContain(
    "toFloatOrZero(JSONExtractString(properties,'raw_calls')) > 0"
  );
  expect(sql).not.toContain(
    "toFloatOrZero(JSONExtractString(properties,'calls')) > 0"
  );
  // The largest cumulative snapshot of a day is the one read.
  expect(sql).toContain("argMax(calls,tuple(raw_calls,timestamp))");
  // The marker survives the raw stream being switched off.
  expect(sql).toContain(
    "SELECT actor FROM mcp_raw UNION ALL SELECT actor FROM mcp_rollup_raw"
  );
  expect(sql).toContain("(SELECT count() FROM mcp_marker)");
});

it("reads every property the backend rollup snapshot emits", () => {
  const source = readFileSync("../../backend/utils/mcp_daily_rollup.py", "utf8")
    .split("def snapshot_properties(")[1]
    .split("def flush_due(")[0];
  const emitted = Array.from(source.matchAll(/^\s*"([a-z_]+)":/gm)).map(
    (m) => m[1]
  );
  const sql = activityQuery(new Date("2026-10-15"), 7);
  for (const key of [
    "utc_day",
    "client",
    "raw_calls",
    "calls",
    "positive_gaps",
    "sum_gap_s",
    "sum_gap_sq_s",
    "span_s",
    "dominant_tool_calls",
    "last_call_s",
  ]) {
    expect(emitted).toContain(key);
    expect(sql).toContain(`JSONExtractString(properties,'${key}')`);
  }
});
