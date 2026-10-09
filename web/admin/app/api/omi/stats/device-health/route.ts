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

// Watch firmware leaks in from connected non-pendant devices: the stored
// label is a watchOS version (26.6, 27.0, 27.0.1). Pendant majors are a
// single digit (1, 2, 3), so a two-digit major is not a pendant. 1.0.4
// stays — it is the original Friend pendant, and the label names it.
export function pendantHealthQuery(days: number): string {
  return `
    SELECT trim(properties.firmware) AS firmware,
           coalesce(nullIf(properties.$os_name,''), properties.platform) AS os,
           any(properties.device_model) AS device_model,
           count() AS events,
           uniqExact(person_id) AS users,
           countIf(toFloat(properties.drain_percent_per_hour) BETWEEN 0.1 AND 100) AS n_valid_drain,
           round(quantileIf(0.5)(toFloat(properties.drain_percent_per_hour), toFloat(properties.drain_percent_per_hour) BETWEEN 0.1 AND 100),2) AS p50_drain_valid,
           round(quantileIf(0.9)(toFloat(properties.drain_percent_per_hour), toFloat(properties.drain_percent_per_hour) BETWEEN 0.1 AND 100),2) AS p90_drain_valid,
           round(avg(toFloat(properties.connected_time_fraction)),2) AS avg_connected_frac,
           countIf(toFloat(properties.cliff_count) > 0) AS n_with_cliffs
    FROM events
    WHERE event = 'Mobile Device Health Daily' AND timestamp >= now() - INTERVAL ${days} DAY
      AND nullIf(trim(properties.firmware),'') IS NOT NULL
      AND trim(properties.firmware) NOT IN ('','Unknown','unknown','26.6','27.0')
      AND NOT match(trim(properties.firmware), '^[0-9]{2}[.]')
    GROUP BY firmware, os
    HAVING uniqExact(person_id) >= 20
    ORDER BY users DESC
  `;
}

// PostHog rejects a window function in WHERE (the drain CTE's second
// lagInFrame over pairs) and cannot see person_id unless that CTE projects
// it. Both lags are computed once in `pairs`; the aggregate stays outside.
// The timestamp predicate is repeated on the outer query so the scan stays
// bounded — a filter that exists only inside the CTE 504s.
// Unknown charging counts as drain on either endpoint; only an explicit
// true excludes the interval. `!= true` drops NULL and would hide those pairs.
// app_version is aggregated with max() so the bar label can show it without
// adding a GROUP BY key — one OS + build stays one row. String max is
// deterministic; these versions are 1.0.558-style, not zero-padded.
export function phoneHealthQuery(days: number): string {
  return `
    WITH samples AS (
      SELECT person_id,
             coalesce(nullIf(properties.$os_name,''), properties.platform) AS os,
             coalesce(properties.$app_build, properties.app_build) AS build,
             coalesce(nullIf(properties.$app_version,''), nullIf(properties.app_version,''), '') AS app_version,
             timestamp,
             toFloat(properties.battery_level) AS level,
             properties.battery_charging AS charging
      FROM events
      WHERE event = 'Phone Battery Sample'
        AND timestamp >= now() - INTERVAL ${days} DAY
        AND coalesce(nullIf(properties.$os_name,''), properties.platform) IN ('Android','iOS')
    ),
    pairs AS (
      SELECT os, build, app_version, person_id, timestamp, level, charging,
             dateDiff('second', lagInFrame(timestamp, 1, timestamp) OVER (PARTITION BY person_id ORDER BY timestamp), timestamp) AS elapsed_s,
             lagInFrame(level, 1, level) OVER (PARTITION BY person_id ORDER BY timestamp) - level AS level_drop,
             lagInFrame(charging, 1, charging) OVER (PARTITION BY person_id ORDER BY timestamp) AS prev_charging
      FROM samples
    )
    SELECT os, build,
           max(app_version) AS app_version,
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
  os: string;
  device_model: string;
  firmware_label: string;
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
  app_version: string;
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

function firmwareLabel(
  firmware: string,
  os: string,
  deviceModel: string
): string {
  // 1.0.4 is the original Friend pendant. Name it so the bar is not read as
  // a current Omi build. device_model is on the row; a blank any() still
  // means Friend v1 because that firmware is the hardware.
  const model = deviceModel.trim();
  const friendV1 =
    firmware === "1.0.4" && (model.length === 0 || /^friend\b/i.test(model));
  const version = friendV1 ? `${firmware} (Friend v1)` : firmware;
  const platform = os.trim();
  return platform.length > 0 ? `${version} · ${platform}` : version;
}

function phoneLabel(os: string, build: string, appVersion: string): string {
  const version = appVersion.trim();
  const buildPart = build.length > 0 ? `(${build})` : "";
  const parts = [os, version, buildPart].filter((part) => part.length > 0);
  return parts.join(" ") || "unknown";
}

function mapPendant(rows: unknown[][]): PendantHealthRow[] {
  return rows.map((row) => {
    const firmware = text(row[0]) || "unknown";
    const os = text(row[1]);
    const deviceModel = text(row[2]);
    return {
      firmware,
      os,
      device_model: deviceModel,
      firmware_label: firmwareLabel(firmware, os, deviceModel),
      events: count(row[3]),
      users: count(row[4]),
      n_valid_drain: count(row[5]),
      p50_drain_valid: finiteNumber(row[6]),
      p90_drain_valid: finiteNumber(row[7]),
      avg_connected_frac: finiteNumber(row[8]),
      n_with_cliffs: count(row[9]),
    };
  });
}

function mapPhone(rows: unknown[][]): PhoneHealthRow[] {
  return rows.map((row) => {
    const os = text(row[0]);
    const build = text(row[1]);
    const appVersion = text(row[2]);
    return {
      os,
      build,
      app_version: appVersion,
      label: phoneLabel(os, build, appVersion),
      n_pairs: count(row[3]),
      users: count(row[4]),
      p50_drain_per_hour: finiteNumber(row[5]),
      p90_drain_per_hour: finiteNumber(row[6]),
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
