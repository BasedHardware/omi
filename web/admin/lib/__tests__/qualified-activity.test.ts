import { describe, expect, it } from "vitest";
import {
  completeWeek,
  completeWindow,
  DEFINITION_VERSION,
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
  /** Regression (David, 2026-10-22): the 2026-10-15 "real snapshot" evidence
   * recorded engagement.mau = 7,163 for [2026-09-13, 2026-10-13) from a
   * hand-built HogQL query using only the six original wire events. The wall
   * (qualified-v2-2026-10-15, commit 474c1105, shipped 12:19 UTC that day,
   * ~3h after the snapshot ran) widened the allowlist with the macOS UI events
   * (Memory List Item Clicked, search) and the mobile UI events (tab/list
   * clicks, action items, fact search); the same window under the shipped
   * definition is 9,665 (+35%). A snapshot or reproduction query built from a
   * reduced event set silently redefines MAU. This test pins the shipped
   * inventory and requires the definition version to move with any change. */
  it("pins the full v2 event inventory so MAU cannot silently narrow", () => {
    expect(DEFINITION_VERSION).toBe("qualified-v2-2026-10-15");
    // The three event families that produced the 7,163 → 9,665 gap.
    for (const event of [
      "Memory List Item Clicked",
      "Search Result Opened",
      "Conversation Opened From Search",
      "Conversation List Item Clicked",
      "Live Transcript Card Clicked",
      "Bottom Navigation Tab Clicked",
      "Action Item Completed",
      "Fact List Item Clicked",
      "Fact Searched",
      "Conversation Detail Search Query Entered",
      "Daily Summary Detail Viewed",
    ])
      expect(QUALIFIED_EVENT_NAMES).toContain(event);
    // The original six wire/saved events stay qualified.
    for (const event of [
      "question_asked",
      "Chat Message Sent",
      "floating_bar_query_sent",
      "Conversation Action",
      "Phone Mic Recording Started",
      "Memory Created",
    ])
      expect(QUALIFIED_EVENT_NAMES).toContain(event);
    // Every query that counts people must scan every allowlisted event: a
    // hand-built reproduction using a subset is the exact 10-15 failure.
    const sql = activityQuery(new Date("2026-10-15"), 30, "active", 1);
    for (const event of QUALIFIED_EVENT_NAMES)
      expect(sql).toContain(`'${event}'`);
  });
});
