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

it("keeps an explicitly available legacy board while the flag is off", () => {
  state.current.data = { enabled: false, legacy: true };
  render(<GrafanaKiosk token="test-link" />);
  expect(screen.getByTitle("Omi TV")).toBeTruthy();
});

it("retries transient failures with bounds and stops capability rejection", async () => {
  render(<GrafanaKiosk token="test-link" />);
  const fetcher = state.fetcher as (key: [string, string]) => Promise<unknown>;
  const options = state.options as {
    shouldRetryOnError: (error: unknown) => boolean;
    errorRetryCount: number;
    errorRetryInterval: number;
  };
  expect(options.errorRetryCount).toBe(3);
  expect(options.errorRetryInterval).toBe(5000);
  for (const status of [400, 401, 403, 503]) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status }))
    );
    const failure = await fetcher(["/api/grafana/tv-embed", "test-link"]).catch(
      (error) => error
    );
    expect(options.shouldRetryOnError(failure)).toBe(status === 503);
  }
});
