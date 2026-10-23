import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const state = vi.hoisted(() => ({
  scopes: [] as string[],
  urls: [] as string[],
}));

vi.mock("@/hooks/useAuthToken", () => ({
  useAuthToken: () => ({ token: "tok", loading: false }),
  authenticatedFetcher: async ([url]: [string, string]) => {
    state.urls.push(url);
    if (url.startsWith("/api/omi/apps/stats"))
      return { total: 4, approved: 3, inReview: 1, paid: 1 };
    if (url.startsWith("/api/omi/stats/conversation-count"))
      return { totalConversations: 99 };
    if (url.startsWith("/api/omi/stats/subscriptions"))
      return { totalSubscriptions: 12, monthly: 9, annual: 3, trialing: 0 };
    if (url.startsWith("/api/omi/stats/app-subscriptions"))
      return {
        totalAppSubscriptions: 5,
        uniqueCustomers: 4,
        uniquePriceIds: 2,
      };
    return {};
  },
}));
vi.mock("@/hooks/useAdminAccess", () => ({
  useAdminAccess: () => ({
    access: { uid: "u", scopes: state.scopes },
    isLoading: false,
    error: null,
    can: (scope: string) => state.scopes.includes(scope),
  }),
}));

import { DashboardStats } from "@/components/dashboard/stats";

/**
 * The subscription overview cards read finance-scoped endpoints. This
 * component sits on the Apps page (apps:read), which Support and Viewer can
 * open without finance:read — for them the two requests must not be made
 * and the cards must not render, instead of turning 403s into error cards.
 */

const FINANCE_URLS = [
  "/api/omi/stats/subscriptions",
  "/api/omi/stats/app-subscriptions",
];

beforeEach(() => {
  state.urls = [];
});

afterEach(() => {
  cleanup();
  state.scopes = [];
});

describe("DashboardStats", () => {
  it("fetches and renders only the non-finance cards without finance:read", async () => {
    state.scopes = ["apps:read"];
    render(createElement(DashboardStats));

    await screen.findByText("Conversations");
    for (const url of FINANCE_URLS) {
      expect(
        state.urls.some((u) => u.startsWith(url)),
        url
      ).toBe(false);
    }
    expect(screen.queryByText("Active OMI Subscriptions")).toBeNull();
    expect(screen.queryByText("App Subscriptions")).toBeNull();
  });

  it("fetches and renders the subscription cards with finance:read", async () => {
    state.scopes = ["apps:read", "finance:read"];
    render(createElement(DashboardStats));

    await screen.findByText("Active OMI Subscriptions");
    await screen.findByText("App Subscriptions");
    for (const url of FINANCE_URLS) {
      expect(
        state.urls.some((u) => u.startsWith(url)),
        url
      ).toBe(true);
    }
  });
});
