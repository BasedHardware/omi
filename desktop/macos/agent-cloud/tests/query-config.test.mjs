import { describe, expect, it } from "vitest";

import { ALLOWED_TOOLS, RESEARCHER_TOOLS, buildAgentDefinitions } from "../query-config.mjs";

describe("query-config", () => {
  it("restricts the researcher to the omi-tools data tools", () => {
    const { researcher } = buildAgentDefinitions("schema-here");
    expect(researcher.tools).toEqual([
      "mcp__omi-tools__execute_sql",
      "mcp__omi-tools__semantic_search",
      "mcp__omi-tools__get_daily_recap",
      "mcp__omi-tools__get_app_usage",
    ]);
    expect(researcher.tools).toEqual(RESEARCHER_TOOLS);
    // No shell, file, or browser access from the researcher.
    for (const name of researcher.tools) {
      expect(name).toMatch(/^mcp__omi-tools__/);
    }
  });

  it("embeds the database schema in the researcher prompt", () => {
    const schema = "screenshots:\n  timestamp TEXT\n  (600000 rows)";
    const { researcher } = buildAgentDefinitions(schema);
    expect(researcher.prompt).toContain(schema);
    // Measured (2026-07-21): haiku researcher is fastest and ~3x cheaper than
    // inherited Opus with equal-or-better accuracy on real data.
    expect(researcher.model).toBe("haiku");
    // One recap call covers a range — pins the fix for the observed
    // call-once-per-day pathology (12-turn runs).
    expect(researcher.prompt).toContain("ONE call covers any date range");
  });

  it("includes Task in the main allowed tools so subagents are invocable", () => {
    expect(ALLOWED_TOOLS).toContain("Task");
  });
});
