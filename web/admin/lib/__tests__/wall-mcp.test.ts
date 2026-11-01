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
  expect(sql).toContain("HAVING count()>=2");
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
