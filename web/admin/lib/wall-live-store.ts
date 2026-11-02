/** Web read of the live metered rows the `omi-tv-live` job writes to
 * `based-hardware.omi_tv.live_day` (see `wall-live-bq.ts`). Read-only here, with
 * the admin runtime's own ADC (dataViewer on omi_tv). Any failure is "no live
 * days", never a guess: the margin then shows the settled days alone and says so. */
import { BigQuery } from "@google-cloud/bigquery";
import { LiveDoc } from "./wall-live";
import { buildLiveRead, liveDocFromRows, LiveRow } from "./wall-live-bq";

let client: BigQuery | null = null;
const LIVE_WINDOW_DAYS = 14;

export async function readLiveDoc(now = Date.now()): Promise<LiveDoc | null> {
  try {
    client ??= new BigQuery({ projectId: "based-hardware" });
    const lower = new Date(now - LIVE_WINDOW_DAYS * 86_400_000)
      .toISOString()
      .slice(0, 10);
    const { query, params } = buildLiveRead(lower);
    const [rows] = await client.query({
      query,
      params,
      maximumBytesBilled: String(10 * 1024 * 1024),
      jobTimeoutMs: 30_000,
    });
    return liveDocFromRows(rows as LiveRow[]);
  } catch {
    return null;
  }
}
