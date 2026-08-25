import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Query-capture coverage for every platform-aware PostHog route the platform
 * dashboards use. The dashboard-side tests only pin URL parameters — these
 * execute each route and assert the HogQL it actually sends is scoped, so a
 * route that silently ignored `platform=` fails here (the "macOS board shows
 * all-platform DAU" class of bug).
 */

const captured: string[] = [];

vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn(async () => ({ uid: "test" })) }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: vi.fn(async () => null),
  setPayload: vi.fn(async () => undefined),
}));
vi.mock("@/lib/posthog", () => ({
  posthogResults: vi.fn(async (_h: string, _p: string, _k: string, query: string) => {
    captured.push(query);
    return [];
  }),
}));
// k-factor reads the Firestore referral ledger alongside PostHog.
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => ({
    collection: () => ({
      where: () => ({ limit: () => ({ get: async () => ({ docs: [] }) }) }),
    }),
  }),
}));

const MACOS_FILTER = "$os_name = 'macOS'";
const MOBILE_FILTER = "$os_name IN ('iOS', 'Android', 'iPadOS')";

function request(url: string) {
  return { nextUrl: new URL(`http://localhost${url}`) } as any;
}

async function capture(loadRoute: () => Promise<{ GET: (r: any) => Promise<any> }>, url: string) {
  captured.length = 0;
  vi.resetModules(); // defeat each route's module-level response cache
  const { GET } = await loadRoute();
  await GET(request(url));
  expect(captured.length).toBeGreaterThan(0);
  return [...captured];
}

function expectScoped(queries: string[], scope: "macos" | "mobile" | "all") {
  for (const q of queries) {
    if (scope === "macos") {
      expect(q).toContain(MACOS_FILTER);
      expect(q).not.toContain(MOBILE_FILTER);
    } else if (scope === "mobile") {
      expect(q).toContain(MOBILE_FILTER);
      expect(q).not.toContain(MACOS_FILTER);
    } else {
      expect(q).not.toContain(MACOS_FILTER);
      expect(q).not.toContain(MOBILE_FILTER);
    }
  }
}

beforeEach(() => {
  process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
  process.env.POSTHOG_PROJECT_ID = "1";
  process.env.POSTHOG_HOST = "https://posthog.test";
});

const ROUTES: [string, () => Promise<any>, string][] = [
  ["dau-trends", () => import("@/app/api/omi/stats/dau-trends/route"), "/api/omi/stats/dau-trends?days=30"],
  ["viral-metrics", () => import("@/app/api/omi/stats/viral-metrics/route"), "/api/omi/stats/viral-metrics?days=30"],
  ["retention", () => import("@/app/api/omi/stats/retention/posthog/route"), "/api/omi/stats/retention/posthog?days=14&intervals=10"],
];

describe.each(ROUTES)("%s route", (_name, loadRoute, baseUrl) => {
  it("scopes every query to macOS for platform=macos", async () => {
    expectScoped(await capture(loadRoute, `${baseUrl}&platform=macos`), "macos");
  });

  it("scopes every query to the mobile OS list for platform=mobile", async () => {
    expectScoped(await capture(loadRoute, `${baseUrl}&platform=mobile`), "mobile");
  });

  it("applies no OS constraint for platform=all", async () => {
    expectScoped(await capture(loadRoute, `${baseUrl}&platform=all`), "all");
  });

  it("defaults to macOS when the param is absent (legacy classic-page compat)", async () => {
    // retention predates the shared scope helper and historically defaulted
    // to all-platforms; every newer route keeps the classic /dashboard page's
    // macOS semantics when unparameterized. The boards always pass platform=.
    const queries = await capture(loadRoute, baseUrl);
    expectScoped(queries, _name === "retention" ? "all" : "macos");
  });
});

describe("k-factor route", () => {
  it("scopes client viral signals to the board's OS but never the server-emitted events", async () => {
    const queries = await capture(
      () => import("@/app/api/omi/stats/k-factor/posthog/route"),
      "/api/omi/stats/k-factor/posthog?days=30&platform=macos",
    );
    // Client-side signals (friend answer, share actions, first-seen new
    // users) carry the macOS scope…
    const friend = queries.filter((q) => q.includes("Onboarding How Did You Hear"));
    expect(friend.length).toBeGreaterThan(0);
    for (const q of friend) expect(q).toContain(MACOS_FILTER);
    expect(queries.some((q) => q.includes("min_ts") && q.includes(MACOS_FILTER))).toBe(true);
    // …while the server-emitted referral funnel and share-email events have
    // no client OS and must not be OS-filtered.
    const funnel = queries.filter((q) => q.includes("desktop_operator_month_v1"));
    expect(funnel).toHaveLength(3);
    for (const q of funnel) expect(q).not.toContain("$os_name");
  });
});

describe("dau-trends response cache", () => {
  it("never serves one platform's cached data to another", async () => {
    captured.length = 0;
    vi.resetModules();
    const { GET } = await import("@/app/api/omi/stats/dau-trends/route");
    await GET(request("/api/omi/stats/dau-trends?days=30&platform=macos"));
    const afterMacos = captured.length;
    await GET(request("/api/omi/stats/dau-trends?days=30&platform=mobile"));
    // A days-only cache key would return the macOS payload without querying.
    expect(captured.length).toBeGreaterThan(afterMacos);
    expect(captured[captured.length - 1]).toContain(MOBILE_FILTER);
  });
});

describe("releases route", () => {
  it("buckets the iOS release timeline by New York calendar day", async () => {
    // GitHub + iTunes calls are irrelevant here; the assertion is that the
    // PostHog rollout-crossing query follows the boards' NYC-day contract
    // (UTC toDate would push evening releases onto the next day).
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => [] }) as any),
    );
    try {
      const queries = await capture(
        () => import("@/app/api/omi/stats/releases/route"),
        "/api/omi/stats/releases?days=30",
      );
      const ios = queries.find((q) => q.includes("$app_version"));
      expect(ios).toBeTruthy();
      expect(ios).toContain("toTimeZone(timestamp, 'America/New_York')");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
