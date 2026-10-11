import { NextRequest, NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET as firstRun } from "@/app/api/omi/stats/onboarding/mobile/route";
import { GET as tutorial } from "@/app/api/omi/stats/onboarding/mobile/tutorial/route";
import { GET as attach } from "@/app/api/omi/stats/onboarding/mobile/attach/route";
import { PostHogError } from "@/lib/mobile-onboarding-funnel";

const mocks = vi.hoisted(() => ({
  verifyAdmin: vi.fn(),
  getPayload: vi.fn(),
  setPayload: vi.fn(),
  compute: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ verifyAdmin: mocks.verifyAdmin }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: mocks.getPayload,
  setPayload: mocks.setPayload,
  MAX_PRECOMPUTED_AGE_MS: 10800000,
  withFreshness: (data: object, freshAt: number) => ({ ...data, freshAt }),
}));
vi.mock("@/lib/mobile-onboarding-funnel", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/mobile-onboarding-funnel")>()),
  computeMobileOnboarding: mocks.compute,
}));
const request = (query = "") =>
  new NextRequest(`https://admin.test/api/omi/stats/onboarding/mobile${query}`);
beforeEach(() => {
  vi.clearAllMocks();
  mocks.verifyAdmin.mockResolvedValue({ uid: "admin" });
  mocks.getPayload.mockResolvedValue(null);
  mocks.setPayload.mockResolvedValue(undefined);
  mocks.compute.mockResolvedValue({
    days: 30,
    totalUsers: 2,
    methodology: "Completion, not views",
    truncated: false,
  });
});
afterEach(() => vi.restoreAllMocks());

describe("mobile onboarding HTTP routes", () => {
  it.each([
    [firstRun, "first-run"],
    [tutorial, "tutorial"],
    [attach, "attach"],
  ] as const)("isolates endpoint kind and cache key", async (get, kind) => {
    const response = await get(request());
    expect(response.status).toBe(200);
    expect(mocks.compute).toHaveBeenCalledWith(kind, 30);
    expect(mocks.getPayload).toHaveBeenCalledWith(
      `onboarding:mobile:v1:${kind}:30`,
      { maxAgeMs: 10800000 }
    );
    expect(mocks.setPayload).toHaveBeenCalledWith(
      `onboarding:mobile:v1:${kind}:30`,
      expect.objectContaining({ totalUsers: 2 })
    );
    expect(await response.json()).toMatchObject({
      totalUsers: 2,
      freshAt: expect.any(Number),
    });
  });
  it("honors auth before reading cached data", async () => {
    mocks.verifyAdmin.mockResolvedValue(
      NextResponse.json({ error: "Forbidden" }, { status: 403 })
    );
    expect((await firstRun(request())).status).toBe(403);
    expect(mocks.getPayload).not.toHaveBeenCalled();
    expect(mocks.compute).not.toHaveBeenCalled();
  });
  it("returns freshness from cache without fetching PostHog", async () => {
    mocks.getPayload.mockResolvedValue({
      data: { totalUsers: 4 },
      freshAt: 1234,
    });
    expect(await (await attach(request("?days=90"))).json()).toEqual({
      totalUsers: 4,
      freshAt: 1234,
    });
    expect(mocks.compute).not.toHaveBeenCalled();
  });
  it.each(["0", "366", "-1", "NaN", "1.5", "30%20OR%201=1", ""])(
    "rejects invalid days %s",
    async (days) => {
      expect((await firstRun(request(`?days=${days}`))).status).toBe(400);
      expect(mocks.getPayload).not.toHaveBeenCalled();
    }
  );
  it("maps a PostHog failure to 502 and never caches it", async () => {
    mocks.compute.mockRejectedValue(new PostHogError(504));
    const response = await tutorial(request());
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ error: "PostHog API error: 504" });
    expect(mocks.setPayload).not.toHaveBeenCalled();
  });
  it("reports missing configuration", async () => {
    mocks.compute.mockRejectedValue(
      new Error("PostHog credentials not configured")
    );
    expect(await (await firstRun(request())).json()).toEqual({
      error: "PostHog credentials not configured",
    });
  });
});
