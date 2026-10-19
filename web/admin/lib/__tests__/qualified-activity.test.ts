import { describe, expect, it } from "vitest";
import {
  completeWeek,
  completeWindow,
  entryPlatform,
  EXCLUSIONS_SQL,
  FOREGROUND_SQL,
  freshness,
  primaryPlatform,
  QUALIFIED_ALLOWLIST,
  QUALIFIED_EVENT_NAMES,
  SAVED_CAPTURE_SQL,
} from "../qualified-activity";
import { activityQuery, cohortQuery, establishedQuery } from "../wall-posthog";

describe("qualified activity v2", () => {
  it("uses completed UTC periods across local midnight and Monday", () => {
    const now = new Date("2026-10-12T01:00:00+07:00");
    expect(completeWindow(7, now).end.toISOString()).toBe(
      "2026-10-11T00:00:00.000Z"
    );
    expect(completeWeek(now).start.toISOString()).toBe(
      "2026-09-28T00:00:00.000Z"
    );
    expect(
      completeWeek(new Date("2026-10-12T00:00Z")).start.toISOString()
    ).toBe("2026-10-05T00:00:00.000Z");
  });
  it("ranks distinct dates then recency then fixed platform order", () => {
    expect(
      primaryPlatform([
        { platform: "ios", at: "2026-10-01T00:00Z" },
        { platform: "ios", at: "2026-10-01T01:00Z" },
        { platform: "macos", at: "2026-10-02T00:00Z" },
      ])
    ).toBe("macos");
    expect(
      primaryPlatform([
        { platform: "ios", at: "2026-10-01T00:00Z" },
        { platform: "macos", at: "2026-10-01T00:00Z" },
      ])
    ).toBe("macos");
    expect(primaryPlatform([])).toBe("unknown");
  });
  it("keeps entry attribution independent from later outcome activity", () => {
    expect(
      entryPlatform([
        { platform: "android", at: "2026-10-02T00:00Z" },
        { platform: "web", at: "2026-10-01T00:00Z" },
      ])
    ).toBe("web");
    expect(entryPlatform([])).toBe("unknown");
  });
  it("guards each audited surface and excludes auto-open/onboarding/MCP", () => {
    expect(QUALIFIED_EVENT_NAMES).not.toContain("MCP Active");
    expect(QUALIFIED_EVENT_NAMES).not.toContain("Action Items Page Opened");
    expect(QUALIFIED_EVENT_NAMES).not.toContain("Search Opened");
    expect(QUALIFIED_ALLOWLIST.web.foreground).toEqual([]);
    expect(QUALIFIED_ALLOWLIST.windows.saved).toEqual([]);
    expect(FOREGROUND_SQL).toContain("onboarding");
    expect(FOREGROUND_SQL).toContain("'Home','Tasks','Chat','Chat Voice'");
    expect(FOREGROUND_SQL).toContain("properties.source IS NULL");
    expect(SAVED_CAPTURE_SQL).toContain("properties.memory_id IS NOT NULL");
    expect(SAVED_CAPTURE_SQL).toContain("memory_result = 'saved'");
  });
  it("excludes probe aliases before aggregation and shares the definitions in all queries", () => {
    for (const sql of [
      activityQuery(new Date("2026-10-15"), 7),
      cohortQuery(new Date("2026-10-15"), 37),
      establishedQuery(new Date("2026-10-12")),
    ]) {
      expect(sql).toContain(EXCLUSIONS_SQL);
      expect(sql).toContain(FOREGROUND_SQL);
      expect(sql).toContain(SAVED_CAPTURE_SQL);
    }
    expect(cohortQuery(new Date("2026-10-15"), 7)).toContain(
      "argMinIf(p,tuple(timestamp,"
    );
    expect(cohortQuery(new Date("2026-10-15"), 7)).toContain(
      "first_event >= a"
    );
  });
  it("does not refresh stale source metadata on cache reads", () => {
    const now = new Date("2026-10-15T12:00Z");
    expect(
      freshness("2026-10-15T10:59Z", "2026-10-14", "hourly", now).stale
    ).toBe(true);
    expect(
      freshness("2026-10-15T11:59Z", "2026-10-12", "settled", now).stale
    ).toBe(true);
    expect(
      freshness("2026-10-15T11:59Z", "2026-10-13", "settled", now).stale
    ).toBe(false);
    expect(freshness(null, null, "daily", now).stale).toBe(true);
  });
});
