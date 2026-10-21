import { describe, expect, it, vi, beforeEach } from "vitest";

/**
 * Staleness/silent-failure honesty: a payload must carry the age of the data it
 * publishes, a bucket with no observations must not read as a real zero, and a
 * date key must be computed in the same timezone the upstream bucketed in.
 */

vi.mock("@/lib/auth", () => ({
  verifyAdmin: vi.fn(async () => ({ uid: "t" })),
}));

const fetchMock = vi.fn();
const posthogResultsMock = vi.hoisted(() =>
  vi.fn(async (): Promise<any[]> => [])
);
vi.mock("@/lib/posthog", () => ({
  cachedPosthogFetch: (...args: unknown[]) => fetchMock(...args),
  posthogResults: posthogResultsMock,
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
  it("keeps today's bucket when successive clock reads advance", () => {
    const RealDate = Date;
    const instant = RealDate.parse("2026-09-05T23:22:00.000Z");
    let reads = 0;
    class AdvancingDate extends RealDate {
      constructor(value?: string | number | Date) {
        super(
          value === undefined
            ? instant + reads++
            : value instanceof RealDate
            ? value.getTime()
            : value
        );
      }
    }
    vi.stubGlobal("Date", AdvancingDate);
    try {
      const series = buildDateSeries(
        3,
        { "2026-09-05": 5 },
        { "2026-09-05": 100 }
      );
      expect(series).toHaveLength(4);
      expect(series.at(-1)).toEqual({
        date: "2026-09-05",
        crashes: 5,
        users: 100,
        crashFreeRate: 95,
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });

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
  it("distinguishes a real all-downvote 0 from an unmeasurable day", async () => {
    const { aggregateRatedMessages } = await import(
      "@/app/api/omi/stats/message-ratings/route"
    );
    const { data, daily } = aggregateRatedMessages([
      {
        createdAt: "2026-08-02T12:00:00.000Z",
        rating: -1,
        messageSource: "desktop_chat",
        continuityKey: null,
      },
      {
        createdAt: "2026-08-03T12:00:00.000Z",
        rating: 1,
        messageSource: "desktop_chat",
        continuityKey: null,
      },
    ]);

    // All-downvotes -> a real 0. A day with no ratings at all produces no
    // point (absence), never a fake 0. These must differ.
    expect(data.find((p) => p.date === "2026-08-02")!.ratio).toBe(0);
    expect(data.find((p) => p.date === "2026-08-03")!.ratio).toBe(100);
    expect(daily.find((p) => p.date === "2026-08-01")).toBeUndefined();
    // Lanes with no observations stay null, not 0.
    expect(daily.find((p) => p.date === "2026-08-03")!.voice).toBeNull();
  });
});
