import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const state = vi.hoisted(() => ({
  scopes: [] as string[],
  plan: undefined as string | undefined,
  // Stable identity: the page's effect keys off fetchWithAuth, so a new
  // function per render would restart the fetch loop forever.
  fetchWithAuth: async (url: string) => {
    if (url.includes("flagged")) {
      return {
        ok: true,
        json: async () => ({ users: [{ uid: "u1", stage: "warning" }] }),
      };
    }
    return {
      ok: true,
      json: async () => ({
        uid: "u1",
        state: { stage: "warning" },
        events: [],
        profile: {
          email: "user@example.com",
          name: "User",
          ...(state.plan ? { subscription_plan: state.plan } : {}),
        },
      }),
    };
  },
}));

vi.mock("@/hooks/useAuthToken", () => ({
  useAuthFetch: () => ({ token: "tok", fetchWithAuth: state.fetchWithAuth }),
}));
vi.mock("@/hooks/useAdminAccess", () => ({
  useAdminAccess: () => ({
    access: { uid: "u", scopes: state.scopes },
    isLoading: false,
    error: null,
    can: (scope: string) => state.scopes.includes(scope),
  }),
}));

import FairUsePage from "@/app/(protected)/dashboard/fair-use/page";

/**
 * subscription_plan is a financial field: the wall strips it from the
 * fair-use user-detail response for callers without finance:read. The
 * detail page must show that as restricted — never fall back to a
 * confident "basic" tier the data does not support.
 */

async function openUserDetail() {
  render(createElement(FairUsePage));
  fireEvent.click(await screen.findByRole("button", { name: "View" }));
  await screen.findByText("User Fair Use Detail");
}

beforeEach(() => {
  state.scopes = [];
  state.plan = undefined;
});

afterEach(() => {
  cleanup();
});

describe("the fair-use plan row", () => {
  it("reads as Restricted without finance:read, never 'basic'", async () => {
    state.scopes = ["users:read"];
    // The wall stripped subscription_plan from the profile.
    await openUserDetail();
    expect(screen.getByText("Restricted")).toBeTruthy();
    expect(screen.queryByText("basic")).toBeNull();
  });

  it("shows the real plan to a finance:read viewer", async () => {
    state.scopes = ["users:read", "finance:read"];
    state.plan = "unlimited";
    await openUserDetail();
    expect(screen.getByText("unlimited")).toBeTruthy();
    expect(screen.queryByText("Restricted")).toBeNull();
  });

  it("keeps the basic fallback for a finance:read viewer with no plan", async () => {
    state.scopes = ["users:read", "finance:read"];
    await openUserDetail();
    expect(screen.getByText("basic")).toBeTruthy();
  });
});
