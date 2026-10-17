// Opt-in read-only acceptance, counts/timings only. Requires completed rollup
// coverage, ADC + configured PostHog credentials. Never writes/backfills.
import { expect, it } from "vitest";
import { readRollup } from "../wall-rollup";
import { activityQuery, queryPosthog } from "../wall-posthog";
import { completeWeek, isoDay } from "../qualified-activity";

it.skipIf(process.env.OMI_TV_ROLLUP_LIVE_CHECK !== "1")(
  "rollup WAU/MAU match HogQL at the last complete UTC week cutoff",
  async () => {
    const week = completeWeek();
    const total = (rows: unknown[][]) =>
      rows
        .filter((r) => Number(r[0]) === 0 && !String(r[1]).startsWith("__"))
        .reduce((n, r) => n + Number(r[2]), 0);
    // Serial source reads; this check intentionally bounds production query work.
    {
      const end = week.end;
      for (const days of [7, 30]) {
        const started = Date.now();
        const rolled = await readRollup({
          kind: "activity",
          end,
          days,
          periods: 1,
        });
        expect(rolled, "rollup must cover the entire window").not.toBeNull();
        const hog = await queryPosthog(activityQuery(end, days, "active", 1));
        console.info(
          JSON.stringify({
            through: isoDay(new Date(+end - 86400000)),
            days,
            rollup: total(rolled!),
            hogql: total(hog),
            durationMs: Date.now() - started,
          })
        );
        expect(total(rolled!)).toBe(total(hog));
        for (const p of [
          "macos",
          "ios",
          "android",
          "windows",
          "web",
          "integrations",
          "unknown",
        ]) {
          const count = (rows: unknown[][]) =>
            rows
              .filter((r) => Number(r[0]) === 0 && r[1] === p)
              .reduce((n, r) => n + Number(r[2]), 0);
          expect(count(rolled!)).toBe(count(hog));
        }
      }
    }
  },
  900_000
);
