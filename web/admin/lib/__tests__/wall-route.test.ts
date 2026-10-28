import { beforeEach, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { computeWall } from "../wall-metrics";
vi.mock("@/lib/auth", async () => {
  const { testIdentity } = await import("./support/test-identity");
  return { requireScope: vi.fn().mockResolvedValue(testIdentity()) };
});
vi.mock("@/lib/wall-cache", () => ({
  wallPayload: vi.fn(),
  wallSnapshotStore: () => undefined,
}));
vi.mock("@/lib/wall-local-fixture", () => ({
  localWallFixture: vi.fn(async () => null),
}));
import { requireScope } from "../auth";
import { wallPayload } from "../wall-cache";
import { GET } from "@/app/api/omi/stats/wall/route";
import { testIdentity } from "./support/test-identity";
const fail = async () => {
  throw new Error("source unavailable");
};
beforeEach(() => vi.clearAllMocks());
it("retains admin authorization", async () => {
  vi.mocked(requireScope).mockResolvedValue(
    NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  );
  expect(
    (await GET(new NextRequest("http://localhost/api/omi/stats/wall"))).status
  ).toBe(401);
  expect(wallPayload).not.toHaveBeenCalled();
});
it("all source failures yield 502 with every metric null and a reason", async () => {
  vi.mocked(requireScope).mockResolvedValue(testIdentity(undefined, "test"));
  vi.mocked(wallPayload).mockResolvedValue(
    await computeWall({
      query: fail,
      shopify: fail,
      stripe: fail,
      billing: fail,
    })
  );
  const response = await GET(
    new NextRequest("http://localhost/api/omi/stats/wall")
  );
  expect(response.status).toBe(502);
  const p = await response.json();
  expect(
    p.metrics.every(
      (m: { value: unknown; reason: string }) => m.value === null && m.reason
    )
  ).toBe(true);
  expect(p.tiles.growth_wau.value).toBeNull();
});
it("partial fixtures preserve source timestamps and return usable aggregates", async () => {
  vi.mocked(requireScope).mockResolvedValue(testIdentity(undefined, "test"));
  const p = await computeWall({
    query: async () => [[0, "macos", 3]],
    shopify: fail,
    stripe: fail,
    billing: fail,
  });
  const refreshed = p.metrics[0].sourceRefreshedAt;
  vi.mocked(wallPayload).mockResolvedValue(p);
  const response = await GET(
    new NextRequest("http://localhost/api/omi/stats/wall")
  );
  expect(response.status).toBe(200);
  const data = await response.json();
  expect(data.metrics[0].sourceRefreshedAt).toBe(refreshed);
  expect(data.partial).toBe(true);
  expect(data.tiles.growth_wau.value).toBe(3);
  expect(response.headers.get("Cache-Control")).toBe("private, no-store");
});
it("returns loading cards with 200 while a cold refresh is retained", async () => {
  vi.mocked(requireScope).mockResolvedValue(testIdentity(undefined, "test"));
  vi.mocked(wallPayload).mockResolvedValue({
    ...(await computeWall({
      query: fail,
      shopify: fail,
      stripe: fail,
      billing: fail,
    })),
    refreshing: true,
  });
  const response = await GET(
    new NextRequest("http://localhost/api/omi/stats/wall")
  );
  expect(response.status).toBe(200);
  expect((await response.json()).refreshing).toBe(true);
});
