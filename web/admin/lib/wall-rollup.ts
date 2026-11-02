/** Read-only ADC client. Responses contain aggregate counts only. */
import {
  BigQuery,
  BigQueryDate,
  BigQueryTimestamp,
  Query as BigQueryQuery,
} from "@google-cloud/bigquery";
import { AggregateRows } from "./wall-posthog";
import { DAY_MS, isoDay } from "./qualified-activity";
import { DATASET, keyId, ROLLUP_VERSION } from "./wall-rollup-extract";
import { RollupRequest, rollupSql } from "./wall-rollup-sql";

export interface RollupStatus {
  through: string | null;
  reason: string | null;
}
export type RollupRead = (
  request: RollupRequest
) => Promise<AggregateRows | null>;
export interface RollupDb {
  query(
    options: BigQueryQuery
  ): Promise<[Record<string, unknown>[], ...unknown[]]>;
}
// Do not use the billing client's optional JSON key override.
let adc: BigQuery | undefined;
const client = () => (adc ||= new BigQuery({ projectId: "based-hardware" }));
const opts = {
  maximumBytesBilled: String(10 * 1024 * 1024 * 1024),
  jobTimeoutMs: 30_000,
  location: "US",
};

export async function readRollup(
  request: RollupRequest,
  db: RollupDb = client()
): Promise<AggregateRows | null> {
  if (process.env.OMI_TV_ROLLUP_ENABLED !== "1") return null;
  try {
    const spec = rollupSql(request);
    const [result] = await db.query({
      ...opts,
      query: spec.query,
      params: {
        start: new BigQueryDate(isoDay(spec.start)),
        stop: new BigQueryDate(isoDay(spec.stop)),
        activityStart: new BigQueryTimestamp(spec.activityStart),
        definition: ROLLUP_VERSION,
        keyId: keyId(process.env.CRON_SECRET || ""),
      },
    });
    const r = result[0];
    if (
      Number(r?.covered) !== Math.round((+spec.stop - +spec.start) / DAY_MS) ||
      !Array.isArray(r?.rows)
    )
      return null;
    const rows = (r.rows as string[]).map((row) => JSON.parse(row));
    return Object.assign(rows, {
      sourceRefreshedAt:
        typeof r.refreshed === "string"
          ? new Date(r.refreshed).toISOString()
          : null,
    });
  } catch {
    // IAM/schema/query errors never expose SQL, response bodies or identities.
    console.warn(
      JSON.stringify({
        event: "wall_rollup_read",
        outcome: "fallback",
        kind: request.kind,
      })
    );
    return null;
  }
}

let statusCache: { at: number; value: RollupStatus } | undefined;
// One shared in-flight lookup: concurrent cache misses coalesce here instead of
// each starting a BigQuery query that may run under its 30s job timeout.
let statusFlight: Promise<RollupStatus> | undefined;
export async function rollupStatus(
  db: RollupDb = client()
): Promise<RollupStatus> {
  if (process.env.OMI_TV_ROLLUP_ENABLED !== "1")
    return { through: null, reason: "disabled" };
  if (statusCache && Date.now() - statusCache.at < 60_000)
    return statusCache.value;
  // Supplemental display text only: never hold a headline response on a slow or
  // degraded BigQuery. The lookup is capped at one second and keeps filling the
  // cache in the background, so a timed-out read retries on a later request and
  // serves the stale cached value in the meantime. Concurrent misses share the
  // in-flight lookup; it clears once the repopulated cache takes over again.
  const lookup = (statusFlight ||= (async (): Promise<RollupStatus> => {
    let value: RollupStatus;
    try {
      const [rows] = await db.query({
        ...opts,
        query: `SELECT FORMAT_DATE('%F',MAX(day)) through FROM \`${DATASET}.coverage\`
      WHERE day >= DATE_SUB(CURRENT_DATE('UTC'),INTERVAL 400 DAY) AND day<CURRENT_DATE('UTC') AND definition=@definition AND key_id=@keyId`,
        params: {
          definition: ROLLUP_VERSION,
          keyId: keyId(process.env.CRON_SECRET || ""),
        },
      });
      value = {
        through: rows[0]?.through ? String(rows[0].through) : null,
        reason: rows[0]?.through ? null : "no completed days",
      };
    } catch {
      value = { through: null, reason: "unavailable" };
    }
    statusCache = { at: Date.now(), value };
    statusFlight = undefined;
    return value;
  })());
  let timer: ReturnType<typeof setTimeout>;
  const capped = new Promise<RollupStatus>((resolve) => {
    timer = setTimeout(
      () => resolve(statusCache?.value ?? { through: null, reason: "slow" }),
      1_000
    );
  });
  return Promise.race([lookup, capped]).finally(() => clearTimeout(timer));
}
export async function preferRollup(
  read: RollupRead | undefined,
  request: RollupRequest,
  fallback: () => Promise<AggregateRows>
) {
  if (!read) return fallback();
  let result: AggregateRows | null = null;
  try {
    result = await read(request);
  } catch {
    /* injected readers fail the same way */
  }
  console.info(
    JSON.stringify({
      event: "wall_rollup_source",
      kind: request.kind,
      source: result ? "rollup" : "posthog",
      outcome: result ? "covered" : "fallback",
    })
  );
  return result ?? fallback();
}
