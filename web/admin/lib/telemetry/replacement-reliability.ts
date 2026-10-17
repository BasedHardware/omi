import type { ReliabilityChannel } from "@/lib/response-reliability";
import {
  buildChannelReliabilityPayloads,
  buildResponseReliabilityPayload,
  type ResponseReliabilityPayload,
  type ResponseReliabilitySeries,
} from "@/lib/response-reliability";
import type {
  AggregateInterpretation,
  TelemetryVoiceRow,
  VoicePopulation,
} from "@/lib/telemetry/aggregates";
import { addUtcDays, utcDay } from "@/lib/telemetry/aggregates";
import type { ReliabilityReaderConfig } from "@/lib/telemetry/flags";

/**
 * Voice rows for the replacement reader.
 * Population is explicit. A missing physical population stays unavailable;
 * floating rows are never substituted for it.
 * A UTC day is counted from PostHog only before cutover and from the aggregate
 * feed only on or after cutover.
 */

export interface VoiceAssembly {
  voiceRows: unknown[];
  voiceAvailable: boolean;
  coveragePartial: boolean;
  excludedActors: number;
}

function dayKeys(days: number, now: Date): string[] {
  const end = utcDay(now);
  const start = addUtcDays(end, -(days - 1));
  const keys: string[] = [];
  for (let day = start; day <= end; day = addUtcDays(day, 1)) keys.push(day);
  return keys;
}

function rowDay(row: unknown): string {
  return Array.isArray(row) ? String(row[0] ?? "") : "";
}

function rowSource(row: unknown): string {
  return Array.isArray(row) ? String(row[8] ?? "").trim() : "";
}

function voiceKey(row: TelemetryVoiceRow): string {
  return [
    row.day,
    row.channel,
    row.actor_id,
    row.health_event,
    row.outcome,
    row.reason,
    row.route,
    row.intent,
    row.population,
  ].join("|");
}

function toTuple(row: TelemetryVoiceRow): unknown[] {
  return [
    row.day,
    row.health_event,
    row.outcome,
    row.reason,
    row.route,
    row.intent,
    row.count,
    row.duration_ms,
    row.population,
    row.actor_id,
    row.latency_count,
  ];
}

export function assembleVoiceRows({
  days,
  now,
  posthogVoiceRows,
  posthogVoiceAvailable,
  reader,
  aggregate,
  channelByActor,
}: {
  days: number;
  now: Date;
  posthogVoiceRows: unknown[];
  posthogVoiceAvailable: boolean;
  reader: ReliabilityReaderConfig;
  aggregate: AggregateInterpretation | null;
  channelByActor: Map<string, ReliabilityChannel>;
}): VoiceAssembly {
  if (!reader.enabled || !reader.cutover) {
    return {
      voiceRows: posthogVoiceRows,
      voiceAvailable: posthogVoiceAvailable,
      coveragePartial: false,
      excludedActors: 0,
    };
  }

  const keys = dayKeys(days, now);
  const historicalDays = keys.filter((day) => day < reader.cutover!);
  const replacementDays = keys.filter((day) => day >= reader.cutover!);
  let coveragePartial = false;
  let excludedActors = 0;

  const historical = historicalDays.length
    ? posthogVoiceRows.filter(
        (row) =>
          rowDay(row) < reader.cutover! && rowSource(row) === reader.population
      )
    : [];
  if (historicalDays.length > 0 && !posthogVoiceAvailable)
    coveragePartial = true;

  const feed = aggregate;
  const replacementUsable =
    replacementDays.length > 0 &&
    feed != null &&
    feed.usable &&
    feed.body != null &&
    feed.countThrough != null;

  if (replacementDays.length > 0 && !replacementUsable) coveragePartial = true;
  if (
    feed &&
    (feed.disposition === "partial" ||
      feed.disposition === "stale" ||
      feed.disposition === "truncated" ||
      feed.disposition === "unavailable")
  ) {
    coveragePartial = true;
  }

  const replacement: unknown[] = [];
  const seen = new Set<string>();
  if (replacementUsable && feed?.body) {
    const coverageStart = feed.body.coverage_start;
    for (const row of feed.body.voice_rows) {
      if (row.population !== reader.population) continue;
      if (row.day < reader.cutover) continue;
      if (coverageStart && row.day < coverageStart) continue;
      if (feed.countThrough && row.day > feed.countThrough) continue;
      if (!replacementDays.includes(row.day)) continue;
      if (row.count <= 0) continue;
      if (!row.actor_id) {
        excludedActors += 1;
        coveragePartial = true;
        continue;
      }
      const classified = channelByActor.get(row.actor_id);
      if (!classified || classified !== row.channel) {
        excludedActors += 1;
        coveragePartial = true;
        continue;
      }
      const key = voiceKey(row);
      if (seen.has(key)) {
        coveragePartial = true;
        continue;
      }
      seen.add(key);
      replacement.push(toTuple(row));
    }
  }

  const selectedPresent = replacement.some(
    (row) => Array.isArray(row) && Number(row[6] ?? 0) > 0
  );
  if (replacementDays.length > 0 && replacementUsable && !selectedPresent) {
    coveragePartial = true;
  }

  const voiceRows = [...historical, ...replacement];
  const historicalPresent = historical.length > 0;
  const voiceAvailable =
    historicalPresent || (replacementUsable && selectedPresent);

  return {
    voiceRows: voiceAvailable ? voiceRows : [],
    voiceAvailable,
    coveragePartial: coveragePartial || !voiceAvailable,
    excludedActors,
  };
}

export function assembleResponseReliability({
  days,
  now = new Date(),
  chatRows,
  posthogVoiceRows,
  chatAvailable,
  posthogVoiceAvailable,
  posthogTruncated = false,
  channelByActor,
  reader,
  aggregate,
}: {
  days: number;
  now?: Date;
  chatRows: unknown[];
  posthogVoiceRows: unknown[];
  chatAvailable: boolean;
  posthogVoiceAvailable: boolean;
  posthogTruncated?: boolean;
  channelByActor: Map<string, ReliabilityChannel>;
  reader: ReliabilityReaderConfig;
  aggregate: AggregateInterpretation | null;
}): ResponseReliabilityPayload {
  const voice = assembleVoiceRows({
    days,
    now,
    posthogVoiceRows,
    posthogVoiceAvailable,
    reader,
    aggregate,
    channelByActor,
  });
  const shared = {
    days,
    now,
    chatRows,
    voiceRows: voice.voiceRows,
    chatAvailable,
    voiceAvailable: voice.voiceAvailable,
    truncated: posthogTruncated,
    coveragePartial: voice.coveragePartial,
  };
  const aggregateSeries = buildResponseReliabilityPayload(shared);
  const channels = buildChannelReliabilityPayloads({
    ...shared,
    channelByActor,
  });
  if (!reader.enabled) {
    return { ...aggregateSeries, channels };
  }
  return {
    ...maskAbsentVoice(aggregateSeries),
    channels: {
      production: maskAbsentVoice(channels.production),
      beta: maskAbsentVoice(channels.beta),
    },
  };
}

function maskAbsentVoice(
  series: ResponseReliabilitySeries
): ResponseReliabilitySeries {
  const voice = series.summary.voice;
  const voiced =
    (voice?.attempts ?? 0) +
      (voice?.success ?? 0) +
      (voice?.failure ?? 0) +
      (voice?.excluded ?? 0) >
    0;
  if (!series.availability.voice || voiced) return series;
  return {
    ...series,
    partial: true,
    voiceSource: null,
    availability: {
      ...series.availability,
      voice: false,
      voiceCoverageStart: null,
    },
    summary: {
      ...series.summary,
      voice: null,
      overall: series.availability.chat ? series.summary.chat : null,
    },
    daily: series.daily.map((point) => ({
      ...point,
      voiceSuccessRate: null,
      voiceAverageSeconds: null,
    })),
    failureReasons: series.failureReasons.filter(
      (reason) => reason.source !== "voice"
    ),
    voiceRoutes: [],
  };
}

export function selectedPopulation(
  rows: TelemetryVoiceRow[],
  population: VoicePopulation
): TelemetryVoiceRow[] {
  return rows.filter((row) => row.population === population && row.count > 0);
}
