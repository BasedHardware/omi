import { expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { computeWall } from "../wall-metrics";
import { wallPresentation } from "../wall-presentation";
import { activityQuery, weeklyGrowthQuery } from "../wall-posthog";
import {
  MCP_ACTIVITY_VERSION,
  MCP_MARKER_MISSING,
  MCP_MARKER_STATUS_ROW,
  mcpDailyReconciliationQuery,
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
  expect(sql).toContain("JSONExtractInt(properties,'schema_version')=2");
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

it("prefers the daily rollup when it covers more qualifying calls (SCA-3665)", () => {
  const sql = activityQuery(new Date("2026-10-15"), 7);
  expect(sql).toContain("event='MCP Daily Activity'");
  expect(sql).toContain("JSONExtractInt(properties,'schema_version')=1");
  // Snapshots for the last day arrive after it ends: read one day past the window.
  expect(sql).toContain("timestamp < toDateTime('2026-10-16 00:00:00', 'UTC')");
  expect(sql).toContain("1 prio FROM mcp_raw_stats");
  expect(sql).toContain("0 prio FROM mcp_roll_stats");
  // The source with more qualifying calls wins (raw on a tie), so the day the
  // raw stream is switched off mid-day reads the complete rollup.
  expect(sql).toContain("argMax(c,tuple(c,prio)) calls");
  // A snapshot of only scheduled-agent calls still proves the marker is live.
  expect(sql).toContain("JSONExtractInt(properties,'raw_calls') > 0");
  expect(sql).not.toContain("JSONExtractInt(properties,'calls') > 0");
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
    const type = key === "client" || key === "utc_day" ? "String" : "Int";
    expect(sql).toContain(`JSONExtract${type}(properties,'${key}')`);
  }
});

it("uses the rollup success timestamp for daily and weekly reader windows", () => {
  const end = new Date("2026-11-24T00:00:00Z");
  const latestFromSuccess =
    "toDateTime(JSONExtractInt(properties,'last_call_s')) latest";
  const daily = activityQuery(end, 7);
  const weekly = weeklyGrowthQuery(end, 1);

  expect(daily).toContain(latestFromSuccess);
  expect(daily).toContain("dateDiff('second',mcp_days.latest,");
  expect(weekly).toContain(latestFromSuccess);
  expect(weekly).toContain("groupUniqArray(mcp_days.utc_day) ds");
  expect(weekly).toContain("dateDiff('second',mcp_days.latest,");
});

it.skipIf(process.env.OMI_TV_CLICKHOUSE_FIXTURE !== "1")(
  "reconciles a complete UTC day with numeric snapshots and no raw fallback",
  () => {
    const day = new Date("2026-11-23T00:00:00Z");
    const raw = (actor: string, time: string, initiator = "user") =>
      [
        actor,
        time,
        "MCP Tool Use Succeeded",
        { schema_version: 2, client: "codex", initiator, tool: "get_memories" },
      ] as const;
    const snapshot = (
      actor: string,
      utc_day: string,
      time: string,
      calls: number,
      raw_calls: number
    ) =>
      [
        actor,
        time,
        "MCP Daily Activity",
        {
          schema_version: 1,
          utc_day,
          client: "codex",
          calls,
          raw_calls,
          positive_gaps: Math.max(0, calls - 1),
          sum_gap_s: 60,
          sum_gap_sq_s: 3600,
          span_s: 60,
          dominant_tool_calls: calls,
          last_call_s: Date.parse(`${utc_day}T05:01:00Z`) / 1000,
        },
      ] as const;
    const events = [
      raw("interactive", "2026-11-23 05:00:00"),
      raw("interactive", "2026-11-23 05:01:00"),
      raw("scheduled", "2026-11-23 06:00:00", "scheduled_agent"),
      snapshot("interactive", "2026-11-23", "2026-11-23 05:00:30", 1, 1),
      snapshot("interactive", "2026-11-23", "2026-11-24 00:01:00", 2, 2),
      snapshot("scheduled", "2026-11-23", "2026-11-24 00:01:00", 0, 1),
      snapshot("next-day", "2026-11-24", "2026-11-24 06:00:00", 4, 4),
    ];
    function run(source: "raw" | "rollup", input: typeof events) {
      const fixture = input
        .map(
          ([id, time, event, props]) =>
            `SELECT '${id}' person_id,'${id}' distinct_id,toDateTime('${time}','UTC') timestamp,
          '${event}' event,'${JSON.stringify(props)}' properties`
        )
        .join(" UNION ALL ");
      // Expand the two HogQL-only property shortcuts for literal JSON in ClickHouse.
      const sql = mcpDailyReconciliationQuery(day, source)
        .replace(
          /^WITH /,
          `WITH events AS (${fixture}),
`
        )
        .replaceAll("toFloat(", "toFloat64(")

        .replace(
          /properties\.(uid|user_id)/g,
          "JSONExtractString(properties,'$1')"
        );
      return execFileSync(
        "docker",
        [
          "run",
          "--rm",
          "-i",
          "--entrypoint",
          "clickhouse",
          "clickhouse/clickhouse-server:25.8-alpine",
          "local",
          "--output-format",
          "TSV",
        ],
        { input: sql, encoding: "utf8", timeout: 30_000 }
      )
        .trim()
        .split("	")
        .map(Number);
    }
    const rawResult = run("raw", events);
    expect(rawResult).toEqual([3, 1, 2]);
    expect(run("rollup", events)).toEqual(rawResult);
    // Leave the raw stream present but remove only the settled snapshot.
    expect(
      run(
        "rollup",
        events.filter((r) => r !== events[4])
      )
    ).toEqual([2, 0, 1]);
  },
  90_000
);
