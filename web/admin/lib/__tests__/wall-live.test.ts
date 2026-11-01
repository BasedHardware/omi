// Opt-in, read-only aggregate smoke check. No credentials or customer rows logged.
import { it, expect, vi } from "vitest";
import {
  activityQuery,
  cohortQuery,
  establishedQuery,
  queryPosthog,
  periodQueries,
} from "../wall-posthog";
import { fetchShopifyWeek } from "../wall-shopify";
import { completeWeek, isoDay } from "../qualified-activity";
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "live sources compile qualified aggregate queries",
  async () => {
    const end = new Date("2026-10-15");
    for (const query of [
      activityQuery(end, 1),
      activityQuery(end, 1, "assistant"),
      activityQuery(end, 30, "active", 2),
      ...([0, 2, 7, 37] as const).map((m) => cohortQuery(end, m)),
      establishedQuery(completeWeek(end).end),
    ]) {
      const rows = await queryPosthog(query);
      console.info("PostHog source refresh watermark:", rows.sourceRefreshedAt);
      expect(rows.length).toBeGreaterThan(0);
    }
  },
  360_000
);
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "live Shopify orders are complete",
  async () => {
    const w = completeWeek(new Date("2026-10-15"));
    const sales = await fetchShopifyWeek(isoDay(w.start), isoDay(w.end));
    expect(sales.units).toBeGreaterThan(0);
  },
  180_000
);

it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "all wall analytics survive uncached production-sized histories",
  async () => {
    const originalFetch = globalThis.fetch;
    const statuses: number[] = [];
    if (process.env.OMI_TV_LIVE_UNCACHED === "1") {
      vi.stubGlobal(
        "fetch",
        async (input: Parameters<typeof fetch>[0], init?: RequestInit) => {
          const body = JSON.parse(String(init?.body));
          const res = await originalFetch(input, {
            ...init,
            body: JSON.stringify({ ...body, refresh: "force_blocking" }),
          });
          statuses.push(res.status);
          return res;
        }
      );
    }
    try {
      const end = new Date("2026-10-15");
      for (const maturity of [0, 2, 7, 37] as const) {
        const rows = await periodQueries(
          queryPosthog,
          (stop, n) => cohortQuery(stop, maturity, n),
          end,
          7
        );
        expect(new Set(rows.map((r) => r[0])).size).toBe(6);
        process.stdout.write(
          JSON.stringify({ maturity, rows: rows.length, buckets: 6 }) + "\n"
        );
      }
      const rows = await periodQueries(
        queryPosthog,
        establishedQuery,
        completeWeek(end).end,
        7
      );
      expect(new Set(rows.map((r) => r[0])).size).toBe(6);
      process.stdout.write(
        JSON.stringify({ established: rows.length, statuses }) + "\n"
      );
    } finally {
      vi.unstubAllGlobals();
    }
  },
  600_000
);
