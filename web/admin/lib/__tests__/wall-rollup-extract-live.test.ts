// Opt-in read-only one-day writer smoke. Raw IDs stay transient in this process;
// only row/page counts are printed. No BigQuery writes or secret reads.
import { expect, it } from "vitest";
import { extractDay } from "../wall-rollup-extract";
import { queryPage } from "../../jobs/omi-tv-rollup/writer";
import { isoDay, shiftDay, utcDay } from "../qualified-activity";
it.skipIf(process.env.OMI_TV_ROLLUP_EXTRACT_CHECK !== "1")(
  "extracts and hashes one closed day through the real bounded HogQL",
  async () => {
    const started = Date.now();
    const day =
      process.env.OMI_TV_ROLLUP_CHECK_DATE || isoDay(shiftDay(utcDay(), -2));
    const data = await extractDay(
      day,
      "ephemeral-test-only-hmac-key-not-stored",
      async (sql) => {
        const started = Date.now();
        const kind = ["identity", "activity", "capture", "mcp", "marker"].find(
          (k) => sql.includes(`'${k}' kind`)
        );
        const page = await queryPage(sql);
        console.info(
          JSON.stringify({
            kind,
            rows: page.results.length,
            durationMs: Date.now() - started,
          })
        );
        return page;
      }
    );
    expect(data.rows.some((r) => r.kind === "marker")).toBe(true);
    expect(data.rows.every((r) => /^[a-f0-9]{64}$/.test(r.actor))).toBe(true);
    console.info(
      JSON.stringify({
        day,
        pages: data.pages,
        features: data.rows.length,
        durationMs: Date.now() - started,
      })
    );
  },
  900_000
);
