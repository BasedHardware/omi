import { describe, expect, it, vi } from "vitest";

import {
  MOBILE_OS_NAMES,
  parsePlatformScope,
  scopeFilterAnd,
} from "@/lib/platform-scope";

describe("parsePlatformScope", () => {
  it("accepts the two platform scopes and defaults everything else to all", () => {
    expect(parsePlatformScope("macos")).toBe("macos");
    expect(parsePlatformScope("mobile")).toBe("mobile");
    expect(parsePlatformScope("all")).toBe("all");
    expect(parsePlatformScope(null)).toBe("all");
    expect(parsePlatformScope("windows")).toBe("all");
  });
});

describe("scopeFilterAnd", () => {
  it("produces three distinct filters — the same-DAU-on-every-board bug", () => {
    const fragments = new Set(
      (["all", "macos", "mobile"] as const).map((scope) => scopeFilterAnd(scope)),
    );
    expect(fragments.size).toBe(3);
  });

  it("scopes macos to the desktop os only", () => {
    const sql = scopeFilterAnd("macos");
    expect(sql).toContain("'macOS'");
    for (const os of MOBILE_OS_NAMES) expect(sql).not.toContain(`'${os}'`);
  });

  it("scopes mobile to the mobile os list and excludes macOS", () => {
    const sql = scopeFilterAnd("mobile");
    for (const os of MOBILE_OS_NAMES) expect(sql).toContain(`'${os}'`);
    expect(sql).not.toContain("'macOS'");
  });

  it("keeps the other product out of the all scope", () => {
    expect(scopeFilterAnd("all")).toContain("cfc_");
  });

  it("supports the legacy $os column used by retention and k-factor", () => {
    expect(scopeFilterAnd("macos", "properties.$os")).toBe(
      "AND properties.$os = 'macOS'",
    );
  });
});

describe("viral-metrics platform scoping (query capture)", () => {
  it("generates disjoint HogQL per platform and anchors non-macOS cohorts on first-seen", async () => {
    vi.resetModules();
    const captured: string[] = [];
    vi.doMock("@/lib/posthog", () => ({
      posthogResults: vi.fn(async (_h: string, _p: string, _k: string, query: string) => {
        captured.push(query);
        return [];
      }),
    }));
    vi.doMock("@/lib/auth", () => ({ verifyAdmin: vi.fn(async () => ({ uid: "test" })) }));
    vi.doMock("@/lib/payload-cache", () => ({
      getPayload: vi.fn(async () => null),
      setPayload: vi.fn(),
    }));
    process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
    process.env.POSTHOG_PROJECT_ID = "1";

    const { GET } = await import("@/app/api/omi/stats/viral-metrics/route");
    const { NextRequest } = await import("next/server");

    const queriesFor = async (platform: string) => {
      captured.length = 0;
      const response = await GET(
        new NextRequest(`http://localhost/api/omi/stats/viral-metrics?days=60&platform=${platform}`),
      );
      expect(response.status).toBe(200);
      return captured.join("\n---\n");
    };

    const macos = await queriesFor("macos");
    expect(macos).toContain("= 'macOS'");
    expect(macos).toContain("Sign In Completed");

    const mobile = await queriesFor("mobile");
    expect(mobile).toContain("'iOS'");
    expect(mobile).not.toContain("= 'macOS'");
    // Mobile never emits Sign In Completed — cohorts anchor on first-seen.
    expect(mobile).not.toContain("Sign In Completed");

    const all = await queriesFor("all");
    expect(all).toContain("cfc_");
    expect(all).not.toContain("= 'macOS'");
    expect(all).not.toContain("'iOS'");
  });
});
