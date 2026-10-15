/**
 * Frozen GET /v1/telemetry/client/aggregates response (schema v1).
 * Lane 1 owns the backend. This module is the admin reader's contract parser.
 */

export const TELEMETRY_SCHEMA_VERSION = 1;
export const TELEMETRY_ROW_LIMIT = 50_000;

export type TelemetryPlatform = "ios" | "android" | "macos";
export type TelemetryQueryChannel = "production" | "beta" | "all";
export type VoicePopulation = "physical_shortcut" | "floating_voice";

export interface TelemetryDurationBucket {
  le_seconds: number | "+Inf";
  count: number;
}

export interface TelemetryDuration {
  count: number;
  sum_ms: number;
  buckets: TelemetryDurationBucket[];
}

export interface TelemetryAggregateRow {
  day: string;
  platform: string;
  channel: string;
  family: string;
  dimensions: Record<string, string>;
  counters: Record<string, number>;
  durations: Record<string, TelemetryDuration>;
}

export interface TelemetryVoiceRow {
  day: string;
  channel: string;
  actor_id: string;
  health_event: string;
  outcome: string;
  reason: string;
  route: string;
  intent: string;
  count: number;
  duration_ms: number | null;
  /** Samples that actually carried a latency; mean = duration_ms / latency_count. */
  latency_count: number | null;
  population: string;
}

export interface TelemetryAggregatesResponse {
  schema_version: number;
  generated_at: string;
  coverage_start: string | null;
  complete_through: string | null;
  partial: boolean;
  available: boolean;
  rows: TelemetryAggregateRow[];
  voice_rows: TelemetryVoiceRow[];
}

export type AggregateDisposition =
  | "ok"
  | "partial"
  | "stale"
  | "unavailable"
  | "truncated";

export interface AggregateInterpretation {
  disposition: AggregateDisposition;
  /** Rows may be read. Truncated and unavailable feeds are not usable. */
  usable: boolean;
  body: TelemetryAggregatesResponse | null;
  code: string | null;
  /** Inclusive last day whose rows may be counted. Null when no rows are usable. */
  countThrough: string | null;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function isUtcDay(value: string): boolean {
  if (!DAY.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function utcDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addUtcDays(day: string, delta: number): string {
  const [year, month, date] = day.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1, date));
  next.setUTCDate(next.getUTCDate() + delta);
  return next.toISOString().slice(0, 10);
}

/** Yesterday UTC. Today's rollup is still open and is not a closed health day. */
export function lastClosedUtcDay(now: Date): string {
  return addUtcDays(utcDay(now), -1);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseVoiceRow(value: unknown): TelemetryVoiceRow | null {
  if (!isRecord(value)) return null;
  const day = stringField(value.day);
  const channel = stringField(value.channel);
  const actorId = stringField(value.actor_id);
  const healthEvent = stringField(value.health_event);
  const population = stringField(value.population);
  const count = value.count;
  if (!day || !isUtcDay(day) || !channel || !healthEvent || !population)
    return null;
  if (typeof count !== "number" || !Number.isInteger(count) || count < 0)
    return null;
  const duration = value.duration_ms;
  if (
    duration != null &&
    (typeof duration !== "number" || !Number.isFinite(duration) || duration < 0)
  ) {
    return null;
  }
  // Backend emits an explicit per-row latency sample count: means must use
  // latency-present samples (latency_count), not the success count.
  const latencyCount = value.latency_count;
  if (
    latencyCount != null &&
    (typeof latencyCount !== "number" ||
      !Number.isInteger(latencyCount) ||
      latencyCount < 0)
  ) {
    return null;
  }
  return {
    day,
    channel,
    actor_id: actorId ?? "",
    health_event: healthEvent,
    outcome: stringField(value.outcome) ?? "unknown",
    reason: stringField(value.reason) ?? "unknown",
    route: stringField(value.route) ?? "unknown",
    intent: stringField(value.intent) ?? "unknown",
    count,
    duration_ms: duration == null ? null : duration,
    latency_count: latencyCount == null ? null : latencyCount,
    population,
  };
}

function parseAggregateRow(value: unknown): TelemetryAggregateRow | null {
  if (!isRecord(value)) return null;
  const day = stringField(value.day);
  const platform = stringField(value.platform);
  const channel = stringField(value.channel);
  const family = stringField(value.family);
  if (!day || !isUtcDay(day) || !platform || !channel || !family) return null;
  if (!isRecord(value.dimensions) || !isRecord(value.counters)) return null;
  const dimensions: Record<string, string> = {};
  for (const [key, item] of Object.entries(value.dimensions)) {
    const text = stringField(item);
    if (!text) return null;
    dimensions[key] = text;
  }
  const counters: Record<string, number> = {};
  for (const [key, item] of Object.entries(value.counters)) {
    if (typeof item !== "number" || !Number.isInteger(item) || item < 0)
      return null;
    counters[key] = item;
  }
  return {
    day,
    platform,
    channel,
    family,
    dimensions,
    counters,
    durations: isRecord(value.durations)
      ? (value.durations as TelemetryAggregateRow["durations"])
      : {},
  };
}

export function parseAggregatesResponse(
  value: unknown
): TelemetryAggregatesResponse | null {
  if (!isRecord(value)) return null;
  if (value.schema_version !== TELEMETRY_SCHEMA_VERSION) return null;
  if (
    typeof value.available !== "boolean" ||
    typeof value.partial !== "boolean"
  )
    return null;
  if (!Array.isArray(value.rows) || !Array.isArray(value.voice_rows))
    return null;
  const generatedAt = stringField(value.generated_at);
  if (!generatedAt) return null;
  const coverage = value.coverage_start;
  const through = value.complete_through;
  if (coverage != null && (typeof coverage !== "string" || !isUtcDay(coverage)))
    return null;
  if (through != null && (typeof through !== "string" || !isUtcDay(through)))
    return null;
  const rows: TelemetryAggregateRow[] = [];
  for (const row of value.rows) {
    const parsed = parseAggregateRow(row);
    if (!parsed) return null;
    rows.push(parsed);
  }
  const voiceRows: TelemetryVoiceRow[] = [];
  for (const row of value.voice_rows) {
    const parsed = parseVoiceRow(row);
    if (!parsed) return null;
    voiceRows.push(parsed);
  }
  return {
    schema_version: 1,
    generated_at: generatedAt,
    coverage_start: coverage == null ? null : coverage,
    complete_through: through == null ? null : through,
    partial: value.partial,
    available: value.available,
    rows,
    voice_rows: voiceRows,
  };
}

function errorCode(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.code === "string") return payload.code;
  if (isRecord(payload.error) && typeof payload.error.code === "string")
    return payload.error.code;
  if (isRecord(payload.detail) && typeof payload.detail.code === "string")
    return payload.detail.code;
  return null;
}

/**
 * Coverage comes from ingestion health fields, not from a recent event or
 * query time. An empty body is not a healthy zero. Overflow is truncated,
 * never a shortened success.
 */
export function interpretAggregateResponse({
  httpStatus,
  payload,
  now,
}: {
  httpStatus: number;
  payload: unknown;
  now: Date;
}): AggregateInterpretation {
  const code = errorCode(payload);
  if (httpStatus === 503 && code === "telemetry_query_truncated") {
    return {
      disposition: "truncated",
      usable: false,
      body: null,
      code,
      countThrough: null,
    };
  }
  if (httpStatus === 503 || httpStatus >= 500 || httpStatus === 0) {
    return {
      disposition: "unavailable",
      usable: false,
      body: null,
      code: code ?? "telemetry_unavailable",
      countThrough: null,
    };
  }
  const body = parseAggregatesResponse(payload);
  if (!body || body.available !== true) {
    return {
      disposition: "unavailable",
      usable: false,
      body: null,
      code: code ?? "telemetry_unavailable",
      countThrough: null,
    };
  }
  const total = body.rows.length + body.voice_rows.length;
  // Contract/backend reject only OVERFLOW (> 50,000); exactly 50,000 is valid.
  if (total > TELEMETRY_ROW_LIMIT) {
    return {
      disposition: "truncated",
      usable: false,
      body: null,
      code: "telemetry_query_truncated",
      countThrough: null,
    };
  }
  if (!body.coverage_start || !body.complete_through) {
    return {
      disposition: "unavailable",
      usable: false,
      body: null,
      code: "telemetry_unavailable",
      countThrough: null,
    };
  }
  const closed = lastClosedUtcDay(now);
  if (body.complete_through < closed) {
    return {
      disposition: "stale",
      usable: true,
      body,
      code: null,
      countThrough: body.complete_through,
    };
  }
  if (body.partial) {
    return {
      disposition: "partial",
      usable: true,
      body,
      code: null,
      countThrough: body.complete_through,
    };
  }
  return {
    disposition: "ok",
    usable: true,
    body,
    code: null,
    countThrough: body.complete_through,
  };
}
