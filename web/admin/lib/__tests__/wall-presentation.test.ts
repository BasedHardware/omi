import { expect, it, vi } from "vitest";
import { computeWall } from "../wall-metrics";
import { wallPresentation } from "../wall-presentation";
import { localWallFixture } from "../wall-local-fixture";
const fail = async () => {
  throw new Error("missing");
};
it("keeps missing values null, dims stale data, and calculates the previous-period delta", async () => {
  const now = new Date("2026-10-15T12:00Z");
  const data = await computeWall(
    {
      query: async () =>
        Object.assign(
          [
            [0, "macos", 3],
            [1, "macos", 2],
          ],
          { sourceRefreshedAt: "2026-10-15T11:59Z" }
        ),
      shopify: fail,
      stripe: fail,
      billing: fail,
    },
    now
  );
  const fresh = wallPresentation(data, now);
  expect(fresh.tiles.growth_wau).toMatchObject({
    value: 3,
    delta: 50,
    macos: "3",
  });
  const old = wallPresentation(data, new Date("2027-01-01"));
  expect(old.tiles.growth_wau).toMatchObject({
    state: "STALE",
    valueColor: "#8190a6",
  });
  expect(old.tiles.health_crash_free).toMatchObject({
    value: null,
    state: "UNAVAILABLE",
  });
});
it("uses same-cutoff fixture MRR / qualified MAU", async () => {
  const now = new Date("2026-10-15T12:00Z");
  const data = await computeWall(
    {
      query: async () =>
        Object.assign([[0, "macos", 10]], {
          sourceRefreshedAt: "2026-10-15T11:59Z",
        }),
      shopify: fail,
      billing: fail,
      stripe: async () => ({
        usd: 100,
        partial: false,
        unsupportedItems: 0,
        unmappedProducts: 0,
        fixture: true,
        dataThrough: "2026-10-14",
        sourceRefreshedAt: "2026-10-15T11:59Z",
      }),
    },
    now
  );
  expect(data.metrics.find((m) => m.id === "revenue.arpmau")?.value).toBe(10);
  expect(wallPresentation(data, now).tiles.revenue_arpmau).toMatchObject({
    state: "FIXTURE",
    value: 10,
  });
});
it("refuses fixture mode in production before reading any file", async () => {
  vi.stubEnv("OMI_TV_LOCAL_FIXTURE_PATH", "/must-not-be-read");
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("DEV_BYPASS_AUTH", "1");
  try {
    await expect(localWallFixture()).rejects.toThrow("development auth bypass");
  } finally {
    vi.unstubAllEnvs();
  }
});

it("keeps absent refresh metadata dim with human copy", async () => {
  const now = new Date("2026-10-15T12:00Z");
  const data = await computeWall(
    {
      query: async () => [[0, "macos", 3]],
      shopify: fail,
      stripe: fail,
      billing: fail,
    },
    now
  );
  expect(data.metrics[0].sourceRefreshedAt).toBeNull();
  expect(wallPresentation(data, now).tiles.growth_wau).toMatchObject({
    state: "STALE",
    valueColor: "#8190a6",
    value: 3,
  });
});
