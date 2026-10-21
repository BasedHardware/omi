import { DESKTOP_HEALTH_EVENT_WEIGHT_SQL } from "./desktop-health-sampling";
import type { TelemetryAggregateRow } from "@/lib/telemetry/aggregates";

/**
 * Desktop fallback triage. Legacy PostHog remains authoritative until the
 * parent records real parity acceptance. This comparison does not switch the
 * consumer.
 *
 * Runbook: backend/docs/runbooks/resilience-dashboards.md (PostHog desktop
 * fallback insight). Outcomes stay recovered | degraded | exhausted. Areas
 * stay the frozen allowlist; anything else buckets to other. Reasons stay
 * the registered literals, with unknown for an unregistered reason.
 */

export const FALLBACK_OUTCOMES = [
  "recovered",
  "degraded",
  "exhausted",
] as const;
export type FallbackOutcome = (typeof FALLBACK_OUTCOMES)[number];

export const FALLBACK_AREAS = [
  "realtime_hub",
  "ptt_cascade",
  "screen_task_gate",
  "screen_task_extraction",
  "other",
] as const;

export const LEGACY_FALLBACK_CONSUMER_AUTHORITATIVE = true;

/** Primary PostHog triage view. Kept until parent acceptance. */
export const LEGACY_FALLBACK_EXHAUSTED_QUERY = `
SELECT
  toString(toDate(timestamp)) AS day,
  coalesce(nullIf(toString(properties.area), ''), 'other') AS area,
  coalesce(nullIf(toString(properties.reason), ''), 'unknown') AS reason,
  sum(${DESKTOP_HEALTH_EVENT_WEIGHT_SQL}) AS event_count
FROM events
WHERE event = 'desktop_health_event'
  AND toString(properties.health_event) = 'fallback_triggered'
  AND toString(properties.outcome) = 'exhausted'
  AND timestamp >= toStartOfDay(now()) - INTERVAL 29 DAY
GROUP BY day, area, reason
ORDER BY day ASC
LIMIT 50000
`;

/** All outcomes, for fixture parity against the replacement aggregate. */
export const LEGACY_FALLBACK_TRIAGE_QUERY = `
SELECT
  toString(toDate(timestamp)) AS day,
  coalesce(nullIf(toString(properties.area), ''), 'other') AS area,
  coalesce(nullIf(toString(properties.reason), ''), 'unknown') AS reason,
  coalesce(nullIf(toString(properties.outcome), ''), 'unknown') AS outcome,
  sum(${DESKTOP_HEALTH_EVENT_WEIGHT_SQL}) AS event_count
FROM events
WHERE event = 'desktop_health_event'
  AND toString(properties.health_event) = 'fallback_triggered'
  AND timestamp >= toStartOfDay(now()) - INTERVAL 29 DAY
GROUP BY day, area, reason, outcome
ORDER BY day ASC
LIMIT 50000
`;

export interface FallbackObservation {
  day: string;
  area: string;
  reason: string;
  outcome: string;
  count: number;
}

export interface FallbackTriageCounts {
  byOutcome: Record<FallbackOutcome, number>;
  byArea: Record<string, number>;
  byKey: Record<string, number>;
}

const AREA_SET = new Set<string>(FALLBACK_AREAS);

export function bucketFallbackArea(area: string): string {
  const text = area.trim();
  return AREA_SET.has(text) ? text : "other";
}

export function bucketFallbackReason(reason: string): string {
  const text = reason.trim();
  return text || "unknown";
}

function emptyCounts(): FallbackTriageCounts {
  return {
    byOutcome: { recovered: 0, degraded: 0, exhausted: 0 },
    byArea: {},
    byKey: {},
  };
}

export function tallyFallbackObservations(
  observations: FallbackObservation[]
): FallbackTriageCounts {
  const counts = emptyCounts();
  for (const observation of observations) {
    if (
      !FALLBACK_OUTCOMES.includes(observation.outcome as FallbackOutcome) ||
      observation.count <= 0
    ) {
      continue;
    }
    const outcome = observation.outcome as FallbackOutcome;
    const area = bucketFallbackArea(observation.area);
    const reason = bucketFallbackReason(observation.reason);
    const key = `${observation.day}|${outcome}|${area}|${reason}`;
    counts.byOutcome[outcome] += observation.count;
    counts.byArea[area] = (counts.byArea[area] ?? 0) + observation.count;
    counts.byKey[key] = (counts.byKey[key] ?? 0) + observation.count;
  }
  return counts;
}

/** Input counts already weighted by the legacy SQL; never multiply again. */
export function fallbackObservationsFromLegacy(
  rows: FallbackObservation[]
): FallbackTriageCounts {
  return tallyFallbackObservations(rows);
}

export function fallbackObservationsFromAggregates(
  rows: TelemetryAggregateRow[]
): FallbackTriageCounts {
  const observations: FallbackObservation[] = [];
  for (const row of rows) {
    if (row.family !== "fallback") continue;
    const count = row.counters.observations ?? row.counters.observations_total;
    if (typeof count !== "number") continue;
    observations.push({
      day: row.day,
      area: row.dimensions.area ?? "other",
      reason: row.dimensions.reason ?? "unknown",
      outcome: row.dimensions.outcome ?? "unknown",
      count,
    });
  }
  return tallyFallbackObservations(observations);
}

export interface FallbackTriageComparison {
  equal: boolean;
  legacy: FallbackTriageCounts;
  replacement: FallbackTriageCounts;
  outcomeDeltas: Record<FallbackOutcome, number>;
  areaDeltas: Record<string, number>;
}

function deltaMap(
  left: Record<string, number>,
  right: Record<string, number>
): Record<string, number> {
  const keys = Array.from(
    new Set([...Object.keys(left), ...Object.keys(right)])
  );
  const deltas: Record<string, number> = {};
  for (const key of keys) {
    deltas[key] = (left[key] ?? 0) - (right[key] ?? 0);
  }
  return deltas;
}

export function compareFallbackTriage(
  legacy: FallbackTriageCounts,
  replacement: FallbackTriageCounts
): FallbackTriageComparison {
  const outcomeDeltas = {
    recovered: legacy.byOutcome.recovered - replacement.byOutcome.recovered,
    degraded: legacy.byOutcome.degraded - replacement.byOutcome.degraded,
    exhausted: legacy.byOutcome.exhausted - replacement.byOutcome.exhausted,
  };
  const areaDeltas = deltaMap(legacy.byArea, replacement.byArea);
  const keyDeltas = deltaMap(legacy.byKey, replacement.byKey);
  const equal =
    Object.values(outcomeDeltas).every((value) => value === 0) &&
    Object.values(areaDeltas).every((value) => value === 0) &&
    Object.values(keyDeltas).every((value) => value === 0);
  return { equal, legacy, replacement, outcomeDeltas, areaDeltas };
}
