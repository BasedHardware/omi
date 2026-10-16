/** One closed UTC arrival day only. No customer properties leave PostHog. */
import { createHmac } from "crypto";
import { captureEvidenceCtes } from "./wall-capture-sql";
import {
  mcpActivityCtes,
  mcpMarkerCte,
  MCP_ACTIVITY_VERSION,
} from "./wall-mcp";
import {
  CAPTURE_TIME_SQL,
  DEFINITION_VERSION,
  EXCLUSIONS_SQL,
  FOREGROUND_SQL,
  SAVED_CAPTURE_SQL,
  PLATFORM_SQL,
  isoDay,
  shiftDay,
  sqlTime,
  utcDay,
} from "./qualified-activity";

export const ROLLUP_VERSION = `${DEFINITION_VERSION}:${MCP_ACTIVITY_VERSION}:daily-1`;
export const PAGE_SIZE = 5000;
export const MAX_PAGES = 100;
export const MAX_EXTRACT_BYTES = 64 * 1024 * 1024;
export const DATASET = "based-hardware.omi_tv";
const epoch = "toDateTime('1970-01-01 00:00:00','UTC')";
const escape = (s: string) => s.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
export function hashId(key: string, value: string, domain = "person"): string {
  if (key.length < 32) throw new Error("Rollup HMAC key missing or too short");
  return createHmac("sha256", key)
    .update(`omi-tv:${domain}:v1\0${value}`)
    .digest("hex");
}
export const keyId = (key: string) => hashId(key, "epoch", "key-id");
export function closedDay(value: string, now = new Date()): Date {
  const d = new Date(`${value}T00:00:00Z`);
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    !Number.isFinite(+d) ||
    isoDay(d) !== value ||
    +d >= +utcDay(now)
  )
    throw new Error("Rollup date must be a closed UTC day");
  return d;
}

/** Stable keyset pagination; OFFSET is unsupported by the queries API. All
 * branches scan [D,D+1), including MCP's marker probe (one day, not 30).
 * Identity rows include non-qualified people for cohort denominators. Feature
 * rows retain capture-day and signup-relative day, never the event payload.
 */
export const FEATURE_KINDS = [
  "identity",
  "activity",
  "capture",
  "mcp",
  "marker",
] as const;
export type FeatureKind = (typeof FEATURE_KINDS)[number];
export function dailyExtractQuery(
  day: string,
  after = "",
  kind: FeatureKind = "identity"
) {
  const start = closedDay(day),
    end = shiftDay(start, 1);
  const age = (at: string) =>
    `floor(dateDiff('microsecond',anchor,${at})/86400000000)`;
  const dayOf = (at: string) => `formatDateTime(${at},'%Y-%m-%d','UTC')`;
  const features: Record<FeatureKind, string> = {
    identity: `SELECT actor,'identity' kind,p,min(anchor) a,min(timestamp) first_at,max(timestamp) latest,
      '${day}' activity_day,0 age_day,false saved,'' family,false phone,false mac,count() n
      FROM raw GROUP BY actor,p`,
    activity: `SELECT actor,'activity' kind,p,min(anchor) a,min(qt) first_at,max(qt) latest,
      ${dayOf("qt")} activity_day,${age(
      "qt"
    )} age_day,max(cap) saved,'' family,false phone,false mac,count() n
      FROM qualified WHERE fg OR cap GROUP BY actor,p,activity_day,age_day`,
    capture: `SELECT actor,'capture' kind,p,min(anchor) a,min(et) first_at,max(et) latest,
      ${dayOf("et")} activity_day,${age(
      "et"
    )} age_day,false saved,h family,phone,mac,count() n
      FROM hw WHERE h!='' OR phone OR mac GROUP BY actor,p,activity_day,age_day,h,phone,mac`,
    mcp: `SELECT actor,'mcp' kind,'integrations' p,${epoch} a,min(mcp_days.latest) first_at,max(mcp_days.latest) latest,
      '${day}' activity_day,0 age_day,false saved,'' family,false phone,false mac,1 n FROM mcp_days GROUP BY actor`,
    marker: `SELECT '' actor,'marker' kind,'unknown' p,${epoch} a,${epoch} first_at,${epoch} latest,
      '${day}' activity_day,0 age_day,false saved,'' family,false phone,false mac,count() n FROM mcp_raw`,
  };
  // Separate feature queries keep the cadence joins out of app extraction.
  const raw = `raw AS (
    SELECT coalesce(toString(person_id),distinct_id) actor,person.created_at anchor,
      event,timestamp,properties,${PLATFORM_SQL} p FROM events
    WHERE timestamp >= ${sqlTime(start)} AND timestamp < ${sqlTime(
    end
  )} AND ${EXCLUSIONS_SQL})`;
  const app = `${raw}, flagged AS (SELECT *,${FOREGROUND_SQL} fg,${SAVED_CAPTURE_SQL} cap FROM raw),
    qualified AS (SELECT *,${CAPTURE_TIME_SQL} qt FROM flagged)`;
  const mcp = mcpActivityCtes(start, end, 1);
  const ctes =
    kind === "identity"
      ? raw
      : kind === "activity"
      ? app
      : kind === "capture"
      ? `${app},${captureEvidenceCtes()}`
      : kind === "mcp"
      ? mcp
      : mcpMarkerCte(start, end, 1);
  return `WITH ${ctes}, features AS (${features[kind]}),
  keyed AS (SELECT *,toJSONString(tuple(actor,kind,p,activity_day,age_day,family,phone,mac)) row_key FROM features)
  SELECT actor,kind,p,toString(a),toString(first_at),toString(latest),activity_day,age_day,saved,family,phone,mac,n,row_key
  FROM keyed WHERE row_key > '${escape(
    after
  )}' ORDER BY row_key LIMIT ${PAGE_SIZE}`;
}

export interface DailyRow {
  day: string;
  definition: string;
  key_id: string;
  actor: string;
  row_key: string;
  kind: string;
  p: string;
  anchor: string | null;
  first_at: string;
  latest: string;
  activity_day: string;
  age_day: number;
  saved: boolean;
  family: string;
  phone: boolean;
  mac: boolean;
  n: number;
}
function timestamp(v: unknown): string {
  const text = String(v);
  const d = new Date(
    /[zZ]|[+-]\d\d:\d\d$/.test(text) ? text : `${text.replace(" ", "T")}Z`
  );
  if (!Number.isFinite(+d)) throw new Error("Rollup timestamp unavailable");
  // Date normalizes timezone but truncates sub-millisecond precision. BigQuery
  // and PostHog both support microseconds; preserve them for recency/cohort ties.
  const fraction = text.match(/\.(\d+)(?:Z|[+-]\d\d:\d\d)?$/i)?.[1];
  const iso = d.toISOString();
  return fraction && fraction.length > 3
    ? iso.replace(/\.\d{3}Z$/, `.${fraction}Z`)
    : iso;
}
/** Personless events have no person.created_at; their identity observations
 * keep a real null anchor instead of aborting the whole day's extraction.
 * HogQL renders a null anchor as null/"null"; epoch sentinels also store null. */
function anchorOf(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const text = String(v);
  if (!/\d/.test(text) || /^null$/i.test(text)) return null;
  return Date.parse(timestamp(text)) === 0 ? null : timestamp(text);
}
export function anonymize(day: string, r: unknown[], key: string): DailyRow {
  if (
    r.length !== 14 ||
    !["identity", "activity", "capture", "mcp", "marker"].includes(String(r[1]))
  )
    throw new Error("Rollup extract shape invalid");
  return {
    day,
    definition: ROLLUP_VERSION,
    key_id: keyId(key),
    actor: hashId(key, String(r[0])),
    row_key: hashId(key, String(r[13]), "row"),
    kind: String(r[1]),
    p: String(r[2]),
    anchor: anchorOf(r[3]),
    first_at: timestamp(r[4]),
    latest: timestamp(r[5]),
    activity_day: String(r[6]),
    age_day: Number(r[7]),
    saved: Boolean(r[8]),
    family: String(r[9]),
    phone: Boolean(r[10]),
    mac: Boolean(r[11]),
    n: Number(r[12]),
  };
}
export type Page = { results: unknown[][]; sourceRefreshedAt: string };
export async function extractDay(
  day: string,
  key: string,
  query: (sql: string) => Promise<Page>
) {
  const rows: DailyRow[] = [];
  const seen = new Set<string>();
  let refreshedAt = "",
    bytes = 0,
    pages = 0;
  for (const kind of FEATURE_KINDS) {
    let after = "";
    for (;;) {
      if (pages >= MAX_PAGES)
        throw new Error("Rollup page budget exceeded; day not published");
      const out = await query(dailyExtractQuery(day, after, kind));
      pages++;
      if (
        out.results.length > PAGE_SIZE ||
        !Number.isFinite(Date.parse(out.sourceRefreshedAt))
      )
        throw new Error("Rollup page incomplete or watermark unavailable");
      refreshedAt =
        !refreshedAt || out.sourceRefreshedAt < refreshedAt
          ? out.sourceRefreshedAt
          : refreshedAt;
      for (const r of out.results) {
        const cursor = String(r[13]);
        if (cursor <= after) throw new Error("Rollup cursor did not advance");
        const row = anonymize(day, r, key);
        if (row.kind !== kind) throw new Error("Rollup feature kind mismatch");
        if (seen.has(row.row_key)) throw new Error("Rollup duplicate feature");
        bytes += Buffer.byteLength(JSON.stringify(row));
        if (bytes > MAX_EXTRACT_BYTES)
          throw new Error("Rollup byte budget exceeded; day not published");
        seen.add(row.row_key);
        rows.push(row);
        after = cursor;
      }
      if (out.results.length < PAGE_SIZE) break;
    }
  }
  if (!rows.some((r) => r.kind === "marker"))
    throw new Error("Rollup marker receipt missing");
  return { rows, refreshedAt, pages };
}
