import { createElement } from "react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SWRConfig } from "swr";

const state = vi.hoisted(() => ({
  scopes: [] as string[],
  localAgent: false,
  urls: [] as string[],
}));

vi.mock("@/hooks/useAuthToken", () => ({
  useAuthToken: () => ({ token: "tok", loading: false }),
  authenticatedFetcher: async ([url]: [string, string]) => {
    state.urls.push(url);
    return fixtureFor(url);
  },
  useAuthFetch: () => ({ fetchWithAuth: vi.fn(), token: "tok" }),
}));
vi.mock("@/hooks/useAdminAccess", () => ({
  useAdminAccess: () => ({
    access: { uid: "u", scopes: state.scopes },
    isLoading: false,
    error: null,
    can: (scope: string) => state.scopes.includes(scope),
  }),
}));
vi.mock("@/hooks/useLocalAgent", () => ({
  useLocalAgentEnabled: () => state.localAgent,
}));
vi.mock("@/components/dashboard/agent-prompt-widget", () => ({
  AgentPromptWidget: () => null,
}));
vi.mock("@/components/dashboard/response-reliability-summary", () => ({
  useResponseReliabilityItems: () => [],
}));

import AnalyticsPage from "@/app/(protected)/dashboard/classic/page";

/**
 * The classic dashboard is the fallback for members without finance:read
 * (the Grafana Business board refuses them), so it must not fetch the
 * finance endpoints or render their tiles for those viewers — no $0 KPIs,
 * no tiles stuck on "Loading".
 */

function fixtureFor(url: string): Record<string, unknown> {
  if (url.startsWith("/api/omi/stats/revenue"))
    return { mrr: 4200, arr: 50400, partial: false };
  if (url.startsWith("/api/omi/stats/mrr-trends"))
    return {
      data: [
        { month: "2026-09", mrr: 4000 },
        { month: "2026-10", mrr: 4200 },
      ],
    };
  if (url.startsWith("/api/omi/stats/subscription-trends"))
    return { data: [{ month: "2026-10", monthly: 3, annual: 1 }] };
  if (url.startsWith("/api/omi/stats/subscriptions"))
    return { totalSubscriptions: 12, monthly: 9, annual: 3 };
  if (url.startsWith("/api/omi/stats/conversation-count"))
    return { totalConversations: 999 };
  if (url.startsWith("/api/omi/stats/activation")) return { weeks: [] };
  if (url.startsWith("/api/omi/stats/viral-metrics"))
    return {
      summary: { dau: 10, wau: 20, mau: 30, dauMau: 33, quickRatio: 1.2 },
      growthAccounting: [],
      powerUserCurve: [],
      stickinessTrend: [],
      activation: [],
    };
  if (url.startsWith("/api/omi/stats/k-factor/posthog"))
    return { available: false };
  if (url.startsWith("/api/omi/stats/daily-new-users"))
    return {
      totalUsers: 100,
      data: [{ date: "2026-10-01", users: 5, cumulative: 100 }],
    };
  if (url.startsWith("/api/omi/stats/profitability"))
    return {
      summary: {
        totalUsersDesktop: 60,
        totalUsersMobile: 40,
        totalNewDesktop: 6,
        totalNewMobile: 4,
        avgCostPerUserDesktop: 0.012,
        avgCostPerUserMobile: 0.02,
        partial: false,
      },
      users: [],
      revenue: [],
      cost: [],
      costPerUser: [],
      conversion: [],
    };
  if (url.startsWith("/api/omi/stats/infra-costs"))
    return {
      breakdown: [
        {
          service: "GCP",
          mtdUsd: 100,
          aprProjectionUsd: 100,
          desktopProjectionUsd: 60,
          mobileProjectionUsd: 40,
        },
      ],
      summary: {
        assumptions: {
          overheadMonthlyUsd: 0,
          desktopShare: 0.6,
          mobileShare: 0.4,
        },
      },
    };
  return {};
}

const FINANCE_URLS = [
  "/api/omi/stats/revenue",
  "/api/omi/stats/mrr-trends",
  "/api/omi/stats/subscription-trends",
  "/api/omi/stats/subscriptions",
  "/api/omi/stats/profitability",
  "/api/omi/stats/infra-costs",
];

beforeAll(() => {
  // recharts measures its containers; jsdom has neither observer.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

beforeEach(() => {
  state.urls = [];
});

/** Each mount gets its own SWR cache, so tests cannot serve each other's requests. */
function mountPage() {
  return render(
    createElement(
      SWRConfig,
      { value: { provider: () => new Map() } },
      createElement(AnalyticsPage)
    )
  );
}

afterEach(() => {
  cleanup();
  state.scopes = [];
  state.localAgent = false;
});

describe("the classic dashboard without finance:read", () => {
  it("fetches no finance endpoint and renders no finance tiles", async () => {
    state.scopes = ["analytics:read", "apps:read", "content:read"];
    mountPage();

    // The page finished loading analytics data…
    await screen.findByText("Conversations");
    await vi.waitFor(() =>
      expect(state.urls.some((u) => u.includes("conversation-count"))).toBe(
        true
      )
    );
    // …without ever requesting a finance endpoint.
    for (const url of FINANCE_URLS) {
      expect(
        state.urls.some((u) => u.startsWith(url)),
        url
      ).toBe(false);
    }
    // And without rendering their tiles.
    for (const title of [
      "MRR",
      "ARR",
      "Subscriptions",
      "Revenue Overview",
      "Profitability by Platform",
      "Infra cost by service — last 30 days",
      "Total Users (macOS)",
    ]) {
      expect(screen.queryByText(title), title).toBeNull();
    }
    // The analytics the viewer does have still render.
    expect(screen.getByText("Analytics Dashboard")).toBeTruthy();
    expect(screen.getByText("macOS Growth Metrics")).toBeTruthy();
    // content:read holders keep the chat ratings section ("By Week" is its
    // grouping toggle; the section header and the analytics message-ratings
    // widget share other names).
    expect(
      state.urls.some((u) => u.startsWith("/api/omi/chat-lab/ratings"))
    ).toBe(true);
    expect(screen.getAllByText("By Week").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Chat Ratings").length).toBeGreaterThan(0);
  });
});

describe("the classic dashboard without content:read", () => {
  it("fetches no chat ratings endpoint and renders no ratings section", async () => {
    // Finance holds analytics:read + finance:read but not content:read; on
    // this fallback dashboard their chat-ratings widget must hide rather
    // than render 403s as zero totals. The analytics message-ratings
    // widget (analytics:read) stays.
    state.scopes = ["analytics:read", "finance:read"];
    mountPage();

    await screen.findByText("Conversations");
    expect(
      state.urls.some((u) => u.startsWith("/api/omi/chat-lab/ratings"))
    ).toBe(false);
    expect(screen.queryAllByText("By Week")).toHaveLength(0);
    expect(screen.queryAllByText("Chat Ratings")).toHaveLength(0);
  });
});

describe("the classic dashboard with finance:read", () => {
  it("fetches the finance endpoints and renders their tiles", async () => {
    state.scopes = ["analytics:read", "finance:read"];
    mountPage();

    await screen.findByText("Infra cost by service — last 30 days");
    for (const url of FINANCE_URLS) {
      expect(
        state.urls.some((u) => u.startsWith(url)),
        url
      ).toBe(true);
    }
    for (const title of [
      "MRR",
      "ARR",
      "Subscriptions",
      "Revenue Overview",
      "Profitability by Platform",
      "Total Users (macOS)",
    ]) {
      expect(screen.getByText(title), title).toBeTruthy();
    }
  });
});

describe("the local agent card", () => {
  it("appears only while the server reports the endpoint enabled", async () => {
    state.scopes = ["analytics:read"];
    state.localAgent = true;
    const { unmount } = mountPage();
    await screen.findByText("Customize this dashboard");
    unmount();

    state.localAgent = false;
    mountPage();
    await screen.findByText("Conversations");
    expect(screen.queryByText("Customize this dashboard")).toBeNull();
  });
});
