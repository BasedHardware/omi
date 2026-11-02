/** Near-real-time metered cost for the Omi TV margin (David 2026-11-02).
 *
 * Producer side (the `omi-tv-live` job) and its document shape. The settled
 * all-in stack stays billing-export truth through D-2 (`allInCost`); D-1 and
 * today are estimated from these metered quantities plus the constants in
 * `omi-tv-live-rates.json`:
 *   - Cloud Run, Firestore, GCS operations and Logging are metered
 *     (the marginmeter query set, Monitoring + managed Prometheus). Their
 *     window ends LIVE_LAG_MS before now: Cloud Run metrics arrive late and a
 *     real-time read undercounts 6-47%.
 *   - GKE pools and the other-GCP carry are calibration constants, not metered.
 *
 * This module has no runtime import of the wall code (types only), so the job
 * bundle stays small. The splice into the wall is in `wall-live-margin.ts`.
 */
import RATES from "./omi-tv-live-rates.json";

export const LIVE_LAG_MS = 5 * 60_000;
export const DAY_MS = 86_400_000;
/** A partial today is shown only from 2 UTC hours on: before that the metered
 * run rate is too thin to scale up to a full day. */
export const LIVE_MIN_FRACTION = 2 / 24;
/** Days of produced live values kept in the document (reconciliation needs 7). */
export const LIVE_KEEP_DAYS = 14;
/** Doc id in `admin_stats_payload_cache`, shared by the job and the admin read. */
export const LIVE_DOC_ID = "wall-live:v1";

export interface LiveQuantities {
  /** Service name → billable instance-seconds in the window. */
  crInstanceSeconds: Record<string, number>;
  fsReads: number;
  fsWrites: number;
  /** GCS Class A and Class B operations in the window. */
  gcsA: number;
  gcsB: number;
  /** Logging bytes ingested in the window. */
  logBytes: number;
  /** Whether Monitoring returned at least one series for each metered family.
   * An empty result is unavailable, never a zero reading (review r1). */
  seen: {
    cloudRun: boolean;
    firestore: boolean;
    gcs: boolean;
    logging: boolean;
  };
}
export interface MeteredUsd {
  cloudRun: number;
  firestore: number;
  gcs: number;
  logging: number;
}
export interface LiveDay {
  /** UTC day (YYYY-MM-DD). */
  date: string;
  /** ISO end of the metered window: now − lag, or the end of the day. */
  queryEnd: string;
  /** Share of the UTC day the window covers (1 for a closed day). */
  fraction: number;
  /** USD for the covered window, unscaled. */
  metered: MeteredUsd;
  producedAt: string;
  /** Cloud Run services priced by the default size because they have no entry
   * in `crSpecs`: an estimate, named on the status line. */
  estimated?: string[];
}
export interface LiveDoc {
  days: Record<string, LiveDay>;
  /** When the producer last wrote this document. A stale run makes every live
   * day stale, including a closed one (a dead job must not look fresh). */
  runAt?: string;
}

const hasSpec = (svc: string) =>
  Object.prototype.hasOwnProperty.call(RATES.crSpecs, svc);

/** Cloud Run services with no calibrated size, and request-billed services
 * (`crRequestBilled`, whose request metrics are not metered): priced at an
 * estimate and flagged, never silently. */
export function estimatedServices(q: LiveQuantities): string[] {
  const requestBilled = new Set<string>(RATES.crRequestBilled);
  return Object.keys(q.crInstanceSeconds)
    .filter((svc) => !hasSpec(svc) || requestBilled.has(svc))
    .sort();
}

/** Metered USD for one window from its quantities and the calibrated unit
 * rates (the marginmeter `margin.py` formulas, ported). Null when any metered
 * family returned no series: that day is unavailable, not $0. */
export function meteredUsd(q: LiveQuantities): MeteredUsd | null {
  if (!q.seen.cloudRun || !q.seen.firestore || !q.seen.gcs || !q.seen.logging)
    return null;
  const cloudRun = Object.entries(q.crInstanceSeconds).reduce(
    (sum, [svc, isec]) => {
      const spec = hasSpec(svc)
        ? (RATES.crSpecs as Record<string, { vcpu: number; gib: number }>)[svc]
        : RATES.crDefaultSpec;
      return sum + isec * (spec.vcpu * RATES.crVcpuS + spec.gib * RATES.crGibS);
    },
    0
  );
  return {
    cloudRun,
    firestore: q.fsReads * RATES.fsReadReq + q.fsWrites * RATES.fsWriteReq,
    gcs: q.gcsA * RATES.gcsA + q.gcsB * RATES.gcsB,
    logging: q.logBytes * RATES.logPerByte,
  };
}

const isoOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** The two days the producer meters on each run: yesterday and today (UTC). */
export function liveDates(now: number): string[] {
  const today = isoOf(now);
  return [isoOf(Date.parse(`${today}T00:00:00Z`) - DAY_MS), today];
}

/** Every day the producer re-meters on each run: D-2 (kept live so a midnight
 * billing lag never leaves it in neither source), yesterday and today. Each row
 * ages on its own produced-at, so a row the run skipped goes stale. */
export function producedDates(now: number): string[] {
  const [yesterday, today] = liveDates(now);
  return [
    isoOf(Date.parse(`${yesterday}T00:00:00Z`) - DAY_MS),
    yesterday,
    today,
  ];
}

/** The metered window for a UTC day at `now`, or null when it has not begun
 * (after the lag). A closed day's window is the whole day. */
export function liveWindow(
  date: string,
  now: number
): { start: number; end: number; fraction: number } | null {
  const start = Date.parse(`${date}T00:00:00Z`);
  const end = Math.min(now - LIVE_LAG_MS, start + DAY_MS);
  if (end <= start) return null;
  return { start, end, fraction: (end - start) / DAY_MS };
}

/** Merge a run's produced days into the stored document, pruning days older
 * than LIVE_KEEP_DAYS. A produced day replaces its stored value (the later
 * window is always the more complete one). */
export function mergeLiveDoc(
  stored: LiveDoc | null,
  produced: LiveDay[],
  now: number
): LiveDoc {
  const days: Record<string, LiveDay> = { ...(stored?.days ?? {}) };
  for (const d of produced) days[d.date] = d;
  const oldest = isoOf(now - LIVE_KEEP_DAYS * DAY_MS);
  for (const key of Object.keys(days)) if (key < oldest) delete days[key];
  return { days, runAt: new Date(now).toISOString() };
}

/** Parse a stored document defensively: anything malformed is no document. */
export function parseLiveDoc(raw: unknown): LiveDoc | null {
  if (!raw || typeof raw !== "object") return null;
  const days = (raw as { days?: unknown }).days;
  if (!days || typeof days !== "object") return null;
  const out: Record<string, LiveDay> = {};
  for (const [date, value] of Object.entries(days as Record<string, unknown>)) {
    const v = value as Partial<LiveDay> | null;
    if (
      v &&
      v.date === date &&
      typeof v.fraction === "number" &&
      v.fraction > 0 &&
      v.fraction <= 1 &&
      v.metered &&
      typeof v.metered.cloudRun === "number" &&
      typeof v.metered.firestore === "number" &&
      typeof v.metered.gcs === "number" &&
      typeof v.metered.logging === "number"
    )
      out[date] = v as LiveDay;
  }
  const runAt = (raw as { runAt?: unknown }).runAt;
  return {
    days: out,
    runAt:
      typeof runAt === "string" && !Number.isNaN(Date.parse(runAt))
        ? runAt
        : undefined,
  };
}

export const isWeekendDay = (date: string) => {
  const dow = new Date(`${date}T00:00:00Z`).getUTCDay();
  return dow === 0 || dow === 6;
};
