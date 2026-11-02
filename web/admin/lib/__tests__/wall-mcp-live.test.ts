import { it, expect } from "vitest";
import { activityQuery, queryPosthog } from "../wall-posthog";
import { responseReliabilityQueries } from "../response-reliability";
import {
  LEGACY_FALLBACK_EXHAUSTED_QUERY,
  LEGACY_FALLBACK_TRIAGE_QUERY,
} from "../telemetry/fallback-triage";
import { MCP_MARKER_STATUS_ROW, MCP_SUCCESS_SELECT } from "../wall-mcp";
import {
  DESKTOP_HEALTH_EVENT_WEIGHT_SQL,
  desktopHealthEventWeightSql,
} from "../telemetry/desktop-health-sampling";
const end = new Date("2026-10-15");
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "MCP activity compiles with the production aggregate engine",
  async () => {
    for (const days of [1, 7, 30]) {
      const rows = await queryPosthog(activityQuery(end, days, "active", 1));
      expect(rows.length).toBeGreaterThan(0);
      process.stdout.write(JSON.stringify({ days, rows: [...rows] }) + "\n");
    }
  },
  360000
);
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "real HogQL enforces UTC MCP days, cadence and app/MCP overlap on literal fixtures",
  async () => {
    const calls: [string, string, string, string, string][] = [];
    const add = (
      actor: string,
      at: string,
      initiator = "user",
      client = "claude_desktop",
      tool = "get_conversations"
    ) => calls.push([actor, at, client, tool, initiator]);
    add("app-and-mcp", "2026-10-14 00:01:00");
    add("app-and-mcp", "2026-10-14 00:02:00");
    add("mcp-only", "2026-10-14 03:01:00", "unknown");
    add("mcp-only", "2026-10-14 03:05:00", "unknown");
    add("single", "2026-10-14 04:00:00");
    add("scheduled", "2026-10-14 04:01:00", "scheduled_agent");
    add("scheduled", "2026-10-14 04:02:00", "scheduled_agent");
    add("split-day", "2026-10-13 23:59:59");
    add("split-day", "2026-10-14 00:00:00");
    for (const actor of ["periodic", "mixed-stream"])
      for (let i = 0; i < 10; i++)
        add(
          actor,
          new Date(Date.parse("2026-10-14T00:00Z") + i * 900000)
            .toISOString()
            .slice(0, 19)
            .replace("T", " "),
          "unknown",
          "python_sdk"
        );
    for (const offset of [
      0, 60, 900, 1800, 1900, 4200, 7800, 8000, 9000, 10800,
    ])
      add(
        "interactive",
        new Date(Date.parse("2026-10-14T10:00Z") + offset * 1000)
          .toISOString()
          .slice(0, 19)
          .replace("T", " ")
      );
    add("multi-client", "2026-10-14 15:00:00", "user", "cursor");
    add("multi-client", "2026-10-14 15:01:00", "unknown", "codex");
    add("mixed-stream", "2026-10-14 17:01:00", "user", "cursor");
    add("mixed-stream", "2026-10-14 17:05:00", "user", "cursor");
    add("simultaneous", "2026-10-14 20:00:00");
    add("simultaneous", "2026-10-14 20:00:00");
    const literal = (v: string) => `'${v}'`;
    const raw = calls
      .map(
        ([actor, at, client, tool, initiator]) =>
          `SELECT ${literal(actor)} AS person_id,${literal(
            actor
          )} AS distinct_id,
          toDateTime('${at}','UTC') AS timestamp,'MCP Tool Use Succeeded' AS event,
          ${literal(
            JSON.stringify({ client, tool, initiator, schema_version: 2 })
          )} AS properties`
      )
      .join(" UNION ALL ");
    const production = activityQuery(end, 1, "active", 1);
    // Execute the exact production SELECT against event-shaped literal rows.
    // Pre-projecting a client column hid the client_name/emitter mismatch.
    const suffix = production.slice(production.indexOf("mcp_eligible AS"));
    expect(production).toContain(`SELECT ${MCP_SUCCESS_SELECT}`);
    const mcp = `mcp_raw AS (SELECT ${MCP_SUCCESS_SELECT} FROM (${raw}) fixture_events),${suffix}`;
    const app =
      "SELECT 'app-and-mcp' AS actor,'macos' AS p,0 AS period,1 AS days,toDateTime('2026-10-14 20:00:00','UTC') AS latest,0 AS captures";
    const rows = await queryPosthog(`WITH app_pd AS (${app}),${mcp}`);
    const actual = Object.fromEntries(
      rows
        .filter((r) => r[1] !== MCP_MARKER_STATUS_ROW)
        .map((r) => [r[1], Number(r[2])])
    );
    expect(actual).toEqual({ macos: 1, integrations: 5 });
    expect(rows.every((r) => Number(r[3]) === calls.length)).toBe(true);
    const streamCtes = mcp.slice(0, mcp.indexOf(",\n  mcp_days AS"));
    const streams = await queryPosthog(
      `WITH ${streamCtes} SELECT client,unattended FROM mcp_streams WHERE actor='mixed-stream' ORDER BY client`
    );
    expect([...streams]).toEqual([
      ["cursor", 0],
      ["python_sdk", 1],
    ]);
    process.stdout.write(
      JSON.stringify({
        fixture: "MCP literal rows",
        people: actual,
        markerRows: calls.length,
      }) + "\n"
    );
  },
  360000
);
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "real HogQL sampling weight preserves history and applies at the exact UTC cutover",
  async () => {
    const times = [
      "2026-10-21 23:59:59",
      "2026-10-22 00:00:00",
      "2026-10-22 00:00:01",
      "2026-10-22 01:00:00",
    ];
    const expressions = times.map((at) =>
      desktopHealthEventWeightSql("2026-10-22T00:00:00Z").replace(
        /\btimestamp\b/g,
        `toDateTime('${at}','UTC')`
      )
    );
    const rows = await queryPosthog(`SELECT ${expressions.join(",")} LIMIT 1`);
    expect([...rows]).toEqual([[1, 10, 10, 10]]);
    const unarmed = await queryPosthog(
      `SELECT ${DESKTOP_HEALTH_EVENT_WEIGHT_SQL} LIMIT 1`
    );
    expect([...unarmed]).toEqual([[1]]);
    const weights = rows[0].map(Number);
    expect(weights.reduce((s, n) => s + n, 0)).toBe(31);
    expect(weights[0] + weights[1] + weights[3]).toBe(21);
    expect(4000 * weights[0] + 4000 * weights[1] + 8000 * weights[3]).toBe(
      124000
    );
    process.stdout.write(
      JSON.stringify({
        fixture: "sampling boundary weights",
        rows: [...rows],
      }) + "\n"
    );
  },
  180000
);
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "production health sampling readers compile against real source columns",
  async () => {
    for (const query of [
      responseReliabilityQueries(1).voice,
      LEGACY_FALLBACK_EXHAUSTED_QUERY,
      LEGACY_FALLBACK_TRIAGE_QUERY,
    ]) {
      const rows = await queryPosthog(
        `SELECT sum(event_count) FROM (${query}) sampled LIMIT 1`
      );
      expect(rows.length).toBe(1);
      process.stdout.write(
        JSON.stringify({ healthReaderCount: rows[0][0] }) + "\n"
      );
    }
  },
  360000
);
