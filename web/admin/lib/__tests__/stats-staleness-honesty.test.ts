import { describe, expect, it, vi, beforeEach } from "vitest";

/**
 * Staleness/silent-failure honesty: a payload must carry the age of the data it
 * publishes, a bucket with no observations must not read as a real zero, and a
 * date key must be computed in the same timezone the upstream bucketed in.
 */

vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn(async () => ({ uid: "t" })) }));

const fetchMock = vi.fn();
vi.mock("@/lib/posthog", () => ({
  cachedPosthogFetch: (...args: unknown[]) => fetchMock(...args),
  posthogResults: vi.fn(async () => []),
  POSTHOG_SERVED_MAX_ROWS: 50_000,
}));

vi.mock("@/lib/firebase/admin", () => ({
  default: { firestore: { FieldPath: { documentId: () => "id" } } },
  getDb: () => ({}),
}));

import { withFreshness } from "@/lib/payload-cache";
import { buildDateSeries } from "@/app/api/omi/stats/crash-rate/route";
import { toGrafanaActivationPayload } from "@/lib/activation-compat";
import { computeMacosVersions } from "@/app/api/omi/stats/macos-versions/route";

describe("activation payload", () => {
  it("keeps erroredUsers alongside the rate it shrank", () => {
    const payload = toGrafanaActivationPayload({
      rate: 0.5,
      signups: 10,
      activated: 5,
      weeks: [],
      erroredUsers: 4,
    } as never);
    expect(payload.erroredUsers).toBe(4);
  });

  it("reports 0 errored users rather than omitting the field", () => {
    const payload = toGrafanaActivationPayload({
      rate: 0.5,
      signups: 10,
      activated: 5,
      weeks: [],
    } as never);
    expect(payload.erroredUsers).toBe(0);
  });
});

describe("macos-versions payload", () => {
  it("bakes no human date label in at compute time", async () => {
    process.env.POSTHOG_PERSONAL_API_KEY = "k";
    process.env.POSTHOG_PROJECT_ID = "1";
    const payload = await computeMacosVersions("macos");
    // A frozen cached payload must not claim to be from today; the label is
    // derived at serve time from freshAt instead.
    expect(payload).not.toHaveProperty("date");
    expect(payload.truncated).toBe(false);
  });
});

describe("withFreshness", () => {
  it("stamps the payload with the age of the data, not the time of the request", () => {
    const stamped = withFreshness({ activeUsers: 3 }, 1_700_000_000_000);
    expect(stamped).toEqual({ activeUsers: 3, freshAt: 1_700_000_000_000 });
  });

  it("does not mutate the cached payload it stamps", () => {
    const cached = { activeUsers: 3 };
    withFreshness(cached, 1);
    expect(cached).not.toHaveProperty("freshAt");
  });

  it("keeps a stale cache hit distinguishable from a fresh compute", () => {
    const staleAt = Date.now() - 7 * 86_400_000;
    const stale = withFreshness({ mrr: 100 }, staleAt);
    const fresh = withFreshness({ mrr: 100 }, Date.now());
    expect(fresh.freshAt - stale.freshAt).toBeGreaterThan(6 * 86_400_000);
  });
});

describe("crash-rate date keys", () => {
  it("builds UTC date keys so they join with PostHog's toDate() buckets", () => {
    const series = buildDateSeries(2, {}, {});
    const expected = new Date().toISOString().slice(0, 10);
    expect(series[series.length - 1].date).toBe(expected);
    for (const point of series) {
      expect(point.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it("joins counts onto the UTC day PostHog reported them under", () => {
    const today = new Date().toISOString().slice(0, 10);
    const series = buildDateSeries(3, { [today]: 5 }, { [today]: 100 });
    const point = series.find((p) => p.date === today);
    expect(point).toBeDefined();
    expect(point!.crashes).toBe(5);
    expect(point!.users).toBe(100);
    expect(point!.crashFreeRate).toBe(95);
  });
});

describe("message-ratings ratio", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    process.env.POSTHOG_PERSONAL_API_KEY = "k";
    process.env.POSTHOG_PROJECT_ID = "1";
  });

  it("reports null, not 0, on a day with no ratings at all", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          ["2026-08-01", 0, 0],
          ["2026-08-02", 0, 4],
          ["2026-08-03", 3, 1],
        ],
      }),
    });

    const { GET } = await import("@/app/api/omi/stats/message-ratings/route");
    const url = "https://admin.omi.me/api/omi/stats/message-ratings?days=7";
    const res = await GET({
      url,
      nextUrl: new URL(url),
    } as never);
    const body = await res.json();

    // No ratings -> unmeasurable. All-downvotes -> a real 0. These must differ.
    expect(body.data[0].ratio).toBeNull();
    expect(body.data[1].ratio).toBe(0);
    expect(body.data[2].ratio).toBe(75);
  });
});
