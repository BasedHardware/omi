/** The live metered document in BigQuery (`based-hardware.omi_tv.live_day`).
 *
 * Replaces the Firestore document (review r1 item 9): the `finops-writer`
 * identity already holds dataEditor on `omi_tv` (the rollup writes there), and
 * the admin runtime already holds dataViewer on it. One row per UTC day. The
 * job writes the rows of a run in one transaction; the admin reads the window
 * back and rebuilds the `LiveDoc` the margin splice consumes.
 *
 * Pure statement builders and row mapping only: no client is created here, so
 * the job and the admin read share one tested mapping.
 */
import { BigQueryDate, BigQueryTimestamp } from "@google-cloud/bigquery";
import type { LiveDay, LiveDoc } from "./wall-live";

export const LIVE_TABLE = "based-hardware.omi_tv.live_day";

export interface LiveRow {
  day: string;
  produced_at: unknown;
  run_at: unknown;
  query_end: unknown;
  fraction: number;
  cloud_run_usd: number;
  firestore_usd: number;
  gcs_usd: number;
  logging_usd: number;
  estimated_services: string;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const ts = (v: unknown): string => {
  const raw =
    typeof v === "string" ? v : String((v as { value?: unknown })?.value ?? "");
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? "" : new Date(ms).toISOString();
};

/** One transaction: replace each produced day's row, prune rows before
 * `pruneBefore`. Every value is a bound parameter; no SQL is interpolated. */
export function buildLiveWrite(
  produced: LiveDay[],
  runAt: Date,
  pruneBefore: string
): { query: string; params: Record<string, unknown> } {
  if (!DAY.test(pruneBefore)) throw new Error("bad prune day");
  const statements = ["BEGIN TRANSACTION;"];
  const params: Record<string, unknown> = {
    prune: new BigQueryDate(pruneBefore),
    runAt: new BigQueryTimestamp(runAt.toISOString()),
  };
  produced.forEach((d, i) => {
    if (!DAY.test(d.date)) throw new Error("bad live day");
    params[`d${i}`] = new BigQueryDate(d.date);
    params[`p${i}`] = new BigQueryTimestamp(d.producedAt);
    params[`q${i}`] = new BigQueryTimestamp(d.queryEnd);
    params[`f${i}`] = d.fraction;
    params[`c${i}`] = d.metered.cloudRun;
    params[`fs${i}`] = d.metered.firestore;
    params[`g${i}`] = d.metered.gcs;
    params[`l${i}`] = d.metered.logging;
    params[`e${i}`] = (d.estimated ?? []).join(",");
    statements.push(
      `DELETE FROM \`${LIVE_TABLE}\` WHERE day = @d${i};`,
      `INSERT INTO \`${LIVE_TABLE}\` (day, produced_at, run_at, query_end, fraction, cloud_run_usd, firestore_usd, gcs_usd, logging_usd, estimated_services) VALUES (@d${i}, @p${i}, @runAt, @q${i}, @f${i}, @c${i}, @fs${i}, @g${i}, @l${i}, @e${i});`
    );
  });
  statements.push(
    `DELETE FROM \`${LIVE_TABLE}\` WHERE day < @prune;`,
    "COMMIT TRANSACTION;"
  );
  return { query: statements.join("\n"), params };
}

/** The window read: rows on or after `lower` (a UTC day). */
export function buildLiveRead(lower: string): {
  query: string;
  params: Record<string, unknown>;
} {
  if (!DAY.test(lower)) throw new Error("bad lower day");
  return {
    query: `SELECT CAST(day AS STRING) AS day, produced_at, run_at, query_end, fraction, cloud_run_usd, firestore_usd, gcs_usd, logging_usd, estimated_services FROM \`${LIVE_TABLE}\` WHERE day >= @lower`,
    params: { lower: new BigQueryDate(lower) },
  };
}

/** Rebuild the document from rows. `runAt` is the latest run time on any row:
 * a run that wrote nothing leaves it old, so every live day reads stale. A row
 * with a malformed value is dropped, never guessed. */
export function liveDocFromRows(rows: LiveRow[]): LiveDoc {
  const days: Record<string, LiveDay> = {};
  let runAt: string | undefined;
  for (const r of rows) {
    const producedAt = ts(r.produced_at);
    const run = ts(r.run_at);
    const queryEnd = ts(r.query_end);
    const values = [
      r.fraction,
      r.cloud_run_usd,
      r.firestore_usd,
      r.gcs_usd,
      r.logging_usd,
    ];
    if (!DAY.test(r.day) || !producedAt || !queryEnd || !run) continue;
    if (!values.every((v) => typeof v === "number" && Number.isFinite(v)))
      continue;
    if (r.fraction <= 0 || r.fraction > 1) continue;
    if (!runAt || run > runAt) runAt = run;
    days[r.day] = {
      date: r.day,
      queryEnd,
      fraction: r.fraction,
      metered: {
        cloudRun: r.cloud_run_usd,
        firestore: r.firestore_usd,
        gcs: r.gcs_usd,
        logging: r.logging_usd,
      },
      producedAt,
      estimated: r.estimated_services ? r.estimated_services.split(",") : [],
    };
  }
  return { days, runAt };
}
