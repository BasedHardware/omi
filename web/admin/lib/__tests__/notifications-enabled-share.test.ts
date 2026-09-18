import { describe, expect, it, vi, beforeEach } from "vitest";

/**
 * The enabled/disabled gauge used to compute `enabled = total - disabled`,
 * which folded every user document MISSING `notifications_enabled` into the
 * enabled bucket and inflated the published share. The unknown population must
 * be its own number.
 */

let db: any;
vi.mock("@/lib/firebase/admin", () => ({ getDb: () => db }));
vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn(async () => ({ uid: "t" })) }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: vi.fn(async () => null),
  setPayload: vi.fn(async () => undefined),
  withFreshness: (data: object, freshAt: number) => ({ ...data, freshAt }),
}));
vi.mock("@/lib/posthog", () => ({
  cachedPosthogFetch: vi.fn(async () => ({ ok: true, json: async () => ({ results: [] }) })),
}));

import { computeNotifications } from "@/app/api/omi/stats/notifications/route";

type Opts = {
  enabled: number;
  disabled: number;
  total: number;
  /** Collection-group index missing -> the per-user fallback path runs. */
  collectionGroupFails?: boolean;
  mentorUserCount?: number;
};

function fakeDb(opts: Opts) {
  const emptySnap = { docs: [] as unknown[] };

  const userDoc = () => ({
    collection: () => ({ where: () => ({ get: async () => emptySnap }) }),
  });

  const usersRef: any = {
    // `.count().get()` with no filter = total users.
    count: () => ({ get: async () => ({ data: () => ({ count: opts.total }) }) }),
    doc: () => userDoc(),
    where: (field: string, _op: string, value: unknown) => {
      if (field === "notifications_enabled") {
        const count = value === true ? opts.enabled : opts.disabled;
        return { count: () => ({ get: async () => ({ data: () => ({ count }) }) }) };
      }
      // mentor_notification_frequency > 0 -> the fallback user list
      const docs = Array.from({ length: opts.mentorUserCount ?? 0 }, (_, i) => ({
        id: `u${i}`,
      }));
      return {
        select: () => ({
          limit: (n: number) => ({ get: async () => ({ docs: docs.slice(0, n) }) }),
        }),
      };
    },
  };

  return {
    collection: () => usersRef,
    collectionGroup: () => ({
      where: function () {
        return this;
      },
      get: async () => {
        if (opts.collectionGroupFails) throw new Error("index missing");
        return emptySnap;
      },
    }),
  };
}

describe("notifications enabled/disabled/unset", () => {
  beforeEach(() => {
    delete process.env.POSTHOG_PERSONAL_API_KEY;
    delete process.env.POSTHOG_PROJECT_ID;
  });

  it("counts users with no notifications_enabled field as unset, not enabled", async () => {
    db = fakeDb({ enabled: 300, disabled: 100, total: 1000 });
    const payload = await computeNotifications(2);

    expect(payload.enabledDisabled).toMatchObject({
      enabled: 300,
      disabled: 100,
      unset: 600,
      total: 1000,
    });
    // The gauge divides enabled/total; the old math published 90%.
    expect((payload.enabledDisabled.enabled / payload.enabledDisabled.total) * 100).toBe(30);
  });

  it("never reports a negative unset population", async () => {
    db = fakeDb({ enabled: 700, disabled: 500, total: 1000 });
    const payload = await computeNotifications(2);
    expect(payload.enabledDisabled.unset).toBe(0);
  });

  it("does not flag truncation when the fallback path is not used", async () => {
    db = fakeDb({ enabled: 1, disabled: 1, total: 2 });
    const payload = await computeNotifications(2);
    expect(payload.fallbackTruncated).toBe(false);
  });

  it("flags truncation when the fallback user list hits its cap", async () => {
    db = fakeDb({
      enabled: 1,
      disabled: 1,
      total: 2,
      collectionGroupFails: true,
      mentorUserCount: 5000,
    });
    const payload = await computeNotifications(2);
    expect(payload.fallbackTruncated).toBe(true);
  });

  it("does not flag truncation when the fallback list is under the cap", async () => {
    db = fakeDb({
      enabled: 1,
      disabled: 1,
      total: 2,
      collectionGroupFails: true,
      mentorUserCount: 3,
    });
    const payload = await computeNotifications(2);
    expect(payload.fallbackTruncated).toBe(false);
  });
});
