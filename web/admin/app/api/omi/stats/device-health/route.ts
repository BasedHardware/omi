import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";

export const dynamic = "force-dynamic";

export const DEVICE_HEALTH_DEFAULT_DAYS = 14;
export const DEVICE_HEALTH_MAX_DAYS = 30;

const POSTHOG_MAX_ATTEMPTS = 3;

// 429 stays inside posthogFetch (called by posthogResults). Retrying it here
// would stack on that inner backoff and reach nine requests per query. The
// outer loop is only for gateway and timeout failures, with escalating backoff.
function isOuterRetryablePostHogStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 504;
}

// attempt is 1-based (the attempt that just failed).
function retryDelayMs(attempt: number): number {
  const jitter = Math.floor(Math.random() * 250);
  return 1000 * attempt + jitter;
}

function posthogStatus(error: unknown): number | null {
  if (!(error instanceof Error)) return null;
  const match = /PostHog API error: (\d+)/.exec(error.message);
  if (!match) return null;
  const status = Number(match[1]);
  return Number.isFinite(status) ? status : null;
}

export function parseDeviceHealthDays(raw: string | null): number {
  if (raw == null || raw.trim() === "") return DEVICE_HEALTH_DEFAULT_DAYS;
  // Digits only: the value is interpolated into HogQL.
  if (!/^\d+$/.test(raw.trim())) return DEVICE_HEALTH_DEFAULT_DAYS;
  const parsed = Number(raw);
  if (parsed < 1) return DEVICE_HEALTH_DEFAULT_DAYS;
  return Math.min(parsed, DEVICE_HEALTH_MAX_DAYS);
}

export function pendantHealthQuery(days: number): string {
  return `
    SELECT properties.firmware AS firmware,
           count() AS events,
           uniqExact(person_id) AS users,
           countIf(toFloat(properties.drain_percent_per_hour) BETWEEN 0.1 AND 100) AS n_valid_drain,
           round(quantileIf(0.5)(toFloat(properties.drain_percent_per_hour), toFloat(properties.drain_percent_per_hour) BETWEEN 0.1 AND 100),2) AS p50_drain_valid,
           round(quantileIf(0.9)(toFloat(properties.drain_percent_per_hour), toFloat(properties.drain_percent_per_hour) BETWEEN 0.1 AND 100),2) AS p90_drain_valid,
           round(avg(toFloat(properties.connected_time_fraction)),2) AS avg_connected_frac,
           countIf(toFloat(properties.cliff_count) > 0) AS n_with_cliffs
    FROM events
    WHERE event = 'Mobile Device Health Daily' AND timestamp >= now() - INTERVAL ${days} DAY
    GROUP BY firmware ORDER BY events DESC LIMIT 15
  `;
}

// PostHog rejects a window function in WHERE (the drain CTE's second
// lagInFrame over pairs) and cannot see person_id unless that CTE projects
// it. Both lags are computed once in `pairs`; the aggregate stays outside.
// The timestamp predicate is repeated on the outer query so the scan stays
// bounded — a filter that exists only inside the CTE 504s.
// Unknown charging counts as drain on either endpoint; only an explicit
// true excludes the interval. `!= true` drops NULL and would hide those pairs.
export function phoneHealthQuery(days: number): string {
  return `
    WITH samples AS (
      SELECT person_id,
             coalesce(nullIf(properties.$os_name,''), properties.platform) AS os,
             coalesce(properties.$app_build, properties.app_build) AS build,
             timestamp,
             toFloat(properties.battery_level) AS level,
             properties.battery_charging AS charging
      FROM events
      WHERE event = 'Phone Battery Sample'
        AND timestamp >= now() - INTERVAL ${days} DAY
        AND coalesce(nullIf(properties.$os_name,''), properties.platform) IN ('Android','iOS')
    ),
    pairs AS (
      SELECT os, build, person_id, timestamp, level, charging,
             dateDiff('second', lagInFrame(timestamp, 1, timestamp) OVER (PARTITION BY person_id ORDER BY timestamp), timestamp) AS elapsed_s,
             lagInFrame(level, 1, level) OVER (PARTITION BY person_id ORDER BY timestamp) - level AS level_drop,
             lagInFrame(charging, 1, charging) OVER (PARTITION BY person_id ORDER BY timestamp) AS prev_charging
      FROM samples
    )
    SELECT os, build,
           count() AS n_pairs,
           uniqExact(person_id) AS users,
           round(quantile(0.5)(toFloat(level_drop) / greatest(elapsed_s/3600.0, 0.01)),2) AS p50_drain_per_hour,
           round(quantile(0.9)(toFloat(level_drop) / greatest(elapsed_s/3600.0, 0.01)),2) AS p90_drain_per_hour
    FROM pairs
    WHERE timestamp >= now() - INTERVAL ${days} DAY
      AND elapsed_s BETWEEN 900 AND 7200
      AND level_drop > 0
      AND (charging = false OR isNull(charging))
      AND (prev_charging = false OR isNull(prev_charging))
    GROUP BY os, build
    ORDER BY os, build
  `;
}

// Cheap existence check, run only when the pair query returns no rows.
// Zero events means the sampler has not shipped; events with no surviving
// pair are a real measurement.
export function phoneEventCountQuery(days: number): string {
  return `
    SELECT count() AS n
    FROM events
    WHERE event = 'Phone Battery Sample'
      AND timestamp >= now() - INTERVAL ${days} DAY
  `;
}

export interface PendantHealthRow {
  firmware: string;
  events: number;
  users: number;
  n_valid_drain: number;
  p50_drain_valid: number | null;
  p90_drain_valid: number | null;
  avg_connected_frac: number | null;
  n_with_cliffs: number;
}

export interface PhoneHealthRow {
  os: string;
  build: string;
  label: string;
  n_pairs: number;
  users: number;
  p50_drain_per_hour: number | null;
  p90_drain_per_hour: number | null;
}

export type PhoneHealthPayload =
  | { status: "awaiting_instrumentation"; series: [] }
  | { status: "measured_no_valid_pairs"; series: []; n_events: number }
  | { status: "ok"; series: PhoneHealthRow[] };

export interface DeviceHealthResponse {
  days: number;
  pendant_health: PendantHealthRow[];
  phone_health: PhoneHealthPayload;
}

async function queryPostHog(
  host: string,
  projectId: string,
  apiKey: string,
  query: string
): Promise<unknown[]> {
  for (let attempt = 1; attempt <= POSTHOG_MAX_ATTEMPTS; attempt++) {
    try {
      return await posthogResults(host, projectId, apiKey, query);
    } catch (error) {
      const status = posthogStatus(error);
      const retry =
        status != null &&
        isOuterRetryablePostHogStatus(status) &&
        attempt < POSTHOG_MAX_ATTEMPTS;
      if (!retry) throw error;
      await new Promise((resolve) =>
        setTimeout(resolve, retryDelayMs(attempt))
      );
    }
  }
  throw new Error("PostHog retries exhausted");
}

function finiteNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function count(value: unknown): number {
  return finiteNumber(value) ?? 0;
}

function text(value: unknown): string {
  if (value == null) return "";
  return String(value);
}

function asRows(results: unknown[]): unknown[][] {
  return results.filter((row): row is unknown[] => Array.isArray(row));
}

function mapPendant(rows: unknown[][]): PendantHealthRow[] {
  return rows.map((row) => ({
    firmware: text(row[0]) || "unknown",
    events: count(row[1]),
    users: count(row[2]),
    n_valid_drain: count(row[3]),
    p50_drain_valid: finiteNumber(row[4]),
    p90_drain_valid: finiteNumber(row[5]),
    avg_connected_frac: finiteNumber(row[6]),
    n_with_cliffs: count(row[7]),
  }));
}

function mapPhone(rows: unknown[][]): PhoneHealthRow[] {
  return rows.map((row) => {
    const os = text(row[0]);
    const build = text(row[1]);
    const label =
      [os, build].filter((part) => part.length > 0).join(" ") || "unknown";
    return {
      os,
      build,
      label,
      n_pairs: count(row[2]),
      users: count(row[3]),
      p50_drain_per_hour: finiteNumber(row[4]),
      p90_drain_per_hour: finiteNumber(row[5]),
    };
  });
}

export async function computeDeviceHealth(
  days: number
): Promise<DeviceHealthResponse> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    ""
  );

  if (!apiKey || !projectId) {
    throw new Error("PostHog credentials not configured");
  }

  const [pendantRows, phoneRows] = await Promise.all([
    queryPostHog(host, projectId, apiKey, pendantHealthQuery(days)),
    queryPostHog(host, projectId, apiKey, phoneHealthQuery(days)),
  ]);

  const series = mapPhone(asRows(phoneRows));
  let phone_health: PhoneHealthPayload;
  if (series.length > 0) {
    phone_health = { status: "ok", series };
  } else {
    const countRows = await queryPostHog(
      host,
      projectId,
      apiKey,
      phoneEventCountQuery(days)
    );
    const nEvents = count(asRows(countRows)[0]?.[0]);
    phone_health =
      nEvents === 0
        ? { status: "awaiting_instrumentation", series: [] }
        : { status: "measured_no_valid_pairs", series: [], n_events: nEvents };
  }

  return {
    days,
    pendant_health: mapPendant(asRows(pendantRows)),
    phone_health,
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const days = parseDeviceHealthDays(request.nextUrl.searchParams.get("days"));
  try {
    return NextResponse.json(await computeDeviceHealth(days));
  } catch (error) {
    console.error("Device health error:", error);
    const message =
      error instanceof Error ? error.message : "Failed to fetch device health";
    return NextResponse.json(
      { error: message || "Failed to fetch device health" },
      { status: 500 }
    );
  }
}
