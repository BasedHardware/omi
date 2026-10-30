import type { TelemetryAggregatesResponse } from "@/lib/telemetry/aggregates";

const voice = (
  day: string,
  channel: "production" | "beta",
  actorId: string,
  healthEvent: "voice_turn_started" | "voice_turn_terminal",
  outcome: string,
  reason: string,
  route: string,
  intent: string,
  count: number,
  durationMs: number | null,
  population: "physical_shortcut" | "floating_voice",
  latencyCount: number | null = null
) => ({
  day,
  channel,
  actor_id: actorId,
  health_event: healthEvent,
  outcome,
  reason,
  route,
  intent,
  count,
  duration_ms: durationMs,
  latency_count: latencyCount ?? (durationMs == null ? null : count),
  population,
});

export function aggregateFixture(
  partial: Partial<TelemetryAggregatesResponse> &
    Pick<TelemetryAggregatesResponse, "voice_rows">
): TelemetryAggregatesResponse {
  return {
    schema_version: 1,
    generated_at: "2026-10-12T00:00:00Z",
    coverage_start: "2026-10-06",
    complete_through: "2026-10-11",
    partial: false,
    available: true,
    rows: [],
    ...partial,
    voice_rows: partial.voice_rows,
  };
}

/** Closed UTC window ending 2026-10-12, so yesterday is 2026-10-11. */
export const FIXTURE_NOW = new Date("2026-10-12T15:00:00Z");
export const FIXTURE_DAYS = 7;
export const FIXTURE_CUTOVER = "2026-10-10";

export const physicalProductionVoice = [
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_started",
    "unknown",
    "unknown",
    "hub",
    "hold",
    6,
    null,
    "physical_shortcut"
  ),
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_terminal",
    "success",
    "success",
    "hub",
    "hold",
    4,
    20_000,
    "physical_shortcut"
  ),
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_terminal",
    "failure",
    "playback_failed",
    "hub",
    "hold",
    1,
    null,
    "physical_shortcut"
  ),
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_terminal",
    "excluded",
    "cancelled",
    "hub",
    "hold",
    1,
    null,
    "physical_shortcut"
  ),
];

export const physicalBetaVoice = [
  voice(
    "2026-10-11",
    "beta",
    "beta-user",
    "voice_turn_started",
    "unknown",
    "unknown",
    "hub",
    "locked",
    2,
    null,
    "physical_shortcut"
  ),
  voice(
    "2026-10-11",
    "beta",
    "beta-user",
    "voice_turn_terminal",
    "failure",
    "timeout",
    "hub",
    "locked",
    2,
    null,
    "physical_shortcut"
  ),
];

export const floatingVoice = [
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_started",
    "unknown",
    "unknown",
    "floating_voice",
    "legacy",
    10,
    null,
    "floating_voice"
  ),
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_terminal",
    "success",
    "success",
    "floating_voice",
    "legacy",
    9,
    9_000,
    "floating_voice"
  ),
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_terminal",
    "failure",
    "timeout",
    "floating_voice",
    "legacy",
    1,
    null,
    "floating_voice"
  ),
];

export const nullLatencyVoice = [
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_started",
    "unknown",
    "unknown",
    "hub",
    "hold",
    2,
    null,
    "physical_shortcut"
  ),
  voice(
    "2026-10-10",
    "production",
    "prod-user",
    "voice_turn_terminal",
    "success",
    "success",
    "hub",
    "hold",
    2,
    null,
    "physical_shortcut"
  ),
];

export const mismatchedActorVoice = [
  voice(
    "2026-10-10",
    "beta",
    "prod-user",
    "voice_turn_terminal",
    "success",
    "success",
    "hub",
    "hold",
    5,
    5_000,
    "physical_shortcut"
  ),
];

export const missingActorVoice = [
  voice(
    "2026-10-10",
    "production",
    "",
    "voice_turn_terminal",
    "success",
    "success",
    "hub",
    "hold",
    3,
    3_000,
    "physical_shortcut"
  ),
];

export const historicalPosthogPhysical = [
  [
    "2026-10-09",
    "voice_turn_started",
    "unknown",
    "unknown",
    "hub",
    "hold",
    4,
    0,
    "physical_shortcut",
    "prod-user",
  ],
  [
    "2026-10-09",
    "voice_turn_terminal",
    "success",
    "success",
    "hub",
    "hold",
    4,
    8_000,
    "physical_shortcut",
    "prod-user",
  ],
  [
    "2026-10-10",
    "voice_turn_terminal",
    "success",
    "success",
    "hub",
    "hold",
    7,
    7_000,
    "physical_shortcut",
    "prod-user",
  ],
];

export const chatRows = [
  [
    "2026-10-10",
    "chat_agent_query_started",
    "main_chat",
    "unknown",
    2,
    0,
    "prod-user",
  ],
  [
    "2026-10-10",
    "chat_agent_query_completed",
    "main_chat",
    "unknown",
    2,
    4_000,
    "prod-user",
  ],
];

export const fallbackLegacy = [
  {
    day: "2026-10-10",
    area: "realtime_hub",
    reason: "timeout",
    outcome: "recovered",
    count: 3,
  },
  {
    day: "2026-10-10",
    area: "ptt_cascade",
    reason: "provider_5xx",
    outcome: "degraded",
    count: 2,
  },
  {
    day: "2026-10-10",
    area: "screen_task_gate",
    reason: "gate_unavailable",
    outcome: "exhausted",
    count: 1,
  },
  {
    day: "2026-10-11",
    area: "screen_task_extraction",
    reason: "provider_429",
    outcome: "exhausted",
    count: 4,
  },
  {
    day: "2026-10-11",
    area: "wal_upload",
    reason: "upload_failed",
    outcome: "recovered",
    count: 1,
  },
];

export const fallbackAggregateRows = [
  {
    day: "2026-10-10",
    platform: "macos",
    channel: "production",
    family: "fallback",
    dimensions: {
      area: "realtime_hub",
      from: "hub",
      to: "cascade",
      reason: "timeout",
      outcome: "recovered",
    },
    counters: { observations: 3 },
    durations: {},
  },
  {
    day: "2026-10-10",
    platform: "macos",
    channel: "production",
    family: "fallback",
    dimensions: {
      area: "ptt_cascade",
      from: "ptt",
      to: "legacy",
      reason: "provider_5xx",
      outcome: "degraded",
    },
    counters: { observations: 2 },
    durations: {},
  },
  {
    day: "2026-10-10",
    platform: "macos",
    channel: "beta",
    family: "fallback",
    dimensions: {
      area: "screen_task_gate",
      from: "gate",
      to: "none",
      reason: "gate_unavailable",
      outcome: "exhausted",
    },
    counters: { observations: 1 },
    durations: {},
  },
  {
    day: "2026-10-11",
    platform: "macos",
    channel: "production",
    family: "fallback",
    dimensions: {
      area: "screen_task_extraction",
      from: "extractor",
      to: "legacy",
      reason: "provider_429",
      outcome: "exhausted",
    },
    counters: { observations: 4 },
    durations: {},
  },
  {
    day: "2026-10-11",
    platform: "macos",
    channel: "production",
    family: "fallback",
    dimensions: {
      area: "not_a_triage_area",
      from: "wal",
      to: "retry",
      reason: "upload_failed",
      outcome: "recovered",
    },
    counters: { observations: 1 },
    durations: {},
  },
];

export const connectionObservations = [
  { event: "Device Connected", personId: "mobile-a", platform: "ios" as const },
  {
    event: "Device Disconnected Detailed",
    personId: "mobile-a",
    platform: "ios" as const,
  },
  {
    event: "Device Disconnected Detailed",
    personId: "mobile-a",
    platform: "android" as const,
  },
  {
    event: "Device Disconnected Detailed",
    personId: "mobile-a",
    platform: "ios" as const,
  },
  {
    event: "Device Disconnected",
    personId: "mobile-a",
    platform: "ios" as const,
  },
  {
    event: "Device Connected",
    personId: "mac-a",
    platform: "macos" as const,
  },
  {
    event: "Device Connected",
    personId: "mac-a",
    platform: "macos" as const,
  },
  {
    event: "Device Disconnected",
    personId: "mac-a",
    platform: "macos" as const,
  },
  {
    event: "Device Disconnected",
    personId: "mac-b",
    platform: "macos" as const,
  },
  {
    event: "Device Disconnected Detailed",
    personId: "mac-a",
    platform: "macos" as const,
  },
];
