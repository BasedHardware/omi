import { createElement } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const state = vi.hoisted(() => ({
  embed: { enabled: false } as any,
  error: undefined as Error | undefined,
}));
vi.mock("swr", () => ({
  default: () => ({
    data: state.embed,
    error: state.error,
    isLoading: false,
    mutate: vi.fn(),
  }),
}));
vi.mock("@/hooks/useAuthToken", () => ({
  useAuthToken: () => ({ token: "synthetic-admin" }),
  authenticatedFetcher: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/app/(protected)/dashboard/classic/page", () => ({
  default: () => createElement("div", null, "Native analytics"),
}));
import AnalyticsPage from "@/app/(protected)/dashboard/page";

afterEach(() => {
  cleanup();
  state.embed = { enabled: false };
  state.error = undefined;
});

it("flag-off and rollback render authenticated native analytics without a legacy iframe", async () => {
  const { container } = render(createElement(AnalyticsPage));
  expect(await screen.findByText("Native analytics")).toBeTruthy();
  expect(container.querySelector("iframe")).toBeNull();
});

it("enabled cutover renders the server-issued private Grafana URL", () => {
  state.embed = {
    enabled: true,
    url: "https://monitor.omi.me/d/omi-tv-v2?auth_token=synthetic",
    expiresAt: Date.now() + 240000,
  };
  const { container } = render(createElement(AnalyticsPage));
  expect(container.querySelector("iframe")?.getAttribute("src")).toBe(
    state.embed.url
  );
  expect(
    container.querySelector("iframe")?.getAttribute("referrerpolicy")
  ).toBe("no-referrer");
});

it("an enrollment failure offers the existing authenticated analytics route", () => {
  state.embed = undefined;
  state.error = new Error("synthetic enrollment failure");
  render(createElement(AnalyticsPage));
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(
    screen
      .getByRole("link", { name: "Open analytics dashboard" })
      .getAttribute("href")
  ).toBe("/dashboard/classic");
});
