import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  current: {} as Record<string, unknown>,
  fetcher: undefined as unknown,
  options: undefined as unknown,
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("swr", () => ({
  default: (_key: unknown, fetcher: unknown, options: unknown) => {
    state.fetcher = fetcher;
    state.options = options;
    return state.current;
  },
}));
import { GrafanaKiosk } from "@/components/dashboard/grafana-kiosk";

beforeEach(() => {
  state.current = {
    data: {
      enabled: true,
      url: "https://monitor.omi.me/d/omi-tv-v2?auth_token=old",
      expiresAt: Date.now() + 240000,
    },
    error: undefined,
    isLoading: false,
    mutate: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it.each([403, 503])(
  "removes the cached JWT iframe after renewal failure %s",
  (status) => {
    const view = render(<GrafanaKiosk token="test-link" />);
    expect(screen.getByTitle("Omi TV")).toBeTruthy();
    state.current.error = Object.assign(new Error("renewal failed"), {
      status,
    });
    view.rerender(<GrafanaKiosk token="test-link" />);
    expect(screen.queryByTitle("Omi TV")).toBeNull();
    expect(screen.getByText("TV dashboard unavailable")).toBeTruthy();
  }
);

it("shows the unavailable notice when the Business embed is disabled", () => {
  state.current.data = { enabled: false };
  render(<GrafanaKiosk token="test-link" />);
  expect(screen.queryByTitle("Omi TV")).toBeNull();
  expect(screen.getByText("TV dashboard unavailable")).toBeTruthy();
});
