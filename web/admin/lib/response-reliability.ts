export type ReliabilitySource = "chat" | "voice";
export type ReliabilityChannel = "production" | "beta";

export interface ReliabilityMetric {
  attempts: number;
  success: number;
  failure: number;
  excluded: number;
  unresolved: number;
  successRate: number | null;
  failureRate: number | null;
  averageFullAnswerSeconds: number | null;
}

export interface ReliabilityDailyPoint {
  date: string;
  chatSuccess: number;
  chatFailure: number;
  chatExcluded: number;
  chatSuccessRate: number | null;
  chatAverageSeconds: number | null;
  voiceSuccess: number;
  voiceFailure: number;
  voiceExcluded: number;
  voiceSuccessRate: number | null;
  voiceAverageSeconds: number | null;
}

export interface ReliabilityBreakdown {
  label: string;
  success: number;
  failure: number;
  excluded: number;
  successRate: number | null;
  averageFullAnswerSeconds: number | null;
}

export interface ReliabilityFailureReason {
  source: ReliabilitySource;
  reason: string;
  count: number;
}

export interface ResponseReliabilitySeries {
  days: number;
  generatedAt: number;
  partial: boolean;
  availability: {
    chat: boolean;
    voice: boolean;
    voiceCoverageStart: string | null;
  };
  summary: {
    overall: ReliabilityMetric | null;
    chat: ReliabilityMetric | null;
    voice: ReliabilityMetric | null;
  };
  daily: ReliabilityDailyPoint[];
  failureReasons: ReliabilityFailureReason[];
  chatSurfaces: ReliabilityBreakdown[];
  voiceRoutes: ReliabilityBreakdown[];
}

export interface ResponseReliabilityPayload extends ResponseReliabilitySeries {
  channels: Record<ReliabilityChannel, ResponseReliabilitySeries>;
}

type ChatRow = [
  date: unknown,
  event: unknown,
  surface: unknown,
  reason: unknown,
  count: unknown,
  durationMs: unknown,
  actorId?: unknown,
];

type VoiceRow = [
  date: unknown,
  healthEvent: unknown,
  outcome: unknown,
  reason: unknown,
  route: unknown,
  intent: unknown,
  count: unknown,
  durationMs: unknown,
  source?: unknown,
  actorId?: unknown,
];

type MutableMetric = {
  attempts: number;
  success: number;
  failure: number;
  excluded: number;
  durationMs: number;
};

const CHAT_STARTED = "chat_agent_query_started";
const CHAT_COMPLETED = "chat_agent_query_completed";
const CHAT_FAILED = "chat_agent_error";
const CHAT_CANCELLED = "chat_agent_query_cancelled";

// PostHog's query API silently applies LIMIT 100 when a query has no LIMIT.
// These queries group by actor_id and order by day ASC, so the default limit
// truncated exactly the newest days off the charts. In HogQL a trailing
// ORDER BY/LIMIT after UNION ALL binds to the last arm only (verified against
// PostHog: `SELECT 1 UNION ALL SELECT 2 LIMIT 1` returns 2 rows), so the voice
// union is wrapped in a subquery with one outer LIMIT.
//
// 50_000 is PostHog's served maximum, verified live: LIMIT 100000 returns
// exactly 50000 rows. The route's overflow tripwire compares row counts
// against this constant, so it must equal the effective cap — a larger value
// would make `rows.length >= RELIABILITY_ROW_LIMIT` unreachable and
// truncation undetectable (the tests pin this).
export const RELIABILITY_ROW_LIMIT = 50_000;

const emptyMetric = (): MutableMetric => ({
  attempts: 0,
  success: 0,
  failure: 0,
  excluded: 0,
  durationMs: 0,
});

const numberValue = (value: unknown): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

const textValue = (value: unknown, fallback = "unknown"): string => {
  const text = String(value ?? "").trim();
  return text || fallback;
};

const percent = (numerator: number, denominator: number): number | null =>
  denominator > 0 ? Math.round((numerator / denominator) * 10_000) / 100 : null;

const averageSeconds = (
  durationMs: number,
  successes: number,
): number | null =>
  successes > 0 ? Math.round((durationMs / successes / 1_000) * 10) / 10 : null;

const finalizeMetric = (metric: MutableMetric): ReliabilityMetric => {
  const judged = metric.success + metric.failure;
  const terminals = judged + metric.excluded;
  return {
    attempts: metric.attempts,
    success: metric.success,
    failure: metric.failure,
    excluded: metric.excluded,
    unresolved: Math.max(0, metric.attempts - terminals),
    successRate: percent(metric.success, judged),
    failureRate: percent(metric.failure, judged),
    averageFullAnswerSeconds: averageSeconds(metric.durationMs, metric.success),
  };
};

const mergeMetric = (target: MutableMetric, source: MutableMetric): void => {
  target.attempts += source.attempts;
  target.success += source.success;
  target.failure += source.failure;
  target.excluded += source.excluded;
  target.durationMs += source.durationMs;
};

const addMetric = (
  map: Map<string, MutableMetric>,
  key: string,
  update: (metric: MutableMetric) => void,
): void => {
  const metric = map.get(key) ?? emptyMetric();
  update(metric);
  map.set(key, metric);
};

function buildDayKeys(days: number, now: Date): string[] {
  const end = new Date(now);
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));

  const keys: string[] = [];
  for (
    const date = new Date(start);
    date <= end;
    date.setUTCDate(date.getUTCDate() + 1)
  ) {
    keys.push(date.toISOString().slice(0, 10));
  }
  return keys;
}

const finalizeBreakdowns = (
  metrics: Map<string, MutableMetric>,
): ReliabilityBreakdown[] =>
  Array.from(metrics.entries())
    .map(([label, metric]) => {
      const finalized = finalizeMetric(metric);
      return {
        label,
        success: finalized.success,
        failure: finalized.failure,
        excluded: finalized.excluded,
        successRate: finalized.successRate,
        averageFullAnswerSeconds: finalized.averageFullAnswerSeconds,
      };
    })
    .sort(
      (a, b) =>
        b.success +
        b.failure +
        b.excluded -
        (a.success + a.failure + a.excluded),
    );

export function responseReliabilityQueries(days: number): {
  chat: string;
  voice: string;
} {
  const safeDays = Math.min(Math.max(Math.trunc(days), 1), 90);
  return {
    chat: `
      SELECT
        toString(toDate(timestamp)) AS day,
        event,
        coalesce(nullIf(toString(properties.surface), ''), 'unknown') AS surface,
        coalesce(nullIf(toString(properties.error_class), ''), 'unknown') AS reason,
        count() AS event_count,
        sum(if(event = '${CHAT_COMPLETED}', toFloatOrZero(toString(properties.duration_ms)), 0)) AS duration_ms,
        distinct_id AS actor_id
      FROM events
      WHERE event IN ('${CHAT_STARTED}', '${CHAT_COMPLETED}', '${CHAT_FAILED}', '${CHAT_CANCELLED}')
        AND timestamp >= toStartOfDay(now()) - INTERVAL ${safeDays - 1} DAY
        AND toIntOrZero(toString(properties.telemetry_schema_version)) >= 2
        AND toString(properties.surface) != 'floating_voice'
      GROUP BY day, event, surface, reason, actor_id
      ORDER BY day ASC
      LIMIT ${RELIABILITY_ROW_LIMIT}
    `,
    voice: `
      SELECT * FROM (
      SELECT
        toString(toDate(timestamp)) AS day,
        toString(properties.health_event) AS health_event,
        coalesce(nullIf(toString(properties.response_outcome), ''), 'unknown') AS outcome,
        coalesce(nullIf(toString(properties.terminal_reason), ''), 'unknown') AS reason,
        coalesce(nullIf(toString(properties.route), ''), 'unknown') AS route,
        coalesce(nullIf(toString(properties.intent), ''), 'unknown') AS intent,
        count() AS event_count,
        sum(if(toString(properties.response_outcome) = 'success', toFloatOrZero(toString(properties.duration_ms)), 0)) AS duration_ms,
        'physical_shortcut' AS source,
        distinct_id AS actor_id
      FROM events
      WHERE event = 'desktop_health_event'
        AND properties.health_event IN ('voice_turn_started', 'voice_turn_terminal')
        AND timestamp >= toStartOfDay(now()) - INTERVAL ${safeDays - 1} DAY
        AND toIntOrZero(toString(properties.telemetry_schema_version)) >= 1
        AND properties.intent IN ('hold', 'locked')
      GROUP BY day, health_event, outcome, reason, route, intent, actor_id
      UNION ALL
      SELECT
        toString(toDate(timestamp)) AS day,
        if(event = '${CHAT_STARTED}', 'voice_turn_started', 'voice_turn_terminal') AS health_event,
        if(
          event = '${CHAT_COMPLETED}',
          'success',
          if(event = '${CHAT_FAILED}', 'failure', if(event = '${CHAT_CANCELLED}', 'excluded', 'unknown'))
        ) AS outcome,
        coalesce(nullIf(toString(properties.error_class), ''), 'unknown') AS reason,
        'floating_voice' AS route,
        'legacy' AS intent,
        count() AS event_count,
        sum(if(event = '${CHAT_COMPLETED}', toFloatOrZero(toString(properties.duration_ms)), 0)) AS duration_ms,
        'floating_voice' AS source,
        distinct_id AS actor_id
      FROM events
      WHERE event IN ('${CHAT_STARTED}', '${CHAT_COMPLETED}', '${CHAT_FAILED}', '${CHAT_CANCELLED}')
        AND timestamp >= toStartOfDay(now()) - INTERVAL ${safeDays - 1} DAY
        AND toIntOrZero(toString(properties.telemetry_schema_version)) >= 2
        AND toString(properties.surface) = 'floating_voice'
      GROUP BY day, health_event, outcome, reason, route, intent, actor_id
      )
      ORDER BY day ASC
      LIMIT ${RELIABILITY_ROW_LIMIT}
    `,
  };
}

/**
 * Drop leading days with no telemetry activity so charts start where coverage
 * actually begins instead of rendering weeks of empty axis. A day with only
 * excluded turns (cancellations, silent voice) still counts as coverage —
 * an all-cancelled first day is a signal, not a gap. Interior gaps are kept —
 * those are real usage gaps.
 */
export function trimDailyToCoverage(
  daily: ReliabilityDailyPoint[],
): ReliabilityDailyPoint[] {
  const first = daily.findIndex(
    (point) =>
      point.chatSuccessRate != null ||
      point.voiceSuccessRate != null ||
      point.chatExcluded > 0 ||
      point.voiceExcluded > 0,
  );
  return first === -1 ? [] : daily.slice(first);
}

export function buildResponseReliabilityPayload({
  days,
  chatRows,
  voiceRows,
  chatAvailable,
  voiceAvailable,
  truncated = false,
  now = new Date(),
}: {
  days: number;
  chatRows: unknown[];
  voiceRows: unknown[];
  chatAvailable: boolean;
  voiceAvailable: boolean;
  truncated?: boolean;
  now?: Date;
}): ResponseReliabilitySeries {
  const safeDays = Math.min(Math.max(Math.trunc(days), 1), 90);
  const chat = emptyMetric();
  const voice = emptyMetric();
  const chatByDay = new Map<string, MutableMetric>();
  const voiceByDay = new Map<string, MutableMetric>();
  const chatSurfaces = new Map<string, MutableMetric>();
  const voiceRoutes = new Map<string, MutableMetric>();
  const failureReasonCounts = new Map<string, number>();
  let voiceCoverageStart: string | null = null;

  if (chatAvailable) {
    for (const rawRow of chatRows) {
      if (!Array.isArray(rawRow)) continue;
      const [
        dateRaw,
        eventRaw,
        surfaceRaw,
        reasonRaw,
        countRaw,
        durationMsRaw,
      ] = rawRow as ChatRow;
      const date = textValue(dateRaw, "");
      const event = textValue(eventRaw, "");
      const surface = textValue(surfaceRaw);
      const reason = textValue(reasonRaw);
      const count = numberValue(countRaw);
      const durationMs = numberValue(durationMsRaw);
      if (!date || count <= 0) continue;

      const update = (metric: MutableMetric) => {
        if (event === CHAT_STARTED) metric.attempts += count;
        if (event === CHAT_COMPLETED) {
          metric.success += count;
          metric.durationMs += durationMs;
        }
        if (event === CHAT_FAILED) metric.failure += count;
        if (event === CHAT_CANCELLED) metric.excluded += count;
      };
      update(chat);
      addMetric(chatByDay, date, update);
      addMetric(chatSurfaces, surface, update);
      if (event === CHAT_FAILED) {
        const key = `chat:${reason}`;
        failureReasonCounts.set(
          key,
          (failureReasonCounts.get(key) ?? 0) + count,
        );
      }
    }
  }

  if (voiceAvailable) {
    const hasPhysicalVoiceRows = voiceRows.some(
      (rawRow) =>
        Array.isArray(rawRow) &&
        textValue((rawRow as VoiceRow)[8], "physical_shortcut") ===
          "physical_shortcut" &&
        numberValue((rawRow as VoiceRow)[6]) > 0,
    );
    for (const rawRow of voiceRows) {
      if (!Array.isArray(rawRow)) continue;
      const [
        dateRaw,
        healthEventRaw,
        outcomeRaw,
        reasonRaw,
        routeRaw,
        ,
        countRaw,
        durationMsRaw,
        sourceRaw,
      ] = rawRow as VoiceRow;
      const source = textValue(sourceRaw, "physical_shortcut");
      if (
        hasPhysicalVoiceRows
          ? source !== "physical_shortcut"
          : source !== "floating_voice"
      )
        continue;
      const date = textValue(dateRaw, "");
      const healthEvent = textValue(healthEventRaw, "");
      const outcome = textValue(outcomeRaw, "");
      const reason = textValue(reasonRaw);
      const route = textValue(routeRaw);
      const count = numberValue(countRaw);
      const durationMs = numberValue(durationMsRaw);
      if (!date || count <= 0) continue;

      const update = (metric: MutableMetric) => {
        if (healthEvent === "voice_turn_started") metric.attempts += count;
        if (healthEvent !== "voice_turn_terminal") return;
        if (outcome === "success") {
          metric.success += count;
          metric.durationMs += durationMs;
        } else if (outcome === "failure") {
          metric.failure += count;
        } else if (outcome === "excluded") {
          metric.excluded += count;
        }
      };
      update(voice);
      addMetric(voiceByDay, date, update);
      if (healthEvent === "voice_turn_terminal") {
        const currentCoverageStart: string | null = voiceCoverageStart;
        if (
          currentCoverageStart === null ||
          date.localeCompare(currentCoverageStart) < 0
        ) {
          voiceCoverageStart = date;
        }
        addMetric(voiceRoutes, route, update);
        if (outcome === "failure") {
          const key = `voice:${reason}`;
          failureReasonCounts.set(
            key,
            (failureReasonCounts.get(key) ?? 0) + count,
          );
        }
      }
    }
  }

  const overall = emptyMetric();
  if (chatAvailable) mergeMetric(overall, chat);
  if (voiceAvailable) mergeMetric(overall, voice);

  const daily = buildDayKeys(safeDays, now).map(
    (date): ReliabilityDailyPoint => {
      const chatDay = chatByDay.get(date) ?? emptyMetric();
      const voiceDay = voiceByDay.get(date) ?? emptyMetric();
      const chatFinal = finalizeMetric(chatDay);
      const voiceFinal = finalizeMetric(voiceDay);
      return {
        date,
        chatSuccess: chatFinal.success,
        chatFailure: chatFinal.failure,
        chatExcluded: chatFinal.excluded,
        chatSuccessRate: chatAvailable ? chatFinal.successRate : null,
        chatAverageSeconds: chatAvailable
          ? chatFinal.averageFullAnswerSeconds
          : null,
        voiceSuccess: voiceFinal.success,
        voiceFailure: voiceFinal.failure,
        voiceExcluded: voiceFinal.excluded,
        voiceSuccessRate: voiceAvailable ? voiceFinal.successRate : null,
        voiceAverageSeconds: voiceAvailable
          ? voiceFinal.averageFullAnswerSeconds
          : null,
      };
    },
  );

  const failureReasons = Array.from(failureReasonCounts.entries())
    .map(([key, count]): ReliabilityFailureReason => {
      const [source, ...reasonParts] = key.split(":");
      return {
        source: source as ReliabilitySource,
        reason: reasonParts.join(":"),
        count,
      };
    })
    .sort((a, b) => b.count - a.count);

  return {
    days: safeDays,
    generatedAt: now.getTime(),
    partial: !chatAvailable || !voiceAvailable || truncated,
    availability: {
      chat: chatAvailable,
      voice: voiceAvailable,
      voiceCoverageStart,
    },
    summary: {
      overall: chatAvailable || voiceAvailable ? finalizeMetric(overall) : null,
      chat: chatAvailable ? finalizeMetric(chat) : null,
      voice: voiceAvailable ? finalizeMetric(voice) : null,
    },
    daily,
    failureReasons,
    chatSurfaces: chatAvailable ? finalizeBreakdowns(chatSurfaces) : [],
    voiceRoutes: voiceAvailable ? finalizeBreakdowns(voiceRoutes) : [],
  };
}

export function buildChannelReliabilityPayloads({
  days,
  chatRows,
  voiceRows,
  chatAvailable,
  voiceAvailable,
  channelByActor,
  truncated = false,
  now = new Date(),
}: {
  days: number;
  chatRows: unknown[];
  voiceRows: unknown[];
  chatAvailable: boolean;
  voiceAvailable: boolean;
  channelByActor: Map<string, ReliabilityChannel>;
  truncated?: boolean;
  now?: Date;
}): Record<ReliabilityChannel, ResponseReliabilitySeries> {
  const rowsForChannel = (
    rows: unknown[],
    actorIndex: number,
    channel: ReliabilityChannel,
  ) =>
    rows.filter(
      (row) =>
        Array.isArray(row) &&
        channelByActor.get(textValue(row[actorIndex])) === channel,
    );

  const build = (channel: ReliabilityChannel) =>
    buildResponseReliabilityPayload({
      days,
      chatRows: rowsForChannel(chatRows, 6, channel),
      voiceRows: rowsForChannel(voiceRows, 9, channel),
      chatAvailable,
      voiceAvailable,
      truncated,
      now,
    });

  return {
    production: build("production"),
    beta: build("beta"),
  };
}
