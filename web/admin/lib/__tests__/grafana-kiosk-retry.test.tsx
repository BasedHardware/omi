import React from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SWRProvider } from "@/components/swr-provider";
import { GrafanaKiosk } from "@/components/dashboard/grafana-kiosk";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));
const fetchMock = vi.fn();
beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
async function mountKiosk() {
  await act(async () => {
    render(
      <SWRProvider>
        <GrafanaKiosk token="retry-test-link" />
      </SWRProvider>
    );
  });
}
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}
function validEmbed() {
  return Response.json({
    enabled: true,
    url: "https://monitor.omi.me/d/omi-tv-v2?auth_token=fixture",
    expiresAt: Date.now() + 66000,
  });
}

it("removes a failed renewal frame and schedules capped exponential retries under SWRProvider", async () => {
  fetchMock.mockImplementation(async () => new Response(null, { status: 503 }));
  fetchMock.mockImplementationOnce(async () => validEmbed());
  await mountKiosk();
  expect(screen.getByTitle("Omi TV")).toBeTruthy();
  await advance(6000);
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.queryByTitle("Omi TV")).toBeNull();
  const delays = [15000, 30000, 60000, 120000, 240000, 480000, 480000];
  for (let index = 0; index < delays.length; index++) {
    const delay = delays[index];
    const retry = index + 1;
    await advance(delay - 1);
    expect(fetchMock).toHaveBeenCalledTimes(retry + 1);
    await advance(1);
    expect(fetchMock).toHaveBeenCalledTimes(retry + 2);
  }
  await advance(30000);
  expect(fetchMock).toHaveBeenCalledTimes(9);
});

it("never retries a revoked capability under SWRProvider", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 403 }));
  await mountKiosk();
  expect(screen.getByText("TV dashboard unavailable")).toBeTruthy();
  await advance(30000);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByTitle("Omi TV")).toBeNull();
});
