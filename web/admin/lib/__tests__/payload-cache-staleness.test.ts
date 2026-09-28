import { beforeEach, describe, expect, it, vi } from "vitest";

// The staleness bound: a consumer that passes maxAgeMs must never be served a
// doc older than it. This is the class-level guard for the Aug-25 incident —
// a legacy cache key no active writer maintained was served as live data for
// ~4 weeks precisely because cache reads had no age bound.

const snapMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => ({
    collection: () => ({ doc: () => ({ get: snapMock }) }),
  }),
}));

import { MAX_PRECOMPUTED_AGE_MS, getPayload } from "@/lib/payload-cache";

const HOUR = 60 * 60 * 1000;
const KEY = "profitability:v1:30:0.2:0.2";

function docWith(payload: unknown, freshAt: number | undefined) {
  return {
    exists: true,
    data: () => ({ payload: JSON.stringify(payload), freshAt }),
  };
}

beforeEach(() => {
  snapMock.mockReset();
});

describe("getPayload maxAgeMs bound", () => {
  it("returns a doc younger than the bound", async () => {
    const freshAt = Date.now() - HOUR;
    snapMock.mockResolvedValue(docWith({ days: 30 }, freshAt));

    await expect(
      getPayload(KEY, { maxAgeMs: MAX_PRECOMPUTED_AGE_MS })
    ).resolves.toEqual({
      data: { days: 30 },
      freshAt,
    });
  });

  it("treats a doc past the bound as a miss — the frozen-legacy-key shape", async () => {
    // 4h old against the 3h bound: the precompute cron stopped writing this
    // key (legacy params), so its doc is frozen and must not be served.
    snapMock.mockResolvedValue(docWith({ days: 30 }, Date.now() - 4 * HOUR));

    await expect(
      getPayload(KEY, { maxAgeMs: MAX_PRECOMPUTED_AGE_MS })
    ).resolves.toBeNull();
  });

  it("treats a doc with no freshAt stamp as stale under a bound", async () => {
    snapMock.mockResolvedValue(docWith({ days: 30 }, undefined));

    await expect(
      getPayload(KEY, { maxAgeMs: MAX_PRECOMPUTED_AGE_MS })
    ).resolves.toBeNull();
  });

  it("keeps the any-age serve for consumers that pass no bound", async () => {
    const freshAt = Date.now() - 30 * 24 * HOUR;
    snapMock.mockResolvedValue(docWith({ days: 30 }, freshAt));

    await expect(getPayload(KEY)).resolves.toEqual({
      data: { days: 30 },
      freshAt,
    });
  });

  it("returns null for a missing doc", async () => {
    snapMock.mockResolvedValue({ exists: false, data: () => ({}) });

    await expect(
      getPayload(KEY, { maxAgeMs: MAX_PRECOMPUTED_AGE_MS })
    ).resolves.toBeNull();
  });
});
