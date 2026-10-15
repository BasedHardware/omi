import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { wallPayload, resetWallCache } from "../wall-cache";
import {
  emptyWallMetrics,
  computeWall,
  type WallPayload,
} from "../wall-metrics";
import { queryPosthog, periodQueries } from "../wall-posthog";
import { WallSourceError } from "../wall-source-error";
import { wallPresentation } from "../wall-presentation";
const now = new Date("2026-10-15T12:00Z");
function payload(): WallPayload {
  const metrics = Object.values(emptyWallMetrics());
  Object.assign(metrics[0], {
    value: 42,
    status: "proxy",
    sourceRefreshedAt: now.toISOString(),
    dataThrough: "2026-10-14",
  });
  return {
    definitionVersion: "test",
    retryableFailures: 0,
    generatedAt: now.toISOString(),
    metrics,
    partial: true,
  };
}
beforeEach(() => {
  resetWallCache();
  vi.useFakeTimers();
  vi.setSystemTime(now);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
it("bounds a 24-panel cold burst and retains exactly one refresh until it completes", async () => {
  let finish!: (value: WallPayload) => void;
  const compute = vi.fn(
    () =>
      new Promise<WallPayload>((resolve) => {
        finish = resolve;
      })
  );
  const retain = vi.fn();
  const reads = Array.from({ length: 24 }, () =>
    wallPayload(now, compute, retain)
  );
  await vi.advanceTimersByTimeAsync(5000);
  const pending = await Promise.all(reads);
  expect(compute).toHaveBeenCalledTimes(1);
  expect(retain).toHaveBeenCalledTimes(1);
  expect(
    pending.every(
      (p) => p.refreshing && p.metrics.every((m) => m.value === null)
    )
  ).toBe(true);
  finish(payload());
  await retain.mock.calls[0][0];
  expect((await wallPayload(new Date(), compute)).metrics[0].value).toBe(42);
  expect(compute).toHaveBeenCalledTimes(1);
});
it("serves the previous good payload during refresh, including midnight, without restamping it", async () => {
  const p = payload();
  const compute = vi
    .fn()
    .mockResolvedValueOnce(p)
    .mockImplementation(() => new Promise(() => {}));
  await wallPayload(now, compute);
  vi.setSystemTime(new Date("2026-10-16T00:00Z"));
  const results = await Promise.all([
    wallPayload(new Date(), compute),
    wallPayload(new Date(), compute),
  ]);
  expect(compute).toHaveBeenCalledTimes(2);
  expect(results[0]).toMatchObject({ refreshing: true, cacheStale: true });
  expect(results[0].metrics[0].sourceRefreshedAt).toBe(now.toISOString());
  expect(
    wallPresentation(results[0], new Date()).tiles.growth_wau
  ).toMatchObject({ state: "STALE", value: 42 });
});
it("does not replace last good data with an all-source failure or spin a retry storm", async () => {
  const p = payload();
  const failed = { ...p, metrics: Object.values(emptyWallMetrics()) };
  const compute = vi.fn().mockResolvedValueOnce(p).mockResolvedValue(failed);
  const retain = vi.fn();
  await wallPayload(now, compute, retain);
  vi.advanceTimersByTime(16 * 60_000);
  await wallPayload(new Date(), compute, retain);
  await retain.mock.calls[1][0];
  const old = await wallPayload(new Date(), compute, retain);
  expect(old.metrics[0].value).toBe(42);
  expect(old.cacheStale).toBe(true);
  expect(old.refreshError).toContain("sources failed");
  expect(compute).toHaveBeenCalledTimes(2);
});
it("splits a query-time-limited pair and keeps bucket offsets and the oldest source watermark", async () => {
  const query = vi.fn(async (sql: string) => {
    if (sql.endsWith("/2"))
      throw new WallSourceError(
        "PostHog execution time limit exceeded (HTTP 504)",
        true
      );
    return Object.assign([[0, "macos", 7]], {
      sourceRefreshedAt: sql.startsWith("2026-10-15")
        ? now.toISOString()
        : "2026-10-15T11:00:00Z",
    });
  });
  const rows = await periodQueries(
    query,
    (end, n) => `${end.toISOString()}/${n}`,
    now,
    7,
    2
  );
  expect([...rows]).toEqual([
    [0, "macos", 7],
    [1, "macos", 7],
  ]);
  expect(rows.sourceRefreshedAt).toBe("2026-10-15T11:00:00Z");
});
it("retries rate limits but exposes only safe actual reasons, never upstream bodies", async () => {
  vi.stubEnv("POSTHOG_PERSONAL_API_KEY", "test-key");
  vi.stubEnv("POSTHOG_PROJECT_ID", "test");
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "secret=do-not-show" }), {
        status: 429,
      })
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [[0, "macos", 2]] }))
    );
  vi.stubGlobal("fetch", fetch);
  const work = queryPosthog("SELECT 1");
  await vi.advanceTimersByTimeAsync(1000);
  expect((await work)[0][2]).toBe(2);
  expect(JSON.parse(fetch.mock.calls[0][1].body).refresh).toBe("blocking");
  fetch.mockResolvedValue(
    new Response(JSON.stringify({ detail: "secret=do-not-show" }), {
      status: 400,
    })
  );
  await expect(queryPosthog("SELECT 1")).rejects.toThrow(
    "PostHog query rejected (HTTP 400)"
  );
});
it("names the PostHog failure on every dependent null tile and in its card", async () => {
  const error = new WallSourceError(
    "PostHog execution time limit exceeded (HTTP 504)"
  );
  const fail = async () => {
    throw error;
  };
  const p = await computeWall(
    { query: fail, shopify: fail, stripe: fail, billing: fail },
    now
  );
  const view = wallPresentation(p, now);
  expect(view.tiles.activation_rate).toMatchObject({ footnote: error.message });
  expect(
    String((view.tiles.activation_rate as { cardSvg: string }).cardSvg)
  ).toContain("HTTP 504");
  expect(
    String((view.tiles.activation_rate as { cardSvg: string }).cardSvg)
  ).not.toContain("Source data not available");
});

it("retries partial transient source failures on the next poll instead of freezing nulls for 15m", async () => {
  const p = { ...payload(), retryableFailures: 1 };
  const compute = vi.fn().mockResolvedValue(p);
  await wallPayload(now, compute);
  vi.advanceTimersByTime(30_001);
  await wallPayload(new Date(), compute);
  expect(compute).toHaveBeenCalledTimes(2);
});
