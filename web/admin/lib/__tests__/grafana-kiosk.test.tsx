import { createElement } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const state = vi.hoisted(() => ({
  embed: undefined as any,
  error: undefined as Error | undefined,
  config: undefined as any,
}));
vi.mock("swr", () => ({
  default: (_key: unknown, _fetcher: unknown, config: any) => {
    // Expose config for assertions; data/error drive the renders.
    state.config = config;
    return {
      data: state.embed,
      error: state.error,
      isLoading: false,
      mutate: vi.fn(),
    };
  },
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

import { GrafanaKiosk } from "@/components/dashboard/grafana-kiosk";

afterEach(() => {
  cleanup();
  state.embed = undefined;
  state.error = undefined;
  vi.useRealTimers();
});

beforeEach(() => {
  vi.useFakeTimers();
});

it("renders the private embed while renewal succeeds", () => {
  state.embed = {
    enabled: true,
    url: "https://monitor.omi.me/d/omi-tv-v2?kiosk=",
    expiresAt: Date.now() + 240_000,
  };
  const { container } = render(
    createElement(GrafanaKiosk, { token: "t".repeat(43) })
  );
  const frame = container.querySelector("iframe");
  expect(frame?.getAttribute("src")).toContain("monitor.omi.me/d/omi-tv-v2");
});

it("shows the honest notice over a stale embed when renewal fails", () => {
  // Codex P1: stale embed must not win over a cached renewal error.
  state.embed = {
    enabled: true,
    url: "https://monitor.omi.me/d/omi-tv-v2?kiosk=",
    expiresAt: Date.now() - 1,
  };
  state.error = new Error("renewal failed");
  const { container } = render(
    createElement(GrafanaKiosk, { token: "t".repeat(43) })
  );
  expect(container.querySelector("iframe")).toBeNull();
  expect(screen.getByText("TV dashboard unavailable")).toBeTruthy();
});

it("shows the notice when the Business embed is disabled", () => {
  state.embed = { enabled: false };
  const { container } = render(
    createElement(GrafanaKiosk, { token: "t".repeat(43) })
  );
  expect(container.querySelector("iframe")).toBeNull();
  expect(screen.getByText("TV dashboard unavailable")).toBeTruthy();
});
