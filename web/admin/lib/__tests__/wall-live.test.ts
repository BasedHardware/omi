// Opt-in, read-only aggregate smoke check. No credentials or customer rows logged.
import { it, expect } from "vitest";
import {
  activityQuery,
  cohortQuery,
  establishedQuery,
  queryPosthog,
} from "../wall-posthog";
import { fetchShopifyWeek } from "../wall-shopify";
import { completeWeek, isoDay } from "../qualified-activity";
it.skipIf(process.env.OMI_TV_LIVE_CHECK !== "1")(
  "live sources compile qualified aggregate queries",
  async () => {
    const end = new Date("2026-10-15");
    for (const query of [
      activityQuery(end, 1, "active", 2),
      activityQuery(end, 30, "active", 2),
      cohortQuery(end, 7, 2),
      establishedQuery(completeWeek(end).end, 2),
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
